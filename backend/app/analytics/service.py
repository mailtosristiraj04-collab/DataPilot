import json
import logging
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.analytics.errors import AnalyticalError
from app.analytics.registry import ToolRegistry
from app.core.config import Settings
from app.core.security import Principal
from app.db.models import AnalyticalExecution, Dataset, ExecutionStatus
from app.ingestion.service import DatasetService
from app.ingestion.validation import read_dataset

logger = logging.getLogger(__name__)


class AnalyticalService:
    def __init__(self, settings: Settings, registry: ToolRegistry) -> None:
        self.dataset_service = DatasetService(settings)
        self.registry = registry

    def execute(
        self,
        dataset: Dataset,
        request_name: str,
        parameters: dict[str, Any],
        db: Session,
        principal: Principal,
    ) -> tuple[UUID, dict[str, Any]]:
        started = perf_counter()
        execution = AnalyticalExecution(
            owner_id=principal.principal_id,
            dataset_id=dataset.id,
            operation_name=request_name,
            arguments=parameters,
            status=ExecutionStatus.running,
        )
        db.add(execution)
        db.flush()
        try:
            dataframe = read_dataset(self.dataset_service.get_path(dataset), dataset.file_format)
            result = self.registry.execute(request_name, dataframe, parameters)
            execution.status = ExecutionStatus.succeeded
            execution.result = (
                result
                if len(json.dumps(result)) <= 100_000
                else {
                    "truncated": True,
                    "keys": list(result),
                }
            )
            execution.duration_ms = int((perf_counter() - started) * 1000)
            db.commit()
            logger.info(
                "Analytical execution succeeded id=%s dataset=%s tool=%s",
                execution.id,
                dataset.id,
                request_name,
            )
            return execution.id, result
        except AnalyticalError as exc:
            execution.status = ExecutionStatus.failed
            execution.error_details = {"message": str(exc)}
            execution.duration_ms = int((perf_counter() - started) * 1000)
            db.commit()
            raise
        except Exception:
            db.rollback()
            logger.exception(
                "Analytical execution failed dataset=%s tool=%s",
                dataset.id,
                request_name,
            )
            raise AnalyticalError("The analytical operation could not be completed")
