"""Keyword + semantic search over integration metadata.

The search document is rebuilt from the audit snapshot (single source of
truth) on every change. Embeddings come from a Databricks model serving
endpoint and are refreshed best-effort AFTER commit — never inside a DB
transaction. embedded_at tracks freshness: it is nulled whenever the
document is rebuilt and set on successful embed; /api/search/reindex
backfills stale rows.
"""
import logging
import math

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import audit
from .config import get_settings
from .models import Integration, utcnow

logger = logging.getLogger(__name__)

EMBED_DOC_MAX_CHARS = 6000
EMBED_BATCH_SIZE = 16
SEMANTIC_TOP_K = 200
# Cosine similarity below this is noise, not a match.
SEMANTIC_MIN_SCORE = 0.5


# Boolean approval fields are indexed only in the positive case (as the field
# name, which contains "approved"); the negative "not approved" is omitted so a
# keyword search for "approved" doesn't match every row. The document is built
# from VALUES only — including the "key:" prefixes would let queries like
# "status" or "name" match every row via the label text.
_APPROVAL_FIELDS = {"design_approved", "code_approved"}


def build_search_document(db: Session, i: Integration) -> str:
    snap = audit.snapshot(db, i)
    parts: list[str] = []
    for key, value in snap.items():
        if not value:
            continue
        if key in _APPROVAL_FIELDS:
            if value == "approved":
                parts.append(key.replace("_", " "))  # e.g. "design approved"
            continue
        parts.append(str(value))
    if i.created_by:
        parts.append(i.created_by.email)
    if i.updated_by:
        parts.append(i.updated_by.email)
    return " | ".join(parts).lower()


def refresh_search_document(db: Session, i: Integration) -> None:
    doc = build_search_document(db, i)
    if doc != i.search_document:
        i.search_document = doc
        i.embedded_at = None


def escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def keyword_conditions(q: str) -> list:
    """AND-ed substring conditions over the search document."""
    return [
        Integration.search_document.like(f"%{escape_like(term.lower())}%", escape="\\")
        for term in q.split()
        if term
    ]


def ai_available() -> bool:
    return bool(get_settings().embedding_endpoint)


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Embed via the configured Databricks serving endpoint. None on failure."""
    settings = get_settings()
    if not settings.embedding_endpoint:
        return None
    try:
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()
        resp = w.serving_endpoints.query(
            name=settings.embedding_endpoint,
            input=[t[:EMBED_DOC_MAX_CHARS] for t in texts],
        )
        vectors = [d.embedding for d in resp.data]
        if len(vectors) != len(texts) or any(v is None for v in vectors):
            logger.warning("Embedding endpoint returned unexpected shape")
            return None
        return vectors
    except Exception:
        logger.warning("Embedding call failed", exc_info=True)
        return None


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def update_embedding_post_commit(db: Session, integration_id: str) -> None:
    """Best-effort embed of one row; called after the main transaction."""
    try:
        i = db.get(Integration, integration_id)
        if i is None or i.is_deleted or not i.search_document or i.embedded_at is not None:
            return
        doc = i.search_document
        vectors = embed_texts([doc])
        if vectors is None:
            return
        # Compare-and-set: only stamp this embedding as fresh if the document
        # hasn't changed (and been re-nulled) since we read it, so a concurrent
        # edit can never be masked by a stale embedding.
        result = db.execute(
            update(Integration)
            .where(
                Integration.id == integration_id,
                Integration.search_document == doc,
                Integration.embedded_at.is_(None),
            )
            .values(embedding=vectors[0], embedded_at=utcnow())
        )
        db.commit()
        if result.rowcount == 0:
            logger.debug("Embedding skipped for %s (document changed concurrently)", integration_id)
    except Exception:
        logger.warning("Post-commit embedding update failed", exc_info=True)
        db.rollback()


def semantic_rank(db: Session, q: str, candidate_ids: list[str]) -> list[str] | None:
    """Rank candidates by similarity to the query.

    Returns ranked ids of embedded rows that clear the relevance floor,
    followed by keyword-matched rows lacking embeddings (so un-embedded rows
    are never invisible). None when semantic search can't run at all.
    """
    if not candidate_ids:
        return []
    qvec_list = embed_texts([q])
    if qvec_list is None:
        return None
    qvec = qvec_list[0]

    rows = db.execute(
        select(
            Integration.id,
            Integration.embedding,
            Integration.embedded_at,
            Integration.search_document,
        ).where(Integration.id.in_(candidate_ids))
    ).all()

    scored: list[tuple[float, str]] = []
    unembedded: list[tuple[str, str]] = []
    for row_id, embedding, embedded_at, doc in rows:
        # Only trust an embedding that matches the current document. A row whose
        # doc changed but whose re-embed failed (embedded_at is None) is ranked
        # by keyword instead, so its new content stays findable.
        if embedding and embedded_at is not None:
            scored.append((cosine(qvec, embedding), row_id))
        else:
            unembedded.append((row_id, doc or ""))

    scored.sort(key=lambda t: t[0], reverse=True)
    ranked = [row_id for score, row_id in scored if score >= SEMANTIC_MIN_SCORE]

    terms = [t.lower() for t in q.split() if t]
    keyword_tail = [row_id for row_id, doc in unembedded if terms and all(t in doc for t in terms)]

    # Cap the ranked head but always keep the (already keyword-bounded) tail so
    # un-embedded matches never fall off the end.
    return ranked[:SEMANTIC_TOP_K] + keyword_tail


def search_status(db: Session) -> dict:
    settings = get_settings()
    rows = db.execute(
        select(Integration.id, Integration.embedded_at).where(Integration.deleted_at.is_(None))
    ).all()
    total = len(rows)
    embedded = sum(1 for _, embedded_at in rows if embedded_at is not None)
    return {
        "endpoint_configured": bool(settings.embedding_endpoint),
        "endpoint": settings.embedding_endpoint,
        "total": total,
        "embedded": embedded,
        "stale": total - embedded,
    }


def reindex(db: Session) -> tuple[int, int]:
    """Rebuild docs and re-embed stale rows. Returns (indexed, failed)."""
    integrations = db.scalars(select(Integration).where(Integration.deleted_at.is_(None))).all()
    for i in integrations:
        refresh_search_document(db, i)
    db.commit()

    stale = [i for i in integrations if i.embedded_at is None]
    indexed = failed = 0
    for start in range(0, len(stale), EMBED_BATCH_SIZE):
        batch = stale[start : start + EMBED_BATCH_SIZE]
        docs = [i.search_document for i in batch]
        vectors = embed_texts(docs)
        if vectors is None:
            failed += len(batch)
            continue
        now = utcnow()
        for i, vec, doc in zip(batch, vectors, docs):
            # Compare-and-set so a row edited since the doc rebuild isn't
            # stamped fresh against an outdated vector.
            result = db.execute(
                update(Integration)
                .where(
                    Integration.id == i.id,
                    Integration.search_document == doc,
                    Integration.embedded_at.is_(None),
                )
                .values(embedding=vec, embedded_at=now)
            )
            if result.rowcount:
                indexed += 1
        db.commit()
    return indexed, failed
