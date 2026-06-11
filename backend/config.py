"""Application settings loaded from environment variables / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Integration Dictionary"

    # --- database ---------------------------------------------------------
    database_url: str = "sqlite:///./integration_dict.db"
    # When set, connect to this Databricks Lakebase (managed Postgres)
    # instance instead of database_url.
    lakebase_instance_name: str | None = None
    lakebase_database: str = "databricks_postgres"
    lakebase_user: str | None = None  # defaults to the app's client id

    # --- Databricks workspace (injected automatically in Databricks Apps) --
    databricks_host: str | None = None
    databricks_client_id: str | None = None
    databricks_client_secret: str | None = None

    # --- AI search ----------------------------------------------------------
    # Name of a Databricks model serving endpoint that returns embeddings
    # (e.g. "databricks-gte-large-en"). Unset = keyword search only.
    embedding_endpoint: str | None = None

    # --- access control ------------------------------------------------------
    # Comma-separated group names granting the "integration" (admin) role.
    admin_groups: str = "integration-admins"
    group_cache_ttl_seconds: int = 300

    # --- local development -----------------------------------------------
    dev_mode: bool = False
    dev_user_email: str = "dev.user@example.com"
    dev_user_name: str = "Dev User"
    dev_user_role: str = "integration"

    @property
    def admin_group_set(self) -> set[str]:
        return {g.strip().lower() for g in self.admin_groups.split(",") if g.strip()}

    @property
    def workspace_host(self) -> str | None:
        if not self.databricks_host:
            return None
        host = self.databricks_host.rstrip("/")
        if not host.startswith("http"):
            host = f"https://{host}"
        return host


@lru_cache
def get_settings() -> Settings:
    return Settings()
