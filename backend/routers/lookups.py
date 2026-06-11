"""Lookup endpoints backing dropdowns: tags, systems, types, credential
types, users (approver candidates), and enum value lists."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import CurrentUser, get_current_user
from ..database import get_db
from ..models import (
    AppUser,
    CredentialType,
    IntegrationType,
    Level,
    Role,
    Status,
    System,
    Tag,
)
from ..schemas import EnumsOut, NamedOut, UserOut

router = APIRouter(tags=["lookups"])


def _named(db: Session, model) -> list[NamedOut]:
    rows = db.scalars(select(model).order_by(func.lower(model.name))).all()
    return [NamedOut(id=r.id, name=r.name) for r in rows]


@router.get("/lookups/tags", response_model=list[NamedOut])
def list_tags(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[NamedOut]:
    return _named(db, Tag)


@router.get("/lookups/systems", response_model=list[NamedOut])
def list_systems(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[NamedOut]:
    return _named(db, System)


@router.get("/lookups/types", response_model=list[NamedOut])
def list_types(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[NamedOut]:
    return _named(db, IntegrationType)


@router.get("/lookups/credential-types", response_model=list[NamedOut])
def list_credential_types(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[NamedOut]:
    return _named(db, CredentialType)


@router.get("/lookups/users", response_model=list[UserOut])
def list_users(
    role: Role | None = Query(default=None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[UserOut]:
    """Known users; role=integration yields the approver candidate list.

    Filters on the cached AppUser.role (dropdown population only — RBAC
    enforcement always uses the live per-request role).
    """
    stmt = select(AppUser)
    if role is not None:
        stmt = stmt.where(AppUser.role == role)
    stmt = stmt.order_by(func.lower(AppUser.display_name), func.lower(AppUser.email))
    rows = db.scalars(stmt).all()
    return [
        UserOut(id=r.id, email=r.email, display_name=r.display_name, role=r.role.value)
        for r in rows
    ]


@router.get("/lookups/enums", response_model=EnumsOut)
def list_enums(user: CurrentUser = Depends(get_current_user)) -> EnumsOut:
    return EnumsOut(
        statuses=[s.value for s in Status],
        levels=[lv.value for lv in Level],
    )
