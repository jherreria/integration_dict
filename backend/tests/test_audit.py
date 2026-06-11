"""Audit trail: snapshots, per-field rows, mirrored link rows, global feed."""
import json

from .conftest import ADMIN, USER, create_integration


def _audit(client, iid, **params):
    resp = client.get(f"/api/integrations/{iid}/audit", params=params, headers=ADMIN)
    assert resp.status_code == 200
    return resp.json()


def test_create_writes_created_entry_with_json_snapshot(client):
    iid = create_integration(client, "Audited", tags=["alpha"]).json()["id"]
    body = _audit(client, iid)
    assert body["total"] == 1
    entry = body["items"][0]
    assert entry["action"] == "created"
    assert entry["field"] is None
    assert entry["old_value"] is None
    snap = json.loads(entry["new_value"])
    assert snap["name"] == "Audited"
    assert snap["tags"] == "alpha"
    assert entry["changed_by_email"] == "admin@example.com"


def test_patch_writes_one_row_per_field_in_one_group(client):
    iid = create_integration(client, "Grouped").json()["id"]
    resp = client.patch(
        f"/api/integrations/{iid}",
        json={"description": "fresh words", "tags": ["beta", "alpha"]},
        headers=ADMIN,
    )
    assert resp.status_code == 200
    updated = [e for e in _audit(client, iid)["items"] if e["action"] == "updated"]
    assert {e["field"] for e in updated} == {"description", "tags"}
    assert len({e["change_group_id"] for e in updated}) == 1
    by_field = {e["field"]: e for e in updated}
    assert by_field["description"]["old_value"] is None
    assert by_field["description"]["new_value"] == "fresh words"
    assert by_field["tags"]["new_value"] == "alpha, beta"


def test_link_change_writes_mirrored_rows(client):
    a = create_integration(client, "Alpha Flow").json()["id"]
    b = create_integration(client, "Beta Flow").json()["id"]

    resp = client.patch(f"/api/integrations/{a}", json={"upstream": [b]}, headers=ADMIN)
    assert resp.status_code == 200

    a_rows = [e for e in _audit(client, a)["items"] if e["field"] == "upstream"]
    b_rows = [e for e in _audit(client, b)["items"] if e["field"] == "downstream"]
    assert len(a_rows) == 1 and len(b_rows) == 1
    assert a_rows[0]["old_value"] is None and a_rows[0]["new_value"] == "Beta Flow"
    assert b_rows[0]["old_value"] is None and b_rows[0]["new_value"] == "Alpha Flow"
    assert a_rows[0]["change_group_id"] == b_rows[0]["change_group_id"]


def test_link_removal_writes_both_sides_again(client):
    a = create_integration(client, "Alpha Flow").json()["id"]
    b = create_integration(client, "Beta Flow").json()["id"]
    client.patch(f"/api/integrations/{a}", json={"upstream": [b]}, headers=ADMIN)

    resp = client.patch(f"/api/integrations/{a}", json={"upstream": []}, headers=ADMIN)
    assert resp.status_code == 200

    a_rows = [e for e in _audit(client, a)["items"] if e["field"] == "upstream"]
    b_rows = [e for e in _audit(client, b)["items"] if e["field"] == "downstream"]
    assert len(a_rows) == 2 and len(b_rows) == 2
    removal_a = next(e for e in a_rows if e["new_value"] is None)
    removal_b = next(e for e in b_rows if e["new_value"] is None)
    assert removal_a["old_value"] == "Beta Flow"
    assert removal_b["old_value"] == "Alpha Flow"
    assert removal_a["change_group_id"] == removal_b["change_group_id"]
    # the removal group differs from the add group
    add_a = next(e for e in a_rows if e["new_value"] is not None)
    assert removal_a["change_group_id"] != add_a["change_group_id"]


def test_delete_writes_snapshot_and_history_survives(client):
    iid = create_integration(client, "Short Lived", description="bye").json()["id"]
    assert client.delete(f"/api/integrations/{iid}", headers=ADMIN).status_code == 204

    body = _audit(client, iid)
    actions = {e["action"] for e in body["items"]}
    assert {"created", "deleted"} <= actions
    deleted = next(e for e in body["items"] if e["action"] == "deleted")
    snap = json.loads(deleted["old_value"])
    assert snap["name"] == "Short Lived"
    assert deleted["new_value"] is None


def test_global_feed_spans_integrations_and_filters_by_action(client):
    a = create_integration(client, "Feed A").json()["id"]
    b = create_integration(client, "Feed B", headers=USER).json()["id"]
    client.patch(f"/api/integrations/{a}", json={"description": "x"}, headers=ADMIN)

    feed = client.get("/api/audit", headers=USER).json()
    assert feed["total"] == 3
    assert {e["integration_id"] for e in feed["items"]} == {a, b}

    created_only = client.get("/api/audit", params={"action": "created"}, headers=USER).json()
    assert created_only["total"] == 2
    assert all(e["action"] == "created" for e in created_only["items"])


def test_audit_pagination_preserves_total(client):
    iid = create_integration(client, "Paged").json()["id"]
    client.patch(f"/api/integrations/{iid}", json={"description": "one"}, headers=ADMIN)
    client.patch(f"/api/integrations/{iid}", json={"description": "two"}, headers=ADMIN)

    page = _audit(client, iid, page=1, page_size=1)
    assert page["total"] == 3
    assert len(page["items"]) == 1
    assert page["page_size"] == 1

    global_page = client.get("/api/audit", params={"page_size": 1}, headers=ADMIN).json()
    assert global_page["total"] == 3
    assert len(global_page["items"]) == 1
