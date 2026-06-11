"""Keyword + semantic search behavior, status endpoint, and reindex RBAC."""
from sqlalchemy import select

import backend.search as search_mod
from backend.database import SessionLocal
from backend.models import Integration

from .conftest import ADMIN, USER, create_integration

VOCAB = ("billing", "invoice", "inventory", "warehouse")


def fake_embed_texts(texts):
    """Deterministic embedding: one dimension per vocabulary word."""
    return [[float(word in t.lower()) for word in VOCAB] for t in texts]


def _patch_ai(monkeypatch):
    monkeypatch.setattr(search_mod, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(search_mod, "ai_available", lambda: True)


def _names(page_json):
    return [item["name"] for item in page_json["items"]]


def test_search_status_default(client):
    create_integration(client, "Plain One")
    create_integration(client, "Plain Two")
    body = client.get("/api/search/status", headers=USER).json()
    assert body["endpoint_configured"] is False
    assert body["endpoint"] is None
    assert body["total"] == 2
    assert body["embedded"] == 0
    assert body["stale"] == 2


def test_ai_mode_without_endpoint_falls_back_to_keyword(client):
    create_integration(client, "Billing Engine", description="handles billing")
    resp = client.get(
        "/api/integrations", params={"q": "billing", "mode": "ai"}, headers=USER
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["search_mode_used"] == "keyword"
    assert _names(body) == ["Billing Engine"]


def test_ai_mode_ranks_by_embedding_and_keeps_keyword_tail(client, monkeypatch):
    create_integration(
        client, "Billing Engine", description="handles billing and invoice generation"
    )
    create_integration(
        client, "Inventory Sync", description="moves inventory to the warehouse"
    )
    create_integration(client, "Billing Notes", description="misc notes about billing")

    _patch_ai(monkeypatch)
    assert client.post("/api/search/reindex", headers=ADMIN).json()["indexed"] == 3

    # Strip the embedding from one keyword-matching row: it must still appear.
    with SessionLocal() as db:
        row = db.scalar(select(Integration).where(Integration.name == "Billing Notes"))
        row.embedding = None
        row.embedded_at = None
        db.commit()

    resp = client.get(
        "/api/integrations", params={"q": "billing", "mode": "ai"}, headers=USER
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["search_mode_used"] == "ai"
    names = _names(body)
    assert names[0] == "Billing Engine"
    assert "Billing Notes" in names  # unembedded but keyword-matched
    assert "Inventory Sync" not in names  # embedded but irrelevant


def test_keyword_search_escapes_like_wildcards(client):
    create_integration(client, "Alpha")
    create_integration(client, "Beta")

    # bare '%' must not act as match-everything
    resp = client.get("/api/integrations", params={"q": "%"}, headers=USER)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # '_' must not act as match-any-character ("a_pha" would match "alpha")
    resp = client.get("/api/integrations", params={"q": "a_pha"}, headers=USER)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # sanity: the un-wildcarded term does match
    resp = client.get("/api/integrations", params={"q": "alpha"}, headers=USER)
    assert resp.json()["total"] == 1


def test_reindex_requires_admin(client):
    resp = client.post("/api/search/reindex", headers=USER)
    assert resp.status_code == 403


def test_reindex_as_admin_indexes_rows(client, monkeypatch):
    create_integration(client, "Index Me")
    create_integration(client, "Index Me Too")
    monkeypatch.setattr(search_mod, "embed_texts", fake_embed_texts)

    resp = client.post("/api/search/reindex", headers=ADMIN)
    assert resp.status_code == 200
    body = resp.json()
    assert body["indexed"] == 2
    assert body["failed"] == 0

    status = client.get("/api/search/status", headers=ADMIN).json()
    assert status["embedded"] == 2
    assert status["stale"] == 0
