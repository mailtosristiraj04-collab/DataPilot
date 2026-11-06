import json
import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import Principal
from app.db.models import Dataset, DatasetMetadata, DatasetStatus
from app.ingestion.profiling import profile_dataset
from app.ingestion.storage import DatasetStorage
from app.ingestion.validation import DatasetValidationError, detect_format, read_dataset

logger = logging.getLogger(__name__)


class DatasetService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.storage = DatasetStorage(settings)

    async def create_dataset(
        self, upload: UploadFile, db: Session, principal: Principal
    ) -> Dataset:
        temporary_path: Path | None = None
        storage_key: str | None = None
        try:
            suffix = Path(upload.filename or "").suffix.lower()
            if suffix not in {".csv", ".xlsx"}:
                raise DatasetValidationError("Only CSV and XLSX files are supported")
            with tempfile.NamedTemporaryFile(
                dir=self.settings.storage_dir, prefix="upload-", suffix=".tmp", delete=False
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                total_bytes = 0
                while chunk := await upload.read(1024 * 1024):
                    total_bytes += len(chunk)
                    if total_bytes > self.settings.max_upload_size_bytes:
                        raise DatasetValidationError("The uploaded file exceeds the size limit")
                    temporary_file.write(chunk)
            file_format = detect_format(temporary_path, upload.filename or "")
            row_count, column_count, profile = profile_dataset(
                temporary_path,
                file_format,
                self.settings.max_dataset_rows,
                self.settings.max_dataset_columns,
            )
            storage_key = self.storage.create_key(f".{file_format}")
            destination = self.storage.path_for(storage_key)
            shutil.move(str(temporary_path), destination)
            temporary_path = None
            dataset = Dataset(
                owner_id=principal.principal_id,
                original_filename=upload.filename or "dataset",
                storage_key=storage_key,
                file_format=file_format,
                file_size_bytes=total_bytes,
                row_count=row_count,
                column_count=column_count,
                status=DatasetStatus.ready,
                metadata_record=DatasetMetadata(
                    columns=profile.pop("columns"),
                    profile_summary=profile,
                ),
            )
            db.add(dataset)
            db.commit()
            db.refresh(dataset)
            logger.info(
                "Dataset ingested id=%s owner=%s format=%s",
                dataset.id,
                principal.principal_id,
                file_format,
            )
            return dataset
        except Exception:
            db.rollback()
            if storage_key is not None:
                self.storage.remove(storage_key)
            raise
        finally:
            await upload.close()
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def delete_dataset(self, dataset: Dataset, db: Session) -> None:
        storage_key = dataset.storage_key
        db.delete(dataset)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        self.storage.remove(storage_key)
        logger.info("Dataset deleted id=%s", dataset.id)

    def preview(self, dataset: Dataset, offset: int, limit: int) -> list[dict]:
        path = self.storage.path_for(dataset.storage_key)
        rows = read_dataset(path, dataset.file_format).iloc[offset : offset + limit]
        return json.loads(rows.to_json(orient="records", date_format="iso"))

    def get_path(self, dataset: Dataset) -> Path:
        return self.storage.path_for(dataset.storage_key)
