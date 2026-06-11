"""Append-only comment thread for an integration, with image attachments.

Any authenticated user (general or integration team) may add a comment with
optional image/screenshot attachments. There is deliberately NO update or
delete route — the discussion record is permanent. Every comment also writes a
`commented` audit entry. Attachment bytes are stored in the database so the app
stays portable across SQLite and Lakebase/Postgres.
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..auth import CurrentUser, get_current_user
from ..database import get_db
from ..models import AuditAction, CommentAttachment, Integration, IntegrationComment
from ..schemas import CommentOut, CommentPageOut

router = APIRouter(tags=["comments"])

MAX_BODY_CHARS = 10_000
MAX_ATTACHMENTS = 10
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024  # 5 MB per image

# Raster image types only. SVG is intentionally excluded — it can embed script.
# Each entry maps the allowed content type to the magic-byte prefixes that must
# start the file, so a mislabeled (or HTML-disguised) upload is rejected.
ALLOWED_IMAGE_TYPES: dict[str, tuple[bytes, ...]] = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/webp": (b"RIFF",),  # plus "WEBP" at offset 8, checked below
}


def _validate_image(content_type: str, data: bytes) -> None:
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image type '{content_type}'. Allowed: PNG, JPEG, GIF, WEBP.",
        )
    if len(data) == 0:
        raise HTTPException(status_code=422, detail="Attachment is empty")
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Attachment exceeds the {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB limit",
        )
    prefixes = ALLOWED_IMAGE_TYPES[content_type]
    if not any(data.startswith(p) for p in prefixes):
        raise HTTPException(status_code=422, detail="File content does not match its image type")
    if content_type == "image/webp" and data[8:12] != b"WEBP":
        raise HTTPException(status_code=422, detail="File content does not match its image type")


@router.get("/integrations/{integration_id}/comments", response_model=CommentPageOut)
def list_comments(
    integration_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> CommentPageOut:
    # Comments are a permanent record, so they remain readable even after the
    # integration is soft-deleted; 404 only when the id never existed.
    if db.get(Integration, integration_id) is None:
        raise HTTPException(status_code=404, detail="Integration not found")

    base = select(IntegrationComment).where(IntegrationComment.integration_id == integration_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(IntegrationComment.created_at.desc(), IntegrationComment.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return CommentPageOut(
        items=[CommentOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/integrations/{integration_id}/comments", response_model=CommentOut, status_code=201)
async def add_comment(
    integration_id: str,
    body: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> CommentOut:
    integration = db.get(Integration, integration_id)
    if integration is None or integration.is_deleted:
        raise HTTPException(status_code=404, detail="Integration not found")

    body = (body or "").strip()
    files = [f for f in files if f and f.filename]
    if not body and not files:
        raise HTTPException(status_code=422, detail="A comment needs text or at least one image")
    if len(body) > MAX_BODY_CHARS:
        raise HTTPException(status_code=422, detail=f"Comment exceeds {MAX_BODY_CHARS} characters")
    if len(files) > MAX_ATTACHMENTS:
        raise HTTPException(status_code=422, detail=f"At most {MAX_ATTACHMENTS} images per comment")

    # Read + validate every file before writing anything. Read at most one byte
    # past the limit so an oversized upload can't amplify into memory before the
    # size check rejects it.
    payloads: list[tuple[str, str, bytes]] = []
    for f in files:
        data = await f.read(MAX_ATTACHMENT_BYTES + 1)
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Attachment exceeds the {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB limit",
            )
        content_type = (f.content_type or "")
        _validate_image(content_type, data)
        # Truncate to the storage column widths so an over-long filename can't
        # cause a Postgres-only error at insert (SQLite ignores VARCHAR length).
        filename = (f.filename or "image")[:255]
        payloads.append((filename, content_type[:100], data))

    comment = IntegrationComment(
        integration_id=integration.id,
        body=body,
        author_email=user.email,
        author_name=user.display_name,
    )
    db.add(comment)
    db.flush()  # assign comment.id for the attachment FK
    for filename, content_type, data in payloads:
        db.add(
            CommentAttachment(
                comment_id=comment.id,
                filename=filename,
                content_type=content_type,
                size_bytes=len(data),
                data=data,
            )
        )

    note = body or "(no text)"
    if payloads:
        note += f" [{len(payloads)} image{'s' if len(payloads) != 1 else ''} attached]"
    audit.write_entry(
        db,
        integration_id=integration.id,
        integration_name=integration.name,
        action=AuditAction.commented,
        user=user,
        change_group_id=audit.new_change_group_id(),
        field="comment",
        new_value=note,
    )
    db.commit()
    db.refresh(comment)
    return CommentOut.model_validate(comment)


@router.get(
    "/integrations/{integration_id}/comments/{comment_id}/attachments/{attachment_id}",
    response_class=Response,
)
def get_attachment(
    integration_id: str,
    comment_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> Response:
    attachment = db.get(CommentAttachment, attachment_id)
    if attachment is None or attachment.comment_id != comment_id:
        raise HTTPException(status_code=404, detail="Attachment not found")
    comment = db.get(IntegrationComment, comment_id)
    if comment is None or comment.integration_id != integration_id:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return Response(
        content=attachment.data,
        media_type=attachment.content_type,
        headers={
            # Render inline, but never let the browser MIME-sniff it into
            # something executable.
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=86400",
        },
    )
