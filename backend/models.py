"""SQLAlchemy models for the Integration Dictionary.

Conventions:
- IDs are uuid4 hex strings (String(32)) for SQLite/Postgres portability.
- Enums are VARCHAR-backed (native_enum=False) so adding values never needs
  an ALTER TYPE migration and behavior matches across SQLite and Postgres.
- All datetimes are stored as UTC. SQLite returns them naive; use as_utc()
  before comparing.
- Case-insensitive uniqueness is enforced with unique indexes on lower(col).
"""
import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes even for timezone=True columns."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class Base(DeclarativeBase):
    pass


class Status(str, enum.Enum):
    planning = "planning"
    dev = "dev"
    test = "test"
    qa = "qa"
    prod = "prod"
    fixing = "fixing"


class Level(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Role(str, enum.Enum):
    general = "general"
    integration = "integration"


class LinkKind(str, enum.Enum):
    flow = "flow"
    integrated = "integrated"


class AuditAction(str, enum.Enum):
    created = "created"
    updated = "updated"
    deleted = "deleted"
    restored = "restored"  # reserved for a future restore endpoint
    commented = "commented"


def _enum(e: type[enum.Enum], name: str) -> SAEnum:
    return SAEnum(
        e,
        name=name,
        native_enum=False,
        length=20,
        values_callable=lambda x: [m.value for m in x],
    )


class AppUser(Base):
    """Known users, upserted on first authenticated request.

    `role` here is a cache of the last-resolved group membership and is used
    ONLY to populate approver dropdowns. RBAC enforcement always uses the
    live per-request role resolved in auth.py — never this column.
    """

    __tablename__ = "app_users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[Role] = mapped_column(_enum(Role, "role"), default=Role.general)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


Index("uq_app_users_email_lower", func.lower(AppUser.email), unique=True)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))


Index("uq_tags_name_lower", func.lower(Tag.name), unique=True)


class System(Base):
    """Shared pool of source/target systems."""

    __tablename__ = "systems"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))


Index("uq_systems_name_lower", func.lower(System.name), unique=True)


class IntegrationType(Base):
    """e.g. REST, SOAP, bespoke — creatable lookup."""

    __tablename__ = "integration_types"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))


Index("uq_integration_types_name_lower", func.lower(IntegrationType.name), unique=True)


class CredentialType(Base):
    """e.g. OAuth, Basic, API key — creatable lookup."""

    __tablename__ = "credential_types"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))


Index("uq_credential_types_name_lower", func.lower(CredentialType.name), unique=True)


