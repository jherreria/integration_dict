"""Integration Dictionary — FastAPI app.

Serves the JSON API under /api/* and, when frontend/dist exists (built with
`npm run build`), the React SPA with a client-route fallback.
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import CurrentUser, get_current_user
from .config import get_settings
from .database import engine
from .models import Base
from .routers import audit as audit_routes
from .routers import comments as comment_routes
from .routers import integrations as integration_routes
from .routers import lookups as lookup_routes
from .routers import search as search_routes
from .schemas import ADMIN_ONLY_FIELDS, MeOut, UserOut


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DEV_MODE fakes identity and grants admin to every request; never let it
    # run on Databricks Apps (markers injected by the platform). Guards against
    # a stray .env being swept into the deploy.
    if get_settings().dev_mode and (os.getenv("DATABRICKS_APP_PORT") or os.getenv("DATABRICKS_CLIENT_ID")):
        raise RuntimeError(
            "DEV_MODE is enabled but Databricks Apps environment was detected. "
            "Remove DEV_MODE from the deployed configuration — it disables authentication."
        )
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Integration Dictionary", lifespan=lifespan)

if get_settings().dev_mode:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(integration_routes.router, prefix="/api")
app.include_router(lookup_routes.router, prefix="/api")
app.include_router(audit_routes.router, prefix="/api")
app.include_router(search_routes.router, prefix="/api")
app.include_router(comment_routes.router, prefix="/api")


@app.get("/api/me", response_model=MeOut)
def me(user: CurrentUser = Depends(get_current_user)) -> MeOut:
    return MeOut(
        user=UserOut(id=user.id, email=user.email, display_name=user.display_name, role=user.role.value),
        is_admin=user.is_admin,
        admin_only_fields=sorted(ADMIN_ONLY_FIELDS),
    )


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"status": "ok"}


_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if _DIST.is_dir():
    if (_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        # An unmatched /api/* GET is a missing endpoint, not a client route —
        # return JSON 404 instead of the SPA shell (which would look like a
        # session-expiry to the client).
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (_DIST / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(_DIST):
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html", headers={"Cache-Control": "no-cache"})
