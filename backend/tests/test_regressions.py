"""Regression tests for issues found in the adversarial review pass."""
import backend.database as dbmod
import backend.search as search
from backend.models import Integration, IntegrationLink, LinkKind

from .conftest import ADMIN, create_integration


def _audit(client, iid):
    return client.get(f"/api/integrations/{iid}/audit", headers=ADMIN).json()["items"]


def test_create_with_links_writes_neighbor_mirror_audit(client):
    b = create_integration(client, "Billing").json()
    create_integration(client, "Consumer", upstream=[b["id"]]).json()
    rows = [e for e in _audit(client, b["id"]) if e["field"] == "downstream"]
    assert rows and "Consumer" in (rows[0]["new_value"] or "")


def test_create_with_links_refreshes_neighbor_search_document(client):
    b = create_integration(client, "Billing").json()
    create_integration(client, "Consumer", upstream=[b["id"]])
    s = dbmod.SessionLocal()
    try:
        assert "consumer" in s.get(Integration, b["id"]).search_document
    finally:
        s.close()


def test_link_edit_preserves_edges_to_soft_deleted_neighbor(client):
    b = create_integration(client, "Billing").json()
    d = create_integration(client, "DeletedUp").json()
    e = create_integration(client, "Editor", upstream=[d["id"], b["id"]]).json()
    client.delete(f"/api/integrations/{d['id']}", headers=ADMIN)
    # Editor now visibly has upstream=[Billing]; clearing it must not touch the
    # hidden edge to the soft-deleted DeletedUp.
    client.patch(f"/api/integrations/{e['id']}", json={"upstream": []}, headers=ADMIN)
    s = dbmod.SessionLocal()
    try:
        srcs = {
            x.source_id
            for x in s.query(IntegrationLink).filter(
                IntegrationLink.target_id == e["id"], IntegrationLink.kind == LinkKind.flow
            )
        }
        assert srcs == {d["id"]}
    finally:
        s.close()


def test_delete_propagates_to_neighbors(client):
    b = create_integration(client, "Billing").json()
    c = create_integration(client, "Consumer", upstream=[b["id"]]).json()
    client.delete(f"/api/integrations/{b['id']}", headers=ADMIN)
    removed = [
        e
        for e in _audit(client, c["id"])
        if e["field"] == "upstream" and (e["old_value"] or "") == "Billing" and e["new_value"] is None
    ]
    assert removed, "neighbor should have a mirror audit row for the removed upstream"
    s = dbmod.SessionLocal()
    try:
        assert "billing" not in s.get(Integration, c["id"]).search_document
    finally:
        s.close()


def test_documentation_url_rejects_dangerous_scheme(client):
    g = create_integration(client, "Guarded").json()
    bad = client.patch(
        f"/api/integrations/{g['id']}", json={"documentation_url": "javascript:alert(1)"}, headers=ADMIN
    )
    assert bad.status_code == 422
    ok = client.patch(
        f"/api/integrations/{g['id']}", json={"documentation_url": "https://wiki/x"}, headers=ADMIN
    )
    assert ok.status_code == 200


def test_overlong_tag_is_422_not_500(client):
    g = create_integration(client, "Guarded").json()
    r = client.patch(f"/api/integrations/{g['id']}", json={"tags": ["x" * 200]}, headers=ADMIN)
    assert r.status_code == 422


def test_unicode_case_insensitive_uniqueness(client):
    assert create_integration(client, "Café").status_code == 201
    assert create_integration(client, "CAFÉ").status_code == 409


def test_keyword_approved_does_not_match_every_row(client):
    create_integration(client, "Alpha").json()
    create_integration(client, "Beta", design_approved=True).json()
    res = client.get("/api/integrations?q=approved", headers=ADMIN).json()
    # Only the approved row should match — "not approved" no longer contains the token.
    names = {i["name"] for i in res["items"]}
    assert "Beta" in names and "Alpha" not in names


def test_semantic_tail_not_truncated(client, monkeypatch):
    """Un-embedded keyword matches survive even when the ranked head is full."""
    monkeypatch.setattr(search, "SEMANTIC_TOP_K", 2)
    monkeypatch.setattr(search, "SEMANTIC_MIN_SCORE", -1.0)
    monkeypatch.setattr(search, "ai_available", lambda: True)
    # Deterministic fake embedder: vector keys on whether 'widget' is present.
    monkeypatch.setattr(
        search, "embed_texts", lambda texts: [[1.0, 0.0] if "widget" in t else [0.0, 1.0] for t in texts]
    )
    for n in ("Widget One", "Widget Two", "Widget Three"):
        create_integration(client, n, description="widget pipeline")
    target = create_integration(client, "Lonely Gadget", description="gadget pipeline").json()
    # Leave target un-embedded (embedding stays NULL); query a term only it matches.
    res = client.get("/api/integrations?q=gadget&mode=ai", headers=ADMIN).json()
    assert res["search_mode_used"] == "ai"
    assert any(i["id"] == target["id"] for i in res["items"]), "un-embedded keyword match dropped"
