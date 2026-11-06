import io
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import get_current_principal
from app.db.models import Dataset
from app.ingestion.service import DatasetService
from app.main import app


def upload(client: TestClient, content: bytes, filename: str) -> dict:
    response = client.post(
        "/api/v1/datasets",
        files={"file": (filename, io.BytesIO(content), "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_csv_upload_profile_list_detail_preview_and_delete(client: TestClient) -> None:
    dataset = upload(
        client,
        b"name,value\nalpha,1\nbeta,\nalpha,1\n",
        "sales.csv",
    )
    dataset_id = dataset["id"]

    assert dataset["file_format"] == "csv"
    assert dataset["row_count"] == 3
    assert dataset["column_count"] == 2
    assert dataset["metadata"]["columns"]["value"]["missing_count"] == 1
    assert dataset["metadata"]["profile_summary"]["duplicate_row_count"] == 1

    listed = client.get("/api/v1/datasets")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [dataset_id]

    detail = client.get(f"/api/v1/datasets/{dataset_id}")
    assert detail.status_code == 200
    assert detail.json()["metadata"]["columns"]["name"]["data_type"] == "object"

    preview = client.get(f"/api/v1/datasets/{dataset_id}/preview?offset=1&limit=1")
    assert preview.status_code == 200
    assert preview.json()["rows"] == [{"name": "beta", "value": None}]

    deleted = client.delete(f"/api/v1/datasets/{dataset_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/datasets/{dataset_id}").status_code == 404
    assert client.get("/api/v1/datasets").json() == []


def test_xlsx_upload(client: TestClient) -> None:
    import pandas as pd

    stream = io.BytesIO()
    pd.DataFrame({"region": ["east", "west"], "sales": [10, 20]}).to_excel(
        stream, index=False, engine="openpyxl"
    )

    dataset = upload(client, stream.getvalue(), "regions.xlsx")

    assert dataset["file_format"] == "xlsx"
    assert dataset["row_count"] == 2
    assert dataset["metadata"]["columns"]["sales"]["data_type"] == "int64"


def test_invalid_files_are_rejected(client: TestClient) -> None:
    for filename, content in (
        ("data.txt", b"name,value\nalpha,1\n"),
        ("broken.xlsx", b"not an xlsx archive"),
        ("empty.csv", b""),
        ("header-only.csv", b"name,value\n"),
    ):
        response = client.post(
            "/api/v1/datasets",
            files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
        )
        assert response.status_code == 400


def test_preview_limits_are_validated(client: TestClient) -> None:
    dataset = upload(client, b"name\nalpha\n", "data.csv")

    assert client.get(f"/api/v1/datasets/{dataset['id']}/preview?limit=0").status_code == 422
    assert client.get(f"/api/v1/datasets/{dataset['id']}/preview?limit=101").status_code == 422


def test_ownership_is_enforced(client: TestClient) -> None:
    dataset = upload(client, b"name\nalpha\n", "private.csv")
    app.dependency_overrides[get_current_principal] = lambda: type(
        "Principal", (), {"principal_id": "different-user"}
    )()

    try:
        assert client.get(f"/api/v1/datasets/{dataset['id']}").status_code == 404
        assert client.get(f"/api/v1/datasets/{dataset['id']}/preview").status_code == 404
        assert client.delete(f"/api/v1/datasets/{dataset['id']}").status_code == 404
        assert client.get("/api/v1/datasets").json() == []
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
    assert client.delete(f"/api/v1/datasets/{dataset['id']}").status_code == 204


def test_malformed_csv_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/datasets",
        files={"file": ("data.csv", io.BytesIO(b"a,b\n1,2,3\n"), "text/csv")},
    )

    assert response.status_code == 400


def test_missing_dataset_is_not_authorized(client: TestClient) -> None:
    assert client.get(f"/api/v1/datasets/{uuid4()}").status_code == 404


def test_oversized_upload_is_rejected(client: TestClient) -> None:
    settings = get_settings()
    original_limit = settings.max_upload_size_bytes
    settings.max_upload_size_bytes = 4
    try:
        response = client.post(
            "/api/v1/datasets",
            files={"file": ("data.csv", io.BytesIO(b"name\nalpha\n"), "text/csv")},
        )
    finally:
        settings.max_upload_size_bytes = original_limit

    assert response.status_code == 400
    assert client.get("/api/v1/datasets").json() == []


async def _failing_upload(service: DatasetService) -> None:
    from fastapi import UploadFile

    class FailingSession:
        def add(self, dataset: Dataset) -> None:
            pass

        def commit(self) -> None:
            raise RuntimeError("database failure")

        def rollback(self) -> None:
            pass

    upload_file = UploadFile(file=io.BytesIO(b"name\nalpha\n"), filename="data.csv")
    try:
        await service.create_dataset(
            upload_file,
            FailingSession(),
            type("Principal", (), {"principal_id": "test-user"})(),
        )
    except RuntimeError:
        pass


def test_database_failure_cleans_up_stored_file() -> None:
    import asyncio

    service = DatasetService(get_settings())
    existing_files = set(Path(get_settings().storage_dir).glob("*.csv"))
    asyncio.run(_failing_upload(service))
    assert set(Path(get_settings().storage_dir).glob("*.csv")) == existing_files
