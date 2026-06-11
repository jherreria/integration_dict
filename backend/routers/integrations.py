"""Core CRUD + graph router for integrations.

Editing model: PATCH is diff-first. _stage_changes builds a plan of what
would actually change (compared against current values), which is used for
field-level RBAC, the no-op short-circuit, validation, and the apply step —
so the diff and the apply can never disagree.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status as http_status
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit, search
from ..auth import CurrentUser, get_current_user, require_admin
from ..database import get_db
from ..models import (
    AppUser,
    AuditAction,
    CredentialType,
    Integration,
    IntegrationLink,
    IntegrationType,
    LinkKind,
    Role,
    Status,
    System,
    Tag,
    utcnow,
)
from ..schemas import (
    ADMIN_ONLY_FIELDS,
    GraphEdge,
    GraphNode,
    GraphOut,
    IntegrationCreate,
    IntegrationDetail,
    IntegrationListItem,
    IntegrationRef,
    IntegrationUpdate,
    PageOut,
    UserOut,
)

router = APIRouter(tags=["integrations"])

# Plain column-ish fields settable directly on the row.
_SCALAR_FIELDS = (
    "name",
    "description",
    "status",
    "associated_projects",
    "documentation_url",
    "notes",
    "complexity",
    "business_logic",
    "design_approved",
    "design_approver_id",
    "design_approval_date",
    "code_approved",
    "code_approver_id",
    "code_approval_date",
    "account_used",
    "needed_roles",
)
# Non-nullable fields where an explicit null means "ignore" ...
_SKIP_IF_NONE = {"name", "status", "design_approved", "code_approved"}
# ... and non-nullable text fields where an explicit null means "clear".
_EMPTY_IF_NONE = {
    "description",
    "associated_projects",
    "documentation_url",
    "notes",
    "account_used",
    "needed_roles",
}

_LOOKUP_FIELDS = {"type": IntegrationType, "credential_type": CredentialType}
_NAME_COLLECTIONS = {"tags": Tag, "sources": System, "targets": System}
_LINK_FIELDS = ("upstream", "downstream", "integrated")
# Changing my "upstream" changes each affected neighbor's mirror field.
_MIRROR = {"upstream": "downstream", "downstream": "upstream", "integrated": "integrated"}

_SORT_COLUMNS = {
    "name": func.lower(Integration.name),
    "status": Integration.status,
    "created_at": Integration.created_at,
    "updated_at": Integration.updated_at,
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def get_or_create_named(db: Session, model, name: str):
    """Case-insensitive get-or-create for a named lookup row.

    The insert runs in a SAVEPOINT so a concurrent-create IntegrityError
    leaves the outer transaction usable; we then re-select the winner.
    """
    row = db.scalar(select(model).where(func.lower(model.name) == name.lower()))
    if row is not None:
        return row
    try:
        with db.begin_nested():
            row = model(name=name)
            db.add(row)
            db.flush()
        return row
    except IntegrityError:
        row = db.scalar(select(model).where(func.lower(model.name) == name.lower()))
        if row is None:
            raise
        return row


def _user_display(u: AppUser | None) -> str | None:
    if u is None:
        return None
    return u.display_name or u.email


def to_ref(i) -> IntegrationRef:
    # i is an audit.LinkedRef (id/name/status) or an Integration — both expose
    # the same three attributes.
    return IntegrationRef(id=i.id, name=i.name, status=i.status.value)


def to_list_item(i: Integration) -> IntegrationListItem:
    return IntegrationListItem(
        id=i.id,
        name=i.name,
        description=i.description,
        status=i.status.value,
        type=i.type.name if i.type else None,
        tags=sorted((t.name for t in i.tags), key=str.lower),
        sources=sorted((s.name for s in i.sources), key=str.lower),
        targets=sorted((s.name for s in i.targets), key=str.lower),
        created_at=i.created_at,
        updated_at=i.updated_at,
        updated_by=_user_display(i.updated_by),
    )


def to_detail(db: Session, i: Integration) -> IntegrationDetail:
    refs = audit.link_refs(db, i.id)
    return IntegrationDetail(
        **to_list_item(i).model_dump(),
        associated_projects=i.associated_projects,
        documentation_url=i.documentation_url,
        notes=i.notes,
        complexity=i.complexity.value if i.complexity else None,
        business_logic=i.business_logic.value if i.business_logic else None,
        design_approved=i.design_approved,
        design_approver=UserOut.model_validate(i.design_approver) if i.design_approver else None,
        design_approval_date=i.design_approval_date,
        code_approved=i.code_approved,
        code_approver=UserOut.model_validate(i.code_approver) if i.code_approver else None,
        code_approval_date=i.code_approval_date,
        credential_type=i.credential_type.name if i.credential_type else None,
        account_used=i.account_used,
        needed_roles=i.needed_roles,
        upstream=[to_ref(r) for r in refs["upstream"]],
        downstream=[to_ref(r) for r in refs["downstream"]],
        integrated=[to_ref(r) for r in refs["integrated"]],
        version=i.version,
        created_by=_user_display(i.created_by),
        deleted_at=i.deleted_at,
    )


def _name_taken(db: Session, name: str, exclude_id: str | None = None) -> bool:
    stmt = select(Integration.id).where(
        func.lower(Integration.name) == name.lower(),
        Integration.deleted_at.is_(None),
    )
    if exclude_id is not None:
        stmt = stmt.where(Integration.id != exclude_id)
    return db.scalar(stmt) is not None


def _name_conflict(name: str) -> HTTPException:
    return HTTPException(status_code=409, detail=f'An integration named "{name}" already exists')


def _current_link_ids(db: Session, integration_id: str) -> dict[str, set[str]]:
    """Active linked-integration ids per relationship (mirrors what the UI sees)."""
    refs = audit.link_refs(db, integration_id)
    return {field: {r.id for r in rows} for field, rows in refs.items()}


def _mirror_value(db: Session, integration_id: str, field: str) -> str | None:
    """A neighbor's link field rendered the way audit snapshots render it."""
    rows = audit.link_refs(db, integration_id)[field]
    return ", ".join(r.name for r in rows) or None


