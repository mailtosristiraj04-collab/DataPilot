from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.db.models import DatasetStatus


class DatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: str
    original_filename: str
    file_format: str
    file_size_bytes: int
    row_count: int | None
    column_count: int | None
    status: DatasetStatus
    created_at: datetime


class DatasetMetadataResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    columns: dict[str, dict[str, Any]]
    profile_summary: dict[str, Any]
    schema_version: int


class DatasetDetailResponse(DatasetResponse):
    metadata: DatasetMetadataResponse | None


class DatasetPreviewResponse(BaseModel):
    dataset_id: UUID
    offset: int
    limit: int
    rows: list[dict[str, Any]]