integration_tags = Table(
    "integration_tags",
    Base.metadata,
    Column("integration_id", String(32), ForeignKey("integrations.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", String(32), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

integration_sources = Table(
    "integration_sources",
    Base.metadata,
    Column("integration_id", String(32), ForeignKey("integrations.id", ondelete="CASCADE"), primary_key=True),
    Column("system_id", String(32), ForeignKey("systems.id", ondelete="CASCADE"), primary_key=True),
)

integration_targets = Table(
    "integration_targets",
    Base.metadata,
    Column("integration_id", String(32), ForeignKey("integrations.id", ondelete="CASCADE"), primary_key=True),
    Column("system_id", String(32), ForeignKey("systems.id", ondelete="CASCADE"), primary_key=True),
)


class Integration(Base):
    __tablename__ = "integrations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[Status] = mapped_column(_enum(Status, "status"), default=Status.planning)
    type_id: Mapped[str | None] = mapped_column(ForeignKey("integration_types.id"), nullable=True)

    associated_projects: Mapped[str] = mapped_column(Text, default="")
    documentation_url: Mapped[str] = mapped_column(String(2000), default="")
    notes: Mapped[str] = mapped_column(Text, default="")

    complexity: Mapped[Level | None] = mapped_column(_enum(Level, "complexity"), nullable=True)
    business_logic: Mapped[Level | None] = mapped_column(_enum(Level, "business_logic"), nullable=True)

    design_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    design_approver_id: Mapped[str | None] = mapped_column(ForeignKey("app_users.id"), nullable=True)
    design_approval_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    code_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    code_approver_id: Mapped[str | None] = mapped_column(ForeignKey("app_users.id"), nullable=True)
    code_approval_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    credential_type_id: Mapped[str | None] = mapped_column(ForeignKey("credential_types.id"), nullable=True)
    account_used: Mapped[str] = mapped_column(String(500), default="")
    needed_roles: Mapped[str] = mapped_column(Text, default="")

    # Denormalized search artifacts. embedded_at is nulled whenever
    # search_document is rebuilt; embedding refresh is best-effort post-commit.
    # Both are deferred: they are large (the embedding is a ~1k-float vector) and
    # never used by the list/detail/graph read paths, so they are loaded only
    # when explicitly selected (search) or accessed (doc rebuild).
    search_document: Mapped[str] = mapped_column(Text, default="", deferred=True)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True, deferred=True)
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    version: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("app_users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_by_id: Mapped[str | None] = mapped_column(ForeignKey("app_users.id"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_id: Mapped[str | None] = mapped_column(ForeignKey("app_users.id"), nullable=True)

    type: Mapped[IntegrationType | None] = relationship(IntegrationType, lazy="selectin")
    credential_type: Mapped[CredentialType | None] = relationship(CredentialType, lazy="selectin")
    design_approver: Mapped[AppUser | None] = relationship(AppUser, foreign_keys=[design_approver_id], lazy="selectin")
    code_approver: Mapped[AppUser | None] = relationship(AppUser, foreign_keys=[code_approver_id], lazy="selectin")
    created_by: Mapped[AppUser | None] = relationship(AppUser, foreign_keys=[created_by_id], lazy="selectin")
    updated_by: Mapped[AppUser | None] = relationship(AppUser, foreign_keys=[updated_by_id], lazy="selectin")

    tags: Mapped[list[Tag]] = relationship(Tag, secondary=integration_tags, lazy="selectin", order_by=Tag.name)
    sources: Mapped[list[System]] = relationship(
        System, secondary=integration_sources, lazy="selectin", order_by=System.name
    )
    targets: Mapped[list[System]] = relationship(
        System, secondary=integration_targets, lazy="selectin", order_by=System.name
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


# Active integrations must have unique names (case-insensitive). The index is
# the arbiter — pre-checks still race, so callers must catch IntegrityError.
Index(
    "uq_integrations_name_active",
    func.lower(Integration.name),
    unique=True,
    postgresql_where=Integration.deleted_at.is_(None),
    sqlite_where=Integration.deleted_at.is_(None),
)


class IntegrationLink(Base):
    """Relationship edge between two integrations.

    kind='flow': data flows source -> target. "B is upstream of A" and
    "A lists B as upstream" are both the single edge (B, A, flow).
    kind='integrated': undirected; canonicalized so source_id < target_id.
    Cycles are legitimate and allowed.
    """

    __tablename__ = "integration_links"
    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "kind", name="uq_link_edge"),
        CheckConstraint("source_id != target_id", name="ck_link_no_self"),
        CheckConstraint("kind = 'flow' OR source_id < target_id", name="ck_link_integrated_canonical"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("integrations.id", ondelete="CASCADE"), index=True)
    target_id: Mapped[str] = mapped_column(ForeignKey("integrations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[LinkKind] = mapped_column(_enum(LinkKind, "link_kind"))


class AuditEntry(Base):
    """One row per changed field per mutating request.

    Identity and integration name are denormalized so history reads correctly
    after renames, role changes, or deletion. Rows from the same request share
    a change_group_id (including mirrored link rows written under the other
    integration of an edge). created/deleted rows carry a full JSON snapshot.
    """

    __tablename__ = "audit_entries"
    __table_args__ = (
        Index("ix_audit_integration_time", "integration_id", "changed_at"),
        Index("ix_audit_time", "changed_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    integration_id: Mapped[str] = mapped_column(ForeignKey("integrations.id"), index=True)
    integration_name: Mapped[str] = mapped_column(String(200))
    action: Mapped[AuditAction] = mapped_column(_enum(AuditAction, "audit_action"))
    field: Mapped[str | None] = mapped_column(String(80), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_group_id: Mapped[str] = mapped_column(String(32), index=True)
    changed_by_email: Mapped[str] = mapped_column(String(320))
    changed_by_name: Mapped[str] = mapped_column(String(255), default="")
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IntegrationComment(Base):
    """A freeform note/comment on an integration. Append-only: there is no
    update or delete path, so the discussion record is permanent. Each comment
    also writes a `commented` audit entry. Identity is denormalized so the note
    reads correctly after renames or user changes."""

    __tablename__ = "integration_comments"
    __table_args__ = (Index("ix_comment_integration_time", "integration_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    integration_id: Mapped[str] = mapped_column(ForeignKey("integrations.id"), index=True)
    body: Mapped[str] = mapped_column(Text, default="")
    author_email: Mapped[str] = mapped_column(String(320))
    author_name: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    attachments: Mapped[list["CommentAttachment"]] = relationship(
        "CommentAttachment", lazy="selectin", order_by="CommentAttachment.created_at"
    )


class CommentAttachment(Base):
    """An image/screenshot attached to a comment. Like comments, attachments
    are append-only — stored as binary in the database so the app stays
    portable across SQLite and Lakebase/Postgres with no object store."""

    __tablename__ = "comment_attachments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    comment_id: Mapped[str] = mapped_column(
        ForeignKey("integration_comments.id"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255), default="")
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    # Deferred so listing comments never drags image bytes into memory; the
    # serving endpoint loads it on demand when .data is accessed.
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
