from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.analytics.errors import AnalyticalError
from app.analytics.registry import registry
from app.analytics.schemas import AnalysisRequest, AnalysisResponse, ToolInfo
from app.analytics.service import AnalyticalService
from app.api.deps import (
    get_analytical_service,
    get_chat_service,
    get_dataset_service,
    get_owned_dataset,
)
from app.core.config import Settings, get_settings
from app.core.security import Principal, get_current_principal
from app.db.models import Dataset
from app.db.session import get_db
from app.ingestion.service import DatasetService
from app.ingestion.validation import DatasetValidationError
from app.orchestration.errors import (
    LLMConfigurationError,
    LLMExecutionError,
    OrchestrationError,
    ToolExecutionError,
)
from app.orchestration.schemas import ChatRequest, ChatResponse
from app.orchestration.service import ChatService
from app.schemas.datasets import (
    DatasetDetailResponse,
    DatasetMetadataResponse,
    DatasetPreviewResponse,
    DatasetResponse,
)
from app.schemas.health import DatabaseHealthResponse, HealthResponse

router = APIRouter(prefix="/api/v1")


def _dataset_detail(dataset: Dataset) -> DatasetDetailResponse:
    summary = DatasetResponse.model_validate(dataset)
    metadata = (
        DatasetMetadataResponse.model_validate(dataset.metadata_record)
        if dataset.metadata_record is not None
        else None
    )
    return DatasetDetailResponse(**summary.model_dump(), metadata=metadata)


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(status="ok", environment=settings.app_env)


@router.get("/health/database", response_model=DatabaseHealthResponse)
def database_health(db: Session = Depends(get_db)) -> DatabaseHealthResponse:
    db.execute(text("SELECT 1"))
    return DatabaseHealthResponse(status="ok", database="reachable")


@router.post("/datasets", response_model=DatasetDetailResponse, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
    service: DatasetService = Depends(get_dataset_service),
) -> DatasetDetailResponse:
    try:
        dataset = await service.create_dataset(file, db, principal)
    except DatasetValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _dataset_detail(dataset)


@router.get("/datasets", response_model=list[DatasetResponse])
def list_datasets(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> list[Dataset]:
    return list(
        db.scalars(
            select(Dataset)
            .where(Dataset.owner_id == principal.principal_id)
            .order_by(Dataset.created_at.desc())
        )
    )


@router.get("/datasets/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset(dataset: Dataset = Depends(get_owned_dataset)) -> DatasetDetailResponse:
    return _dataset_detail(dataset)


@router.get("/datasets/{dataset_id}/preview", response_model=DatasetPreviewResponse)
def preview_dataset(
    dataset_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=1_000),
    dataset: Dataset = Depends(get_owned_dataset),
    service: DatasetService = Depends(get_dataset_service),
    settings: Settings = Depends(get_settings),
) -> DatasetPreviewResponse:
    if limit > settings.max_preview_rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Preview limit is too large",
        )
    return DatasetPreviewResponse(
        dataset_id=dataset_id,
        offset=offset,
        limit=limit,
        rows=service.preview(dataset, offset, limit),
    )


@router.delete("/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(
    dataset: Dataset = Depends(get_owned_dataset),
    db: Session = Depends(get_db),
    service: DatasetService = Depends(get_dataset_service),
) -> None:
    service.delete_dataset(dataset, db)


@router.get("/analytics/tools", response_model=list[ToolInfo])
def list_analytical_tools() -> list[ToolInfo]:
    return registry.list()


@router.post(
    "/datasets/{dataset_id}/analytics",
    response_model=AnalysisResponse,
)
def execute_analysis(
    request: AnalysisRequest,
    dataset: Dataset = Depends(get_owned_dataset),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
    service: AnalyticalService = Depends(get_analytical_service),
) -> AnalysisResponse:
    try:
        execution_id, result = service.execute(
            dataset, request.tool_name, request.parameters, db, principal
        )
    except AnalyticalError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AnalysisResponse(
        execution_id=str(execution_id),
        tool_name=request.tool_name,
        status="succeeded",
        result=result,
    )


@router.post(
    "/datasets/{dataset_id}/chat",
    response_model=ChatResponse,
)
def chat_about_dataset(
    request: ChatRequest,
    dataset: Dataset = Depends(get_owned_dataset),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    try:
        return service.execute(dataset, request.question, request.session_id, db, principal)
    except OrchestrationError as exc:
        if isinstance(exc, LLMConfigurationError):
            code = status.HTTP_503_SERVICE_UNAVAILABLE
        elif isinstance(exc, LLMExecutionError):
            code = status.HTTP_502_BAD_GATEWAY
        elif isinstance(exc, ToolExecutionError):
            code = status.HTTP_400_BAD_REQUEST
        else:
            code = status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(exc)) from exc
