"""Search admin endpoints: embedding/index status and manual reindex."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..auth import CurrentUser, get_current_user, require_admin
from ..database import get_db
from ..search import reindex, search_status

router = APIRouter(tags=["search"])


@router.get("/search/status", response_model=schemas.SearchStatusOut)
def get_search_status(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> schemas.SearchStatusOut:
    return schemas.SearchStatusOut(**search_status(db))


@router.post("/search/reindex", response_model=schemas.ReindexOut)
def post_search_reindex(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_admin),
) -> schemas.ReindexOut:
    indexed, failed = reindex(db)
    return schemas.ReindexOut(indexed=indexed, failed=failed)