def _deleted_ids(db: Session, ids: set[str]) -> set[str]:
    """Subset of ids that point at soft-deleted integrations."""
    if not ids:
        return set()
    return set(
        db.scalars(
            select(Integration.id).where(
                Integration.id.in_(ids), Integration.deleted_at.is_not(None)
            )
        )
    )


def _mirror_pairs(plan: dict) -> set[tuple[str, str]]:
    """(neighbor_id, mirror_field) for every neighbor whose link to us changed."""
    pairs: set[tuple[str, str]] = set()
    for field in _LINK_FIELDS:
        if field in plan:
            mirror = _MIRROR[field]
            for neighbor_id in plan[field]["old"] ^ plan[field]["new"]:
                pairs.add((neighbor_id, mirror))
    return pairs


def _capture_mirror_values(
    db: Session, pairs: set[tuple[str, str]]
) -> dict[tuple[str, str], str | None]:
    return {(nid, mirror): _mirror_value(db, nid, mirror) for nid, mirror in pairs}


def _audit_and_refresh_neighbors(
    db: Session,
    pairs: set[tuple[str, str]],
    before: dict[tuple[str, str], str | None],
    user: CurrentUser,
    change_group: str,
) -> None:
    """Write a mirrored audit row and refresh the search doc for each neighbor
    whose mirror-field value actually changed. Call AFTER edges are flushed."""
    for nid, mirror in pairs:
        after_val = _mirror_value(db, nid, mirror)
        if after_val == before.get((nid, mirror)):
            continue
        neighbor = db.get(Integration, nid)
        if neighbor is None:
            continue
        audit.write_entry(
            db,
            integration_id=neighbor.id,
            integration_name=neighbor.name,
            action=AuditAction.updated,
            user=user,
            change_group_id=change_group,
            field=mirror,
            old_value=before.get((nid, mirror)),
            new_value=after_val,
        )
        if not neighbor.is_deleted:
            search.refresh_search_document(db, neighbor)


