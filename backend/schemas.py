"""Pydantic schemas and the field-level RBAC contract.

Payload shape convention:
- tags / sources / targets are lists of NAMES (server get-or-creates them).
- upstream / downstream / integrated are lists of integration IDs.
- approvers are app_user IDs.
PATCH is partial: only fields present in the request body are touched.
Sending null clears a nullable field; name/status/description cannot be null.
"""
from datetime import date, datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    field_validator,
)

from .models import Level, Status, as_utc

# SQLite hands back naive datetimes; normalize JSON output to UTC with offset
# so API consumers always see the same format.
UTCDateTime = Annotated[
    datetime,
    PlainSerializer(lambda v: as_utc(v).isoformat(), return_type=str, when_used="json"),
]

# Fields only the integration team may change (name is settable by anyone at
# creation; renaming is admin-only). Enforced diff-first in the router and
# surfaced to the frontend via GET /api/me so the UI never hardcodes it.
ADMIN_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "complexity",
        "business_logic",
        "design_approved",
        "design_approver_id",
        "design_approval_date",
        "code_approved",
        "code_approver_id",
        "code_approval_date",
    }
)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: str
    role: str


class MeOut(BaseModel):
    user: UserOut
    is_admin: bool
    admin_only_fields: list[str]


class NamedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str


class IntegrationRef(BaseModel):
    id: str
    name: str
    status: str


class IntegrationListItem(BaseModel):
    id: str
    name: str
    description: str
    status: str
    type: str | None
    tags: list[str]
    sources: list[str]
    targets: list[str]
    created_at: UTCDateTime
    updated_at: UTCDateTime
    updated_by: str | None


class IntegrationDetail(IntegrationListItem):
    associated_projects: str
    documentation_url: str
    notes: str
    complexity: str | None
    business_logic: str | None
    design_approved: bool
    design_approver: UserOut | None
    design_approval_date: date | None
    code_approved: bool
    code_approver: UserOut | None
    code_approval_date: date | None
    credential_type: str | None
    account_used: str
    needed_roles: str
    upstream: list[IntegrationRef]
    downstream: list[IntegrationRef]
    integrated: list[IntegrationRef]
    version: int
    created_by: str | None
    deleted_at: UTCDateTime | None


def _clean_str_list(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        v = v.strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


class IntegrationUpdate(BaseModel):
    """Partial update. extra='forbid' so typo'd field names fail loudly."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    status: Status | None = None
    type: str | None = Field(default=None, max_length=120)
    # Per-item length caps match the lookup columns (Tag 120, System 200) so
    # an over-long name fails with 422 on both SQLite and Postgres rather than
    # passing Pydantic and tripping a Postgres-only DataError at insert.
    tags: list[Annotated[str, StringConstraints(max_length=120)]] | None = None
    sources: list[Annotated[str, StringConstraints(max_length=200)]] | None = None
    targets: list[Annotated[str, StringConstraints(max_length=200)]] | None = None
    upstream: list[str] | None = None
    downstream: list[str] | None = None
    integrated: list[str] | None = None
    associated_projects: str | None = None
    documentation_url: str | None = Field(default=None, max_length=2000)
    notes: str | None = None
    complexity: Level | None = None
    business_logic: Level | None = None
    design_approved: bool | None = None
    design_approver_id: str | None = None
    design_approval_date: date | None = None
    code_approved: bool | None = None
    code_approver_id: str | None = None
    code_approval_date: date | None = None
    credential_type: str | None = Field(default=None, max_length=120)
    account_used: str | None = Field(default=None, max_length=500)
    needed_roles: str | None = None
    # Optimistic-concurrency precondition, not a data field. If provided and
    # it doesn't match the stored version, the request gets a 409.
    version: int | None = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v

    @field_validator("type", "credential_type")
    @classmethod
    def _strip_lookup(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None

    @field_validator("documentation_url")
    @classmethod
    def _safe_url(cls, v: str | None) -> str | None:
        # Defense in depth against stored-XSS via the link: reject any scheme
        # other than http/https (the frontend also guards at render time).
        if v is None:
            return None
        v = v.strip()
        if not v:
            return ""
        scheme = v.split(":", 1)[0].lower() if ":" in v.split("/", 1)[0] else ""
        if scheme and scheme not in ("http", "https"):
            raise ValueError("documentation_url must be an http(s) URL")
        return v

    @field_validator("tags", "sources", "targets")
    @classmethod
    def _clean_names(cls, v: list[str] | None) -> list[str] | None:
        return _clean_str_list(v)

    @field_validator("upstream", "downstream", "integrated")
    @classmethod
    def _clean_ids(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return list(dict.fromkeys(i.strip() for i in v if i.strip()))


class IntegrationCreate(IntegrationUpdate):
    name: str = Field(max_length=200)


class PageOut(BaseModel):
    items: list[IntegrationListItem]
    total: int
    page: int
    page_size: int
    search_mode_used: str | None = None


class AuditEntryOut(BaseModel):
    id: str
    integration_id: str
    integration_name: str
    action: str
    field: str | None
    old_value: str | None
    new_value: str | None
    change_group_id: str
    changed_by_email: str
    changed_by_name: str
    changed_at: UTCDateTime


class AuditPageOut(BaseModel):
    items: list[AuditEntryOut]
    total: int
    page: int
    page_size: int


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    content_type: str
    size_bytes: int


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    integration_id: str
    body: str
    author_email: str
    author_name: str
    created_at: UTCDateTime
    attachments: list[AttachmentOut] = []


class CommentPageOut(BaseModel):
    items: list[CommentOut]
    total: int
    page: int
    page_size: int


class GraphNode(BaseModel):
    id: str
    name: str
    status: str
    is_root: bool = False


class GraphEdge(BaseModel):
    source: str
    target: str
    kind: str


class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class SearchStatusOut(BaseModel):
    endpoint_configured: bool
    endpoint: str | None
    total: int
    embedded: int
    stale: int


class ReindexOut(BaseModel):
    indexed: int
    failed: int


class EnumsOut(BaseModel):
    statuses: list[str]
    levels: list[str]
