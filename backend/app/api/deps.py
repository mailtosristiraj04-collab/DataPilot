from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_current_principal
from app.db.models import Dataset
from app.db.session import get_db
from app.ingestion.service import DatasetService


def get_owned_dataset(
    dataset_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> Dataset:
    dataset = db.scalar(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.owner_id == principal.principal_id)
    )
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return dataset


def get_dataset_service(settings: Settings = Depends(get_settings)) -> DatasetService:
    return DatasetService(settings)