# --------------------------------------------------------------------------
# stage / validate / apply — shared by POST and PATCH
# --------------------------------------------------------------------------
def _stage_changes(db: Session, i: Integration, data: dict) -> dict:
    """Return a plan of fields that would ACTUALLY change.

    Keys are payload field names; a provided-but-unchanged field is absent.
    Values: scalars -> new value; type/credential_type -> name or None;
    tags/sources/targets -> list of names; links -> {"old": set, "new": set}.
    """
    plan: dict = {}

    for field in _SCALAR_FIELDS:
        if field not in data:
            continue
        value = data[field]
        if value is None:
            if field in _SKIP_IF_NONE:
                continue
            if field in _EMPTY_IF_NONE:
                value = ""
        if getattr(i, field) != value:
            plan[field] = value

    for field in _LOOKUP_FIELDS:
        if field not in data:
            continue
        new_name = data[field]
        current = getattr(i, field)
        current_name = current.name if current else None
        if new_name is None:
            if current_name is not None:
                plan[field] = None
        elif current_name is None or current_name.lower() != new_name.lower():
            plan[field] = new_name

    for field in _NAME_COLLECTIONS:
        if field not in data:
            continue
        new_names = data[field] or []
        current_set = {row.name.lower() for row in getattr(i, field)}
        if {n.lower() for n in new_names} != current_set:
            plan[field] = new_names

    current_links: dict[str, set[str]] | None = None
    for field in _LINK_FIELDS:
        if field not in data:
            continue
        if current_links is None:
            current_links = _current_link_ids(db, i.id)
        new_ids = set(data[field] or [])
        if new_ids != current_links[field]:
            plan[field] = {"old": current_links[field], "new": new_ids}

    return plan


def _validate_plan(db: Session, i: Integration, plan: dict) -> None:
    if "name" in plan and _name_taken(db, plan["name"], exclude_id=i.id):
        raise _name_conflict(plan["name"])

    for field in ("design_approver_id", "code_approver_id"):
        if field in plan and plan[field] is not None:
            approver = db.get(AppUser, plan[field])
            if approver is None or approver.role != Role.integration:
                raise HTTPException(
                    status_code=422,
                    detail="approver must be a member of the integration team "
                    "(they may need to open the app once)",
                )

    for field in _LINK_FIELDS:
        if field not in plan:
            continue
        new_ids: set[str] = plan[field]["new"]
        if i.id in new_ids:
            raise HTTPException(status_code=422, detail="an integration cannot link to itself")
        if not new_ids:
            continue
        rows = {
            r.id: r
            for r in db.scalars(select(Integration).where(Integration.id.in_(new_ids)))
        }
        for link_id in new_ids:
            row = rows.get(link_id)
            if row is None or row.is_deleted:
                raise HTTPException(
                    status_code=422,
                    detail=f"{field} contains an unknown or deleted integration id: {link_id}",
                )


def _apply_approval_defaults(i: Integration, plan: dict, data: dict, user: CurrentUser) -> None:
    """When an approval flag flips False->True, default approver/date if absent."""
    for prefix in ("design", "code"):
        if plan.get(f"{prefix}_approved") is not True:
            continue
        approver_field = f"{prefix}_approver_id"
        date_field = f"{prefix}_approval_date"
        if approver_field not in data and getattr(i, approver_field) is None:
            plan[approver_field] = user.id
        if date_field not in data and getattr(i, date_field) is None:
            plan[date_field] = datetime.now(timezone.utc).date()


def _replace_link_edges(db: Session, i: Integration, field: str, new_ids: set[str]) -> None:
    """Reconcile this integration's edges of one relationship to `new_ids`.

    Edges to soft-deleted neighbors are preserved: they are invisible in the
    diff (link_refs hides them) so the caller never intends to touch them, and
    dropping them would silently lose history.
    """
    if field == "integrated":
        existing = db.scalars(
            select(IntegrationLink).where(
                IntegrationLink.kind == LinkKind.integrated,
                or_(IntegrationLink.source_id == i.id, IntegrationLink.target_id == i.id),
            )
        ).all()
        others = {e.target_id if e.source_id == i.id else e.source_id for e in existing}
        deleted = _deleted_ids(db, others)
        wanted = {(min(i.id, other), max(i.id, other)) for other in new_ids}
        have: set[tuple[str, str]] = set()
        for edge in existing:
            pair = (edge.source_id, edge.target_id)
            other = edge.target_id if edge.source_id == i.id else edge.source_id
            if pair in wanted:
                have.add(pair)
            elif other not in deleted:
                db.delete(edge)
        for source_id, target_id in wanted - have:
            db.add(IntegrationLink(source_id=source_id, target_id=target_id, kind=LinkKind.integrated))
        return

    # flow edges: upstream = (other -> me), downstream = (me -> other)
    my_col = IntegrationLink.target_id if field == "upstream" else IntegrationLink.source_id
    existing = db.scalars(
        select(IntegrationLink).where(my_col == i.id, IntegrationLink.kind == LinkKind.flow)
    ).all()
    others = {e.source_id if field == "upstream" else e.target_id for e in existing}
    deleted = _deleted_ids(db, others)
    have_ids: set[str] = set()
    for edge in existing:
        other_id = edge.source_id if field == "upstream" else edge.target_id
        if other_id in new_ids:
            have_ids.add(other_id)
        elif other_id not in deleted:
            db.delete(edge)
    for other_id in new_ids - have_ids:
        if field == "upstream":
            db.add(IntegrationLink(source_id=other_id, target_id=i.id, kind=LinkKind.flow))
        else:
            db.add(IntegrationLink(source_id=i.id, target_id=other_id, kind=LinkKind.flow))


