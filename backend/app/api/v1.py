from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.health import DatabaseHealthResponse, HealthResponse

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(status="ok", environment=settings.app_env)


@router.get("/health/database", response_model=DatabaseHealthResponse)
def database_health(db: Session = Depends(get_db)) -> DatabaseHealthResponse:
    db.execute(text("SELECT 1"))
    return DatabaseHealthResponse(status="ok", database="reachable")
