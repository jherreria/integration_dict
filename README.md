# Integration Dictionary

Single source of truth for the integration inventory: what each integration is, what systems it touches, its lifecycle status, approvals, credentials metadata, and how integrations relate to each other. Built for project managers, contractors, and the integration team so questions like "what talks to the ERP?" or "who approved this design?" have one answer. Deployed as a single Databricks App (FastAPI + React).

## Features

- Searchable, filterable integration inventory with pagination
- AI semantic search via a Databricks embedding endpoint, with automatic keyword fallback (and keyword-only mode when no endpoint is configured — the UI hides the AI toggle)
- Metadata detail page with field-level RBAC (admin-only fields locked for general users)
- Relationship DAG: upstream/downstream data-flow edges plus undirected "integrated with" edges, rendered as a graph
- Full audit trail: who changed what, when, with old → new values per field, grouped per request
- Soft delete with confirmation (records retained; name freed for reuse)
- Case-insensitive unique names enforced for active integrations
- Tri-State theming (palette tokens + logo)

## Architecture

- **Backend** — FastAPI + SQLAlchemy 2.x (`backend/`). JSON API under `/api/*`, health check at `/healthz`.
- **Frontend** — React 18 + Vite SPA (TypeScript). Built to `frontend/dist` and served statically by FastAPI with a client-route fallback.
- **Database** — SQLite locally; Databricks Lakebase (managed Postgres) or any Postgres in production. Tables are created automatically on startup.
- **Identity** — Databricks Apps forwarded headers (`x-forwarded-email`); roles resolved from workspace group membership. No app-level login.

```
integration_dict/
├── app.yaml              # Databricks Apps entrypoint + env
├── requirements.txt      # backend runtime deps (+ requirements-dev.txt for tests)
├── backend/
│   ├── main.py           # FastAPI app; /api/*, /healthz, serves frontend/dist
│   ├── auth.py           # forwarded-header identity + SCIM group → role
│   ├── config.py         # settings from env / .env
│   ├── database.py       # SQLite / any-Postgres / Lakebase engine
│   ├── models.py         # SQLAlchemy models (integrations, links, audit, users)
│   ├── schemas.py        # Pydantic schemas + ADMIN_ONLY_FIELDS contract
│   ├── search.py         # keyword + embedding search, reindex
│   ├── audit.py          # field-level audit trail
│   └── routers/          # integrations, lookups, audit, search
└── frontend/
    ├── src/              # React SPA (pages, components, styles/tokens.css)
    └── public/logo.svg   # placeholder Tri-State mark — replace (see Branding)
```

## Roles & permissions

Membership in any group listed in `ADMIN_GROUPS` grants the **integration** (admin) role; every other authenticated user is **general**. The field list is served by `GET /api/me` (from `backend/schemas.py:ADMIN_ONLY_FIELDS`) so the UI never hardcodes it.

| Capability | general | integration team |
|---|---|---|
| View inventory, detail pages, graph, audit trail | yes | yes |
| Create integrations; edit most fields | yes | yes |
| Rename an integration (`name` after creation) | no | yes |
| Edit `complexity`, `business_logic` | no | yes |
| Edit approvals: `design_approved`, `design_approver_id`, `design_approval_date`, `code_approved`, `code_approver_id`, `code_approval_date` | no | yes |
| Soft-delete an integration | no | yes |

Note: approver dropdowns list known admin users — an admin appears there after their **first visit** to the app (users are upserted on first authenticated request).

## Local development

```bash
cp .env.example .env   # DEV_MODE=true fakes identity from env

uv venv .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt

.venv/bin/python -m backend.seed                  # optional demo data
.venv/bin/uvicorn backend.main:app --reload       # API on :8000

cd frontend && npm install && npm run dev         # SPA on :5173, /api proxied to :8000
```

With `DEV_MODE=true`, identity comes from `DEV_USER_EMAIL`, `DEV_USER_NAME`, and `DEV_USER_ROLE` (`integration` or `general`) instead of Databricks headers. The default database is a local SQLite file (`DATABASE_URL`).

Run tests:

```bash
.venv/bin/python -m pytest backend/tests -q
```

## Deploying to Databricks Apps

Runtime: Ubuntu 22.04, Python 3.11, default 2 vCPU / 6 GB. `app.yaml` runs `uvicorn backend.main:app` — the platform injects `UVICORN_HOST=0.0.0.0` and `UVICORN_PORT=$DATABRICKS_APP_PORT`, so no flags are needed.