def _apply_plan(db: Session, i: Integration, plan: dict) -> None:
    for field, value in plan.items():
        if field in _LOOKUP_FIELDS:
            row = get_or_create_named(db, _LOOKUP_FIELDS[field], value) if value else None
            setattr(i, field, row)
        elif field in _NAME_COLLECTIONS:
            model = _NAME_COLLECTIONS[field]
            setattr(i, field, [get_or_create_named(db, model, name) for name in value])
        elif field in _LINK_FIELDS:
            _replace_link_edges(db, i, field, value["new"])
        elif field in ("design_approver_id", "code_approver_id"):
            setattr(i, field, value)
            # keep the eagerly-loaded relationship in sync for snapshots/docs
            setattr(i, field.removesuffix("_id"), db.get(AppUser, value) if value else None)
        else:
            setattr(i, field, value)


# --------------------------------------------------------------------------
# routes (static paths before dynamic ones)
# --------------------------------------------------------------------------
@router.get("/graph", response_model=GraphOut)
def full_graph(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> GraphOut:
    rows = db.scalars(select(Integration).where(Integration.deleted_at.is_(None))).all()
    ids = {r.id for r in rows}
    nodes = [
        GraphNode(id=r.id, name=r.name, status=r.status.value)
        for r in sorted(rows, key=lambda r: r.name.lower())
    ]
    edges = [
        GraphEdge(source=e.source_id, target=e.target_id, kind=e.kind.value)
        for e in db.scalars(
            select(IntegrationLink).where(
                IntegrationLink.source_id.in_(ids), IntegrationLink.target_id.in_(ids)
            )
        )
    ]
    return GraphOut(nodes=nodes, edges=edges)


@router.get("/integrations", response_model=PageOut)
def list_integrations(
    q: str = "",
    mode: str = "keyword",
    status: list[Status] | None = Query(None),
    type: str | None = None,
    tag: str | None = None,
    system: str | None = None,
    sort: str = "updated_at",
    order: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> PageOut:
    conditions = []
    if not (include_deleted and user.is_admin):
        conditions.append(Integration.deleted_at.is_(None))
    if status:
        conditions.append(Integration.status.in_(status))
    if type:
        conditions.append(Integration.type.has(func.lower(IntegrationType.name) == type.lower()))
    if tag:
        conditions.append(Integration.tags.any(func.lower(Tag.name) == tag.lower()))
    if system:
        wanted = system.lower()
        conditions.append(
            or_(
                Integration.sources.any(func.lower(System.name) == wanted),
                Integration.targets.any(func.lower(System.name) == wanted),
            )
        )

    q = q.strip()
    search_mode_used: str | None = None

    if q and mode == "ai" and search.ai_available():
        candidate_ids = list(db.scalars(select(Integration.id).where(*conditions)))
        ranked = search.semantic_rank(db, q, candidate_ids)
        if ranked is not None:
            start = (page - 1) * page_size
            page_ids = ranked[start : start + page_size]
            by_id = (
                {r.id: r for r in db.scalars(select(Integration).where(Integration.id.in_(page_ids)))}
                if page_ids
                else {}
            )
            return PageOut(
                items=[to_list_item(by_id[pid]) for pid in page_ids if pid in by_id],
                total=len(ranked),
                page=page,
                page_size=page_size,
                search_mode_used="ai",
            )
        # semantic search unavailable right now -> degrade to keyword

    stmt = select(Integration).where(*conditions)
    if q:
        stmt = stmt.where(*search.keyword_conditions(q))
        search_mode_used = "keyword"

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    sort_col = _SORT_COLUMNS.get(sort, Integration.updated_at)
    stmt = stmt.order_by(
        sort_col.asc() if order == "asc" else sort_col.desc(),
        func.lower(Integration.name).asc(),
    )
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return PageOut(
        items=[to_list_item(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        search_mode_used=search_mode_used,
    )


@router.post("/integrations", response_model=IntegrationDetail, status_code=201)
def create_integration(
    payload: IntegrationCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> IntegrationDetail:
    if not user.is_admin:
        violations = sorted((payload.model_fields_set & ADMIN_ONLY_FIELDS) - {"name"})
        if violations:
            raise HTTPException(
                status_code=403,
                detail={
                    "detail": "Only the integration team can set: " + ", ".join(violations),
                    "fields": violations,
                },
            )

    if _name_taken(db, payload.name):
        raise _name_conflict(payload.name)

    data = payload.model_dump(exclude_unset=True)
    data.pop("version", None)

    i = Integration(name=payload.name, created_by_id=user.id, updated_by_id=user.id)
    db.add(i)
    try:
        db.flush()  # assign id + column defaults before staging/links
    except IntegrityError:
        db.rollback()
        raise _name_conflict(payload.name)

    plan = _stage_changes(db, i, data)
    _validate_plan(db, i, plan)
    _apply_approval_defaults(i, plan, data, user)

    # Capture neighbors' mirror values before we wire up the new edges
    # (for a create, "old" is empty, so this is their pre-link rendering).
    pairs = _mirror_pairs(plan)
    neighbor_before = _capture_mirror_values(db, pairs)

    try:
        _apply_plan(db, i, plan)
        db.flush()
        change_group = audit.new_change_group_id()
        audit.audit_created(db, i, audit.snapshot(db, i), user, change_group)
        _audit_and_refresh_neighbors(db, pairs, neighbor_before, user, change_group)
        search.refresh_search_document(db, i)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _name_conflict(payload.name)

    search.update_embedding_post_commit(db, i.id)
    return to_detail(db, i)


@router.get("/integrations/{integration_id}", response_model=IntegrationDetail)
def get_integration(
    integration_id: str,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> IntegrationDetail:
    i = db.get(Integration, integration_id)
    if i is None or (i.is_deleted and not (include_deleted and user.is_admin)):
        raise HTTPException(status_code=404, detail="Integration not found")
    return to_detail(db, i)


@router.patch("/integrations/{integration_id}", response_model=IntegrationDetail)
def update_integration(
    integration_id: str,
    payload: IntegrationUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> IntegrationDetail:
    i = db.get(Integration, integration_id)
    if i is None or i.is_deleted:
        raise HTTPException(status_code=404, detail="Integration not found")
    seen_version = i.version

    data = payload.model_dump(exclude_unset=True)
    version_precond = data.pop("version", None)

    plan = _stage_changes(db, i, data)

    if not user.is_admin:
        violations = sorted(set(plan) & ADMIN_ONLY_FIELDS)
        if violations:
            raise HTTPException(
                status_code=403,
                detail={
                    "detail": "Only the integration team can edit: " + ", ".join(violations),
                    "fields": violations,
                },
            )

    if version_precond is not None and version_precond != seen_version:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This integration was modified by someone else "
                f"(your version {version_precond}, current {seen_version}). Reload and retry."
            ),
        )

    if not plan:
        return to_detail(db, i)

    _validate_plan(db, i, plan)
    _apply_approval_defaults(i, plan, data, user)

    before_snap = audit.snapshot(db, i)
    # Capture affected neighbors' mirror-field values before we touch edges.
    pairs = _mirror_pairs(plan)
    neighbor_before = _capture_mirror_values(db, pairs)
    attempted_name = plan.get("name", i.name)

    try:
        _apply_plan(db, i, plan)
        db.flush()

        after_snap = audit.snapshot(db, i)
        changes = audit.diff_snapshots(before_snap, after_snap)
        change_group = audit.new_change_group_id()
        if changes:
            audit.audit_updated(db, i, changes, user, change_group)
        _audit_and_refresh_neighbors(db, pairs, neighbor_before, user, change_group)

        i.updated_at = utcnow()
        i.updated_by_id = user.id
        i.updated_by = db.get(AppUser, user.id)
        search.refresh_search_document(db, i)
        if "name" in changes:
            _refresh_name_neighbor_docs(db, i, plan)
        db.flush()

        # Atomic optimistic lock: only one writer can advance from seen_version,
        # so a concurrent commit in the precondition->commit window loses here.
        stamped = db.execute(
            update(Integration)
            .where(Integration.id == integration_id, Integration.version == seen_version)
            .values(version=seen_version + 1)
        )
        if stamped.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="This integration was modified by someone else. Reload and retry.",
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        if _name_taken(db, attempted_name, exclude_id=integration_id):
            raise _name_conflict(attempted_name)
        raise HTTPException(
            status_code=409, detail="Concurrent modification, please reload and retry."
        )

    i.version = seen_version + 1
    search.update_embedding_post_commit(db, i.id)
    return to_detail(db, i)


def _refresh_name_neighbor_docs(db: Session, i: Integration, plan: dict) -> None:
    """After a rename, rebuild the search docs of integrations that embed our
    name — current neighbors plus any we just unlinked."""
    neighbor_ids: set[str] = set()
    for rows in audit.link_refs(db, i.id).values():
        neighbor_ids.update(r.id for r in rows)
    for field in _LINK_FIELDS:
        if field in plan:
            neighbor_ids.update(plan[field]["old"] - plan[field]["new"])
    neighbor_ids.discard(i.id)
    for neighbor_id in neighbor_ids:
        neighbor = db.get(Integration, neighbor_id)
        if neighbor is not None and not neighbor.is_deleted:
            search.refresh_search_document(db, neighbor)


@router.delete("/integrations/{integration_id}", status_code=204)
def delete_integration(
    integration_id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_admin),
) -> Response:
    i = db.get(Integration, integration_id)
    if i is None or i.is_deleted:
        raise HTTPException(status_code=404, detail="Integration not found")
    snap = audit.snapshot(db, i)

    # Removing this integration changes every active neighbor's mirror view
    # of it; capture their values before the delete hides it from link_refs.
    refs = audit.link_refs(db, i.id)
    pairs = {(r.id, _MIRROR[field]) for field in _LINK_FIELDS for r in refs[field]}
    neighbor_before = _capture_mirror_values(db, pairs)

    change_group = audit.new_change_group_id()
    i.deleted_at = utcnow()
    i.deleted_by_id = user.id
    db.flush()  # so link_refs now excludes this integration for neighbors
    audit.audit_deleted(db, i, snap, user, change_group)
    _audit_and_refresh_neighbors(db, pairs, neighbor_before, user, change_group)
    db.commit()
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@router.get("/integrations/{integration_id}/graph", response_model=GraphOut)
def integration_graph(
    integration_id: str,
    depth: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> GraphOut:
    root = db.get(Integration, integration_id)
    if root is None or root.is_deleted:
        raise HTTPException(status_code=404, detail="Integration not found")

    # BFS over all link kinds, undirected, skipping soft-deleted integrations.
    visited: set[str] = {root.id}
    frontier: list[str] = [root.id]
    hops = 0
    while frontier and (depth is None or hops < depth):
        hops += 1
        edges = db.scalars(
            select(IntegrationLink).where(
                or_(
                    IntegrationLink.source_id.in_(frontier),
                    IntegrationLink.target_id.in_(frontier),
                )
            )
        ).all()
        candidates = {
            endpoint
            for e in edges
            for endpoint in (e.source_id, e.target_id)
            if endpoint not in visited
        }
        if not candidates:
            break
        frontier = list(
            db.scalars(
                select(Integration.id).where(
                    Integration.id.in_(candidates), Integration.deleted_at.is_(None)
                )
            )
        )
        visited.update(frontier)

    rows = db.scalars(select(Integration).where(Integration.id.in_(visited))).all()
    nodes = [
        GraphNode(id=r.id, name=r.name, status=r.status.value, is_root=r.id == root.id)
        for r in sorted(rows, key=lambda r: r.name.lower())
    ]
    edges = [
        GraphEdge(source=e.source_id, target=e.target_id, kind=e.kind.value)
        for e in db.scalars(
            select(IntegrationLink).where(
                IntegrationLink.source_id.in_(visited),
                IntegrationLink.target_id.in_(visited),
            )
        )
    ]
    return GraphOut(nodes=nodes, edges=edges)
