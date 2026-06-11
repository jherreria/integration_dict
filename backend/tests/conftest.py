"""Shared fixtures for the backend test suite.

Environment MUST be configured before any backend module is imported so the
module-level engine in backend.database is built against a throwaway SQLite
file and auth runs in header (non-dev) mode.
"""
import os
import tempfile

_db_fd, _db_path = tempfile.mkstemp(prefix="integration_dict_test_", suffix=".sqlite")
os.close(_db_fd)
os.environ["DATABASE_URL"] = "sqlite:///" + _db_path
os.environ["DEV_MODE"] = "false"
os.environ["ADMIN_GROUPS"] = "integration-admins"

from backend.config import get_settings  # noqa: E402

get_settings.cache_clear()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import backend.auth as auth  # noqa: E402
from backend.database import engine  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models import Base  # noqa: E402

ADMIN = {
    "x-forwarded-email": "admin@example.com",
    "x-forwarded-preferred-username": "Ana Admin",
}
USER = {
    "x-forwarded-email": "user@example.com",
    "x-forwarded-preferred-username": "Uma User",
}


@pytest.fixture(autouse=True)
def fresh_db():
    """Recreate the schema for every test so state never leaks."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    auth.clear_group_cache()
    yield


@pytest.fixture(autouse=True)
def fake_group_resolution(monkeypatch):
    """Never talk to Databricks: admin@example.com is in the admin group."""

    def _resolve(email: str, obo_token: str | None = None) -> list[str]:
        if email == "admin@example.com":
            return ["integration-admins"]
        return []

    monkeypatch.setattr(auth, "resolve_groups", _resolve)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def create_integration(client, name, headers=ADMIN, **fields):
    """POST /api/integrations and return the raw response."""
    return client.post("/api/integrations", json={"name": name, **fields}, headers=headers)


@pytest.fixture(name="create_integration")
def create_integration_fixture():
    return create_integration