1. **Create the app** (UI or `databricks apps create <name>`).
2. **Add a database resource** (Lakebase): resource key `database`, permission **Can connect and create**. The platform injects `PGHOST`/`PGPORT`/`PGUSER`/`PGDATABASE`/`PGSSLMODE`. Lakebase auth is an OAuth token used as the password (1h expiry, enforced at login only) — `backend/database.py` already mints a fresh token per new connection (`pool_recycle=600`). The Postgres role name is the app service principal's client ID.
3. **Add a serving endpoint resource** (optional, for AI search): resource key `serving-endpoint`, permission **Can query**, e.g. `databricks-gte-large-en`.
4. **Edit `app.yaml` env**: set `ADMIN_GROUPS` (account groups assigned to the workspace — Entra-synced), set `LAKEBASE_INSTANCE_NAME` to your instance name, and uncomment `EMBEDDING_ENDPOINT` (`valueFrom: "serving-endpoint"`). Leave `EMBEDDING_ENDPOINT` unset for keyword-only search.
5. **Build the frontend first** — Databricks Apps will **not** run npm:
   ```bash
   cd frontend && npm ci && npm run build
   ```
6. **Deploy with `frontend/dist` included.** `databricks sync` skips gitignored paths, so either sync with an include rule for `dist`, or temporarily remove `dist` from your ignore file before syncing; then run `databricks apps deploy`.
7. **First run creates the tables automatically** (no migration step).
8. **Verify**: open `https://<app-url>/healthz` → `{"status": "ok"}`, then load the app and check `GET /api/me` shows your role. If embeddings are enabled, hit `POST /api/search/reindex` (admin) once to backfill.

How identity works in production: Databricks Apps forwards `x-forwarded-email` (primary), `x-forwarded-preferred-username`, and `x-forwarded-access-token` (only with on-behalf-of user authorization). Group membership is resolved via the app service principal's SCIM lookup, with an OBO `/Me` fallback, and TTL-cached.

### Built-in guardrails

The app fails fast rather than mis-deploying silently:

- **Identity trust.** Roles derive from the proxy-set `x-forwarded-email` header. The app must run **only behind the Databricks Apps proxy** (or another proxy you control that sets that header) — never expose the uvicorn port directly, or a client could spoof identity.
- **`DEV_MODE` lockout.** `DEV_MODE` fakes identity and grants admin to everyone — for local dev only. The app refuses to start if `DEV_MODE` is set while Databricks Apps env markers (`DATABRICKS_CLIENT_ID`/`DATABRICKS_APP_PORT`) are present, so a stray `.env` swept into the deploy can't disable auth.
- **No accidental SQLite in prod.** If a database resource is attached (`PGHOST` injected) but `LAKEBASE_INSTANCE_NAME` is unset, the app refuses to start instead of silently falling back to an ephemeral SQLite file and losing data on restart.

## Branding

- Theme tokens live in `frontend/src/styles/tokens.css` (palette observed from tristate.coop).
- `frontend/public/logo.svg` is a placeholder rendition. Replace it with the official asset (https://tristate.coop/sites/default/files/Tri-State-Logo-Blue_lr2.png) — keep the filename `logo.svg`, or update the reference in `frontend/src/components/Header.tsx`.

## Moving off Databricks later

- **Database**: point `DATABASE_URL` at any Postgres (leave `LAKEBASE_INSTANCE_NAME` unset).
- **Auth**: put any authenticating proxy in front that sets `x-forwarded-email` (keep `DEV_MODE` off), and adapt the group resolution in `backend/auth.py` to your directory if you still want group-based roles.
- **Serving**: it's a standard ASGI app — run it under any ASGI host; the SPA is just static files in `frontend/dist`.
- **AI search**: tied to a Databricks serving endpoint; unset `EMBEDDING_ENDPOINT` for keyword-only, or swap the embed call in `backend/search.py`.

## Operational notes

- The audit table grows forever — by design; nothing prunes it.
- After enabling embeddings (or changing the endpoint), run `POST /api/search/reindex` (admin only) to embed existing rows. `GET /api/search/status` reports total/embedded/stale counts.
- SCIM group lookups are TTL-cached (`GROUP_CACHE_TTL_SECONDS`, default 300s) — role changes can take up to that long to apply.
