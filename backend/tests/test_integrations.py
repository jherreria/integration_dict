"""CRUD, filtering, pagination, optimistic concurrency and soft delete."""
from .conftest import ADMIN, USER, create_integration


def _names(page_json):
    return [item["name"] for item in page_json["items"]]


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------
def test_create_returns_201_and_detail_shape(client):
    resp = create_integration(
        client,
        "Orders Feed",
        description="Sends orders downstream",
        status="dev",
        tags=["finance"],
        sources=["ERP"],
        targets=["CRM"],
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Orders Feed"
    assert body["description"] == "Sends orders downstream"
    assert body["status"] == "dev"
    assert body["tags"] == ["finance"]
    assert body["sources"] == ["ERP"]
    assert body["targets"] == ["CRM"]
    assert body["version"] == 1
    assert body["upstream"] == [] and body["downstream"] == [] and body["integrated"] == []
    assert body["deleted_at"] is None
    assert body["created_by"] == "Ana Admin"
    # detail-only keys exist
    for key in ("complexity", "design_approved", "code_approver", "notes", "account_used"):
        assert key in body


def test_general_user_can_create_with_name(client):
    resp = create_integration(client, "User Made", headers=USER)
    assert resp.status_code == 201
    assert resp.json()["created_by"] == "Uma User"


def test_duplicate_name_conflict(client):
    assert create_integration(client, "foo").status_code == 201
    resp = create_integration(client, "foo")
    assert resp.status_code == 409


def test_case_insensitive_duplicate_conflict(client):
    assert create_integration(client, "foo").status_code == 201
    resp = create_integration(client, "Foo")
    assert resp.status_code == 409


def test_blank_name_rejected(client):
    assert create_integration(client, "").status_code == 422
    assert create_integration(client, "   ").status_code == 422


def test_unknown_payload_field_rejected(client):
    resp = client.post(
        "/api/integrations", json={"name": "x", "bogus_field": 1}, headers=ADMIN
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# patch
# ---------------------------------------------------------------------------
def test_patch_updates_scalar_and_collection_fields(client):
    iid = create_integration(client, "Patch Me").json()["id"]
    resp = client.patch(
        f"/api/integrations/{iid}",
        json={
            "description": "now described",
            "status": "prod",
            "tags": ["beta", "Alpha"],
            "sources": ["Warehouse"],
        },
        headers=ADMIN,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["description"] == "now described"
    assert body["status"] == "prod"
    assert body["tags"] == ["Alpha", "beta"]
    assert body["sources"] == ["Warehouse"]
    assert body["version"] == 2


def test_get_or_create_lookups_appear_in_lookup_endpoints(client):
    iid = create_integration(client, "Lookup Maker").json()["id"]
    resp = client.patch(
        f"/api/integrations/{iid}",
        json={"tags": ["Brand New Tag"], "sources": ["Brand New System"]},
        headers=ADMIN,
    )
    assert resp.status_code == 200
    tag_names = [t["name"] for t in client.get("/api/lookups/tags", headers=USER).json()]
    assert "Brand New Tag" in tag_names
    system_names = [s["name"] for s in client.get("/api/lookups/systems", headers=USER).json()]
    assert "Brand New System" in system_names


# ---------------------------------------------------------------------------
# list filters / search / pagination / sort
# ---------------------------------------------------------------------------
def test_list_status_filter(client):
    create_integration(client, "in prod", status="prod")
    create_integration(client, "in dev", status="dev")
    resp = client.get("/api/integrations", params={"status": "prod"}, headers=USER)
    assert resp.status_code == 200
    assert _names(resp.json()) == ["in prod"]


def test_list_tag_filter(client):
    create_integration(client, "tagged", tags=["Billing"])
    create_integration(client, "untagged")
    resp = client.get("/api/integrations", params={"tag": "billing"}, headers=USER)
    assert _names(resp.json()) == ["tagged"]


def test_list_system_filter_matches_source_or_target(client):
    create_integration(client, "uses as source", sources=["CRM"])
    create_integration(client, "uses as target", targets=["CRM"])
    create_integration(client, "unrelated", sources=["ERP"])
    resp = client.get("/api/integrations", params={"system": "crm"}, headers=USER)
    assert sorted(_names(resp.json())) == ["uses as source", "uses as target"]


def test_list_keyword_search_terms_anded_and_matches_metadata(client):
    create_integration(client, "Tag Match", tags=["fintech"])
    create_integration(client, "Desc Match", description="the fintech portal sync")
    create_integration(client, "Unrelated")

    # single term matches metadata (tag name) via the search document
    resp = client.get("/api/integrations", params={"q": "fintech"}, headers=USER)
    body = resp.json()
    assert body["search_mode_used"] == "keyword"
    assert sorted(_names(body)) == ["Desc Match", "Tag Match"]

    # multiple terms are ANDed
    resp = client.get("/api/integrations", params={"q": "fintech portal"}, headers=USER)
    assert _names(resp.json()) == ["Desc Match"]

    resp = client.get("/api/integrations", params={"q": "fintech zzznope"}, headers=USER)
    assert resp.json()["total"] == 0


def test_list_pagination_totals(client):
    for n in range(3):
        create_integration(client, f"pager {n}")
    p1 = client.get(
        "/api/integrations", params={"page": 1, "page_size": 2, "sort": "name", "order": "asc"},
        headers=USER,
    ).json()
    p2 = client.get(
        "/api/integrations", params={"page": 2, "page_size": 2, "sort": "name", "order": "asc"},
        headers=USER,
    ).json()
    assert p1["total"] == 3 and p2["total"] == 3
    assert len(p1["items"]) == 2 and len(p2["items"]) == 1
    assert p1["page"] == 1 and p2["page"] == 2
    assert _names(p1) + _names(p2) == ["pager 0", "pager 1", "pager 2"]


def test_list_sort_name_asc_case_insensitive(client):
    create_integration(client, "banana")
    create_integration(client, "Apple")
    create_integration(client, "cherry")
    resp = client.get("/api/integrations", params={"sort": "name", "order": "asc"}, headers=USER)
    assert _names(resp.json()) == ["Apple", "banana", "cherry"]


# ---------------------------------------------------------------------------
# optimistic concurrency
# ---------------------------------------------------------------------------
def test_patch_with_stale_version_conflicts(client):
    iid = create_integration(client, "Versioned").json()["id"]
    ok = client.patch(
        f"/api/integrations/{iid}", json={"description": "first", "version": 1}, headers=ADMIN
    )
    assert ok.status_code == 200
    assert ok.json()["version"] == 2
    stale = client.patch(
        f"/api/integrations/{iid}", json={"description": "second", "version": 1}, headers=ADMIN
    )
    assert stale.status_code == 409


def test_patch_without_version_is_last_write_wins(client):
    iid = create_integration(client, "Unversioned").json()["id"]
    client.patch(f"/api/integrations/{iid}", json={"description": "first"}, headers=ADMIN)
    resp = client.patch(f"/api/integrations/{iid}", json={"description": "second"}, headers=ADMIN)
    assert resp.status_code == 200
    assert resp.json()["description"] == "second"


# ---------------------------------------------------------------------------
# soft delete
# ---------------------------------------------------------------------------
def test_soft_delete_hides_and_frees_name(client):
    iid = create_integration(client, "Doomed").json()["id"]
    assert client.delete(f"/api/integrations/{iid}", headers=ADMIN).status_code == 204
    assert client.get(f"/api/integrations/{iid}", headers=ADMIN).status_code == 404
    listed = client.get("/api/integrations", headers=ADMIN).json()
    assert "Doomed" not in _names(listed)
    # the name is free again for a new active integration
    assert create_integration(client, "Doomed").status_code == 201


def test_patch_on_deleted_integration_404(client):
    iid = create_integration(client, "Gone").json()["id"]
    client.delete(f"/api/integrations/{iid}", headers=ADMIN)
    resp = client.patch(f"/api/integrations/{iid}", json={"description": "x"}, headers=ADMIN)
    assert resp.status_code == 404


def test_linking_to_deleted_integration_422(client):
    dead = create_integration(client, "Dead End").json()["id"]
    live = create_integration(client, "Alive").json()["id"]
    client.delete(f"/api/integrations/{dead}", headers=ADMIN)
    resp = client.patch(f"/api/integrations/{live}", json={"upstream": [dead]}, headers=ADMIN)
    assert resp.status_code == 422
