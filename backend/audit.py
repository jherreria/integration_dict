"""Audit trail helpers: link queries, display snapshots, and entry writers.

The snapshot is the single source of truth for "what does this integration
look like as display strings" — used for audit diffs, created/deleted
snapshots, and the search document.
"""
import json
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import (
    AuditAction,
    AuditEntry,
    Integration,
    IntegrationLink,
    LinkKind,
    Status,
    new_id,
)


@dataclass(frozen=True)
class LinkedRef:
    """A linked integration as needed by snapshots/refs/graph — just id, name,
    and status. Avoids loading full ORM rows (and their eager relationships)
    for every neighbor, which made link edits O(N) heavy queries."""

    id: str
    name: str
    status: Status


def link_refs(db: Session, integration_id: str) -> dict[str, list[LinkedRef]]:
    """Active integrations linked to this one, grouped by relationship.

    Selects only id/name/status and filters soft-deleted neighbors in SQL, so
    it never triggers the eager-loaded relationships on Integration.
    """
    cols = (Integration.id, Integration.name, Integration.status)

    def fetch(join_on, where) -> list[LinkedRef]:
        rows = db.execute(
            select(*cols)
            .join(IntegrationLink, join_on)
            .where(where, Integration.deleted_at.is_(None))
        ).all()
        return [LinkedRef(id=r.id, name=r.name, status=r.status) for r in rows]

    upstream = fetch(
        IntegrationLink.source_id == Integration.id,
        (IntegrationLink.target_id == integration_id) & (IntegrationLink.kind == LinkKind.flow),
    )
    downstream = fetch(
        IntegrationLink.target_id == Integration.id,
        (IntegrationLink.source_id == integration_id) & (IntegrationLink.kind == LinkKind.flow),
    )
    integrated_a = fetch(
        IntegrationLink.target_id == Integration.id,
        (IntegrationLink.source_id == integration_id) & (IntegrationLink.kind == LinkKind.integrated),
    )
    integrated_b = fetch(
        IntegrationLink.source_id == Integration.id,
        (IntegrationLink.target_id == integration_id) & (IntegrationLink.kind == LinkKind.integrated),
    )
    return {
        "upstream": sorted(upstream, key=lambda i: i.name.lower()),
        "downstream": sorted(downstream, key=lambda i: i.name.lower()),
        "integrated": sorted(integrated_a + integrated_b, key=lambda i: i.name.lower()),
    }


def _names(objs) -> str | None:
    joined = ", ".join(sorted((o.name for o in objs), key=str.lower))
    return joined or None


def _date_str(d: date | datetime | None) -> str | None:
    return d.isoformat() if d else None


def snapshot(db: Session, i: Integration) -> dict[str, str | None]:
    """All metadata as display strings, in presentation order."""
    refs = link_refs(db, i.id)
    return {
        "name": i.name,
        "description": i.description or None,
        "status": i.status.value,
        "type": i.type.name if i.type else None,
        "tags": _names(i.tags),
        "sources": _names(i.sources),
        "targets": _names(i.targets),
        "upstream": _names(refs["upstream"]),
        "downstream": _names(refs["downstream"]),
        "integrated": _names(refs["integrated"]),
        "associated_projects": i.associated_projects or None,
        "documentation_url": i.documentation_url or None,
        "complexity": i.complexity.value if i.complexity else None,
        "business_logic": i.business_logic.value if i.business_logic else None,
        "design_approved": "approved" if i.design_approved else "not approved",
        "design_approver": i.design_approver.email if i.design_approver else None,
        "design_approval_date": _date_str(i.design_approval_date),
        "code_approved": "approved" if i.code_approved else "not approved",
        "code_approver": i.code_approver.email if i.code_approver else None,
        "code_approval_date": _date_str(i.code_approval_date),
        "credential_type": i.credential_type.name if i.credential_type else None,
        "account_used": i.account_used or None,
        "needed_roles": i.needed_roles or None,
        "notes": i.notes or None,
    }


def diff_snapshots(
    before: dict[str, str | None], after: dict[str, str | None]
) -> dict[str, tuple[str | None, str | None]]:
    return {
        k: (before.get(k), after.get(k))
        for k in after
        if before.get(k) != after.get(k)
    }


def write_entry(
    db: Session,
    *,
    integration_id: str,
    integration_name: str,
    action: AuditAction,
    user,
    change_group_id: str,
    field: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
) -> AuditEntry:
    entry = AuditEntry(
        integration_id=integration_id,
        integration_name=integration_name,
        action=action,
        field=field,
        old_value=old_value,
        new_value=new_value,
        change_group_id=change_group_id,
        changed_by_email=user.email,
        changed_by_name=user.display_name,
    )
    db.add(entry)
    return entry


def audit_created(db: Session, i: Integration, snap: dict, user, change_group_id: str) -> None:
    write_entry(
        db,
        integration_id=i.id,
        integration_name=i.name,
        action=AuditAction.created,
        user=user,
        change_group_id=change_group_id,
        new_value=json.dumps(snap, ensure_ascii=False),
    )


def audit_deleted(db: Session, i: Integration, snap: dict, user, change_group_id: str) -> None:
    write_entry(
        db,
        integration_id=i.id,
        integration_name=i.name,
        action=AuditAction.deleted,
        user=user,
        change_group_id=change_group_id,
        old_value=json.dumps(snap, ensure_ascii=False),
    )


def audit_updated(
    db: Session,
    i: Integration,
    changes: dict[str, tuple[str | None, str | None]],
    user,
    change_group_id: str,
) -> None:
    for field, (old, new) in changes.items():
        write_entry(
            db,
            integration_id=i.id,
            integration_name=i.name,
            action=AuditAction.updated,
            user=user,
            change_group_id=change_group_id,
            field=field,
            old_value=old,
            new_value=new,
        )


def new_change_group_id() -> str:
    return new_id()
