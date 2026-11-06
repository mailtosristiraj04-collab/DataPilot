from uuid import uuid4

import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.analytics.errors import AnalyticalError
from app.analytics.registry import registry
from app.analytics.service import AnalyticalService
from app.core.config import ROOT_ENV_FILE, Settings
from app.core.security import Principal
from app.db.models import AnalyticalExecution, Dataset, ExecutionStatus


@pytest.mark.integration
def test_unexpected_failure_is_durable_on_postgresql(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = dotenv_values(ROOT_ENV_FILE).get("DATABASE_URL")
    if not database_url:
        pytest.skip("PostgreSQL integration test requires DATABASE_URL in the project .env")
    settings = Settings(database_url=database_url)
    engine = create_engine(settings.database_url)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.skip("PostgreSQL integration test requires the configured PostgreSQL database")
    owner_id = f"phase4-test-{uuid4()}"
    with Session(engine) as db:
        dataset = Dataset(
            owner_id=owner_id,
            original_filename="phase4-failure.csv",
            storage_key=f"phase4/{uuid4()}.csv",
            file_format="csv",
            file_size_bytes=1,
        )
        db.add(dataset)
        db.commit()
        dataset_id = dataset.id
        monkeypatch.setattr(
            "app.analytics.service.read_dataset",
            lambda path, file_format: (_ for _ in ()).throw(RuntimeError("read failure")),
        )
        try:
            with pytest.raises(AnalyticalError):
                AnalyticalService(settings, registry).execute(
                    dataset,
                    "get_summary_statistics",
                    {},
                    db,
                    Principal(owner_id),
                )
            execution = db.scalar(
                select(AnalyticalExecution).where(
                    AnalyticalExecution.dataset_id == dataset_id
                )
            )
            assert execution is not None
            assert execution.status is ExecutionStatus.failed
            assert execution.error_details == {
                "message": "The analytical operation could not be completed"
            }
        finally:
            db.query(AnalyticalExecution).filter(
                AnalyticalExecution.dataset_id == dataset_id
            ).delete()
            db.query(Dataset).filter(Dataset.id == dataset_id).delete()
            db.commit()
    engine.dispose()
