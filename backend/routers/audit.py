"""Audit trail read endpoints: per-integration history and the global feed."""
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import CurrentUser, get_current_user
from ..database import get_db
from ..search import escape_like

router = APIRouter(tags=["audit"])


def _entry_out(e: models.AuditEntry) -> schemas.AuditEntryOut:
    return schemas.AuditEntryOut(
        id=e.id,
        integration_id=e.integration_id,
        integration_name=e.integration_name,
        action=e.action.value,
        field=e.field,
        old_value=e.old_value,
        new_value=e.new_value,
        change_group_id=e.change_group_id,
        changed_by_email=e.changed_by_email,
        changed_by_name=e.changed_by_name,
        changed_at=e.changed_at,
    )


def _page(
    db: Session, conditions: list, page: int, page_size: int
) -> tuple[int, list[models.AuditEntry]]:
    total = (
        db.scalar(select(func.count()).select_from(models.AuditEntry).where(*conditions)) or 0
    )
    rows = db.scalars(
        select(models.AuditEntry)
        .where(*conditions)
        .order_by(models.AuditEntry.changed_at.desc(), models.AuditEntry.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return total, rows


@router.get("/integrations/{integration_id}/audit", response_model=schemas.AuditPageOut)
def integration_audit(
    integration_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> schemas.AuditPageOut:
    """History for one integration. Works for soft-deleted integrations —
    404 only when the id has no Integration row AND no audit rows."""
    conditions = [models.AuditEntry.integration_id == integration_id]
    total, rows = _page(db, conditions, page, page_size)
    if total == 0 and db.get(models.Integration, integration_id) is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    return schemas.AuditPageOut(
        items=[_entry_out(e) for e in rows], total=total, page=page, page_size=page_size
    )


@router.get("/audit", response_model=schemas.AuditPageOut)
def audit_feed(
    integration_id: str | None = Query(default=None),
    changed_by: str | None = Query(default=None, description="Email substring, case-insensitive"),
    action: models.AuditAction | None = Query(default=None),
    date_from: date | None = Query(default=None, description="ISO date, inclusive"),
    date_to: date | None = Query(default=None, description="ISO date, inclusive"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> schemas.AuditPageOut:
    """Global audit feed, newest first."""
    conditions: list = []
    if integration_id:
        conditions.append(models.AuditEntry.integration_id == integration_id)
    if changed_by:
        pattern = f"%{escape_like(changed_by.lower())}%"
        conditions.append(
            func.lower(models.AuditEntry.changed_by_email).like(pattern, escape="\\")
        )
    if action is not None:
        conditions.append(models.AuditEntry.action == action)
    if date_from is not None:
        conditions.append(
            models.AuditEntry.changed_at
            >= datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        )
    if date_to is not None:
        conditions.append(
            models.AuditEntry.changed_at
            < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
        )
    total, rows = _page(db, conditions, page, page_size)
    return schemas.AuditPageOut(
        items=[_entry_out(e) for e in rows], total=total, page=page, page_size=page_size
    )
