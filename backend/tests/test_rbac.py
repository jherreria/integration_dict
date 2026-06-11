"""Field-level RBAC: admin-only fields, diff-first PATCH, approver rules."""
from datetime import datetime, timezone

import pytest

from .conftest import ADMIN, USER, create_integration


def _me(client, headers):
    resp = client.get("/api/me", headers=headers)
    assert resp.status_code == 200
    return resp.json()


def _normalized(detail: dict) -> dict:
    """POST renders tz-aware datetimes ('...Z'); GET re-reads them naive from
    SQLite. Strip the suffix so equal instants compare equal."""
    out = dict(detail)
    for key in ("created_at", "updated_at"):
        if isinstance(out.get(key), str):
            out[key] = out[key].removesuffix("Z").removesuffix("+00:00")
    return out


# ---------------------------------------------------------------------------
# /api/me
# ---------------------------------------------------------------------------
def test_me_admin(client):
    body = _me(client, ADMIN)
    assert body["is_admin"] is True
    assert body["user"]["email"] == "admin@example.com"
    assert body["user"]["role"] == "integration"
    fields = body["admin_only_fields"]
    assert isinstance(fields, list) and fields == sorted(fields)
    assert "name" in fields and "complexity" in fields and "design_approver_id" in fields


def test_me_general(client):
    body = _me(client, USER)
    assert body["is_admin"] is False
    assert body["user"]["role"] == "general"


# ---------------------------------------------------------------------------
# general users may not change admin-only fields
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "Sneaky Rename"),
        ("complexity", "high"),
        ("business_logic", "low"),
        ("design_approved", True),
        ("design_approver_id", "deadbeefdeadbeefdeadbeefdeadbeef"),
        ("design_approval_date", "2026-01-01"),
        ("code_approved", True),
    ],
)
def test_general_patch_admin_only_field_forbidden(client, field, value):
    created = create_integration(client, "Locked Down").json()
    iid = created["id"]
    resp = client.patch(f"/api/integrations/{iid}", json={field: value}, headers=USER)
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert detail["fields"] == [field]
    # nothing was applied
    after = client.get(f"/api/integrations/{iid}", headers=USER).json()
    assert _normalized(after) == _normalized(created)


def test_general_patch_unchanged_name_with_changed_description_ok(client):
    iid = create_integration(client, "Stable Name").json()["id"]
    resp = client.patch(
        f"/api/integrations/{iid}",
        json={"name": "Stable Name", "description": "general edit"},
        headers=USER,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Stable Name"
    assert body["description"] == "general edit"


# ---------------------------------------------------------------------------
# admin rename
# ---------------------------------------------------------------------------
def test_admin_rename_works(client):
    iid = create_integration(client, "Old Name").json()["id"]
    resp = client.patch(f"/api/integrations/{iid}", json={"name": "New Name"}, headers=ADMIN)
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


def test_admin_rename_to_existing_active_name_conflicts(client):
    create_integration(client, "Taken")
    iid = create_integration(client, "Renamer").json()["id"]
    resp = client.patch(f"/api/integrations/{iid}", json={"name": "taken"}, headers=ADMIN)
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# delete / create RBAC
# ---------------------------------------------------------------------------
def test_general_delete_forbidden(client):
    iid = create_integration(client, "Protected").json()["id"]
    resp = client.delete(f"/api/integrations/{iid}", headers=USER)
    assert resp.status_code == 403
    # still there
    assert client.get(f"/api/integrations/{iid}", headers=USER).status_code == 200


def test_general_create_with_complexity_forbidden(client):
    resp = create_integration(client, "Too Fancy", headers=USER, complexity="high")
    assert resp.status_code == 403
    assert "complexity" in resp.json()["detail"]["fields"]


def test_admin_create_with_complexity_ok(client):
    resp = create_integration(client, "Fancy", headers=ADMIN, complexity="high")
    assert resp.status_code == 201
    assert resp.json()["complexity"] == "high"


# ---------------------------------------------------------------------------
# approver validation and approval defaults
# ---------------------------------------------------------------------------
def test_design_approver_must_be_integration_team(client):
    general_id = _me(client, USER)["user"]["id"]
    iid = create_integration(client, "Needs Approval").json()["id"]
    resp = client.patch(
        f"/api/integrations/{iid}", json={"design_approver_id": general_id}, headers=ADMIN
    )
    assert resp.status_code == 422


def test_design_approver_admin_user_accepted(client):
    admin_id = _me(client, ADMIN)["user"]["id"]
    iid = create_integration(client, "Approvable").json()["id"]
    resp = client.patch(
        f"/api/integrations/{iid}", json={"design_approver_id": admin_id}, headers=ADMIN
    )
    assert resp.status_code == 200
    assert resp.json()["design_approver"]["email"] == "admin@example.com"


def test_design_approved_autofills_approver_and_date(client):
    iid = create_integration(client, "Auto Approved").json()["id"]
    resp = client.patch(
        f"/api/integrations/{iid}", json={"design_approved": True}, headers=ADMIN
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["design_approved"] is True
    assert body["design_approver"]["email"] == "admin@example.com"
    assert body["design_approval_date"] == datetime.now(timezone.utc).date().isoformat()
