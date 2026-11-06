
from app.db.base import Base


def test_phase_two_tables_are_present() -> None:
    expected = {
        "datasets",
        "dataset_metadata",
        "analysis_sessions",
        "conversation_messages",
        "analytical_executions",
        "analysis_jobs",
    }

    assert expected.issubset(Base.metadata.tables)


def test_owned_resource_columns_are_indexed() -> None:
    for table_name in ("datasets", "analysis_sessions", "analysis_jobs", "analytical_executions"):
        table = Base.metadata.tables[table_name]
        assert any(index.name == f"ix_{table_name}_owner_id" for index in table.indexes)
