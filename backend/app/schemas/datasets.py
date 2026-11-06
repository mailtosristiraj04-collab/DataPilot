from datetime import datetime
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
