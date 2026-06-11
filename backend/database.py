"""Engine/session factory. Supports SQLite (dev), any SQLAlchemy URL, and
Databricks Lakebase (managed Postgres) with rotating token credentials."""
import os
import uuid

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from .config import Settings, get_settings


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        # SQLite does not enforce foreign keys unless asked, per connection.
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        # SQLite's built-in lower() is ASCII-only; override with Python's
        # Unicode-aware lower so case-insensitive uniqueness/filtering behaves
        # identically to Postgres. Must be deterministic to back the expression
        # indexes (uq_*_name_lower).
        dbapi_conn.create_function(
            "lower", 1, lambda s: s.lower() if s is not None else None, deterministic=True
        )


def _create_lakebase_engine(settings: Settings) -> Engine:
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    # Inside a Databricks App with a database resource attached, the platform
    # injects standard libpq env vars (PGHOST/PGPORT/PGUSER/PGDATABASE).
    host = os.getenv("PGHOST")
    if not host:
        instance = w.database.get_database_instance(name=settings.lakebase_instance_name)
        host = instance.read_write_dns
    port = int(os.getenv("PGPORT", "5432"))
    dbname = os.getenv("PGDATABASE") or settings.lakebase_database
    user = os.getenv("PGUSER") or settings.lakebase_user or w.config.client_id
    if not user:
        raise RuntimeError(
            "Could not determine the Lakebase Postgres user. Inside a Databricks "
            "App this is injected (PGUSER); when connecting from elsewhere with a "
            "PAT/CLI profile, set LAKEBASE_USER to your Databricks identity."
        )

    def creator():
        import psycopg2

        # Lakebase auth is OAuth-token-as-password; tokens last ~1 hour and
        # expiry is enforced only at login, so each new physical connection
        # gets a fresh token.
        cred = w.database.generate_database_credential(
            request_id=str(uuid.uuid4()),
            instance_names=[settings.lakebase_instance_name],
        )
        return psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=cred.token,
            sslmode="require",
        )

    return create_engine(
        "postgresql+psycopg2://",
        creator=creator,
        pool_pre_ping=True,
        pool_recycle=600,
    )


def build_engine(settings: Settings | None = None) -> Engine:
    settings = settings or get_settings()
    if settings.lakebase_instance_name:
        return _create_lakebase_engine(settings)
    # A Databricks Apps database resource injects PGHOST. If it is present but
    # no Lakebase instance is configured, we would silently fall back to an
    # ephemeral SQLite file and lose all data on the next restart — fail loudly.
    if os.getenv("PGHOST"):
        raise RuntimeError(
            "A database resource is attached (PGHOST is set) but "
            "LAKEBASE_INSTANCE_NAME is not configured. Set it in app.yaml so the "
            "app connects to Lakebase instead of ephemeral local SQLite."
        )
    kwargs: dict = {"pool_pre_ping": True}
    if settings.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(settings.database_url, **kwargs)
    if engine.dialect.name == "sqlite":
        _configure_sqlite(engine)
    return engine


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
