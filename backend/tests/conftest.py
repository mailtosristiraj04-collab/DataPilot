import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AUTH_MODE"] = "single_user_dev"
os.environ["DEV_PRINCIPAL_ID"] = "test-user"

from app.core.config import get_settings  # noqa: E402
from app.db.base import Base
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402

get_settings.cache_clear()

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(autouse=True)
def database() -> Generator[None, None, None]:
    Base.metadata.create_all(test_engine)
    yield
    Base.metadata.drop_all(test_engine)


def override_get_db() -> Generator[Session, None, None]:
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
