"""Identity and role resolution.

Inside a Databricks App the platform authenticates users and forwards
identity headers (x-forwarded-email etc.). Group membership (Entra groups
synced into the Databricks workspace) is resolved via the app's service
principal SCIM lookup, falling back to the user's on-behalf-of token when
present, and cached with a TTL. Local dev fakes identity from env vars.
"""
import logging
import threading
import time
from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import AppUser, Role, as_utc, utcnow

logger = logging.getLogger(__name__)

LAST_SEEN_WRITE_INTERVAL_SECONDS = 300


@dataclass
class CurrentUser:
    id: str
    email: str
    display_name: str
    role: Role
    groups: list[str]

    @property
    def is_admin(self) -> bool:
        return self.role == Role.integration


_group_cache: dict[str, tuple[float, list[str]]] = {}
_group_cache_lock = threading.Lock()


def _groups_via_service_principal(email: str) -> list[str] | None:
    try:
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()
        # SCIM filter strings use double quotes; refuse emails that would
        # break out of the literal rather than attempting to escape.
        if '"' in email or "\\" in email:
            logger.warning("Refusing SCIM lookup for suspicious email %r", email)
            return []
        users = list(w.users.list(filter=f'userName eq "{email}"', attributes="id,userName,groups"))
        if not users:
            return []
        return [g.display for g in (users[0].groups or []) if g.display]
    except Exception:
        logger.warning("Service-principal group lookup failed for %s", email, exc_info=True)
        return None


def _groups_via_obo_token(token: str) -> list[str] | None:
    settings = get_settings()
    if not settings.workspace_host:
        return None
    try:
        resp = httpx.get(
            f"{settings.workspace_host}/api/2.0/preview/scim/v2/Me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        return [g.get("display") for g in resp.json().get("groups", []) if g.get("display")]
    except Exception:
        logger.warning("On-behalf-of group lookup failed", exc_info=True)
        return None


def resolve_groups(email: str, obo_token: str | None = None) -> list[str]:
    settings = get_settings()
    key = email.lower()
    now = time.monotonic()
    with _group_cache_lock:
        cached = _group_cache.get(key)
        if cached and now - cached[0] < settings.group_cache_ttl_seconds:
            return cached[1]

    groups = _groups_via_service_principal(email)
    if groups is None and obo_token:
        groups = _groups_via_obo_token(obo_token)
    if groups is None:
        logger.error("Could not resolve groups for %s; treating as no groups", email)
        groups = []

    with _group_cache_lock:
        _group_cache[key] = (now, groups)
    return groups


def clear_group_cache() -> None:
    with _group_cache_lock:
        _group_cache.clear()


def _role_from_groups(groups: list[str]) -> Role:
    admin = get_settings().admin_group_set
    if any(g.lower() in admin for g in groups):
        return Role.integration
    return Role.general


def _upsert_app_user(db: Session, email: str, display_name: str, role: Role) -> AppUser:
    row = db.scalar(select(AppUser).where(func.lower(AppUser.email) == email.lower()))
    now = utcnow()
    if row is None:
        row = AppUser(email=email, display_name=display_name, role=role)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            # Concurrent first request from the same user won the insert.
            db.rollback()
            row = db.scalar(select(AppUser).where(func.lower(AppUser.email) == email.lower()))
            if row is None:
                raise
        return row

    changed = False
    if row.role != role:
        row.role = role
        changed = True
    if display_name and row.display_name != display_name:
        row.display_name = display_name
        changed = True
    last_seen = as_utc(row.last_seen_at)
    if last_seen is None or (now - last_seen).total_seconds() > LAST_SEEN_WRITE_INTERVAL_SECONDS:
        row.last_seen_at = now
        changed = True
    if changed:
        db.commit()
    return row


def get_current_user(request: Request, db: Session = Depends(get_db)) -> CurrentUser:
    settings = get_settings()

    if settings.dev_mode:
        email = settings.dev_user_email
        display_name = settings.dev_user_name
        role = Role.integration if settings.dev_user_role == "integration" else Role.general
        groups = sorted(settings.admin_group_set) if role == Role.integration else []
    else:
        email = request.headers.get("x-forwarded-email")
        if not email:
            raise HTTPException(
                status_code=401,
                detail="No authenticated user (expected Databricks Apps forwarded headers)",
            )
        display_name = request.headers.get("x-forwarded-preferred-username") or email.split("@")[0]
        groups = resolve_groups(email, request.headers.get("x-forwarded-access-token"))
        role = _role_from_groups(groups)

    row = _upsert_app_user(db, email, display_name, role)
    return CurrentUser(id=row.id, email=row.email, display_name=row.display_name, role=role, groups=groups)


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="This action requires the integration team role")
    return user
