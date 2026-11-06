import io
from uuid import UUID

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.analytics.errors import AnalyticalError
from app.analytics.registry import registry
from app.analytics.schemas import (
    ChartInput,
    CorrelationInput,
    DuplicateInput,
    FilterCondition,
    FilterInput,
    GroupByInput,
    OutlierInput,
    SummaryInput,
    TrendInput,
)
from app.analytics.tools import (
    detect_duplicates,
    detect_outliers,
    filter_dataset,
    generate_chart,
    get_correlation,
    get_summary_statistics,
    get_time_trends,
    group_by_analysis,
)


@pytest.fixture
def dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-02-01", "2024-03-01", "2024-03-01"],
            "category": ["a", "a", "b", "b"],
            "value": [1.0, 2.0, 100.0, 100.0],
            "other": [2.0, 4.0, 200.0, 200.0],
        }
    )


def test_summary_quality_and_duplicates(dataframe: pd.DataFrame) -> None:
    summary = get_summary_statistics(dataframe, SummaryInput())
    assert summary["numeric"]["value"]["mean"] == pytest.approx(50.75)
    assert summary["categorical"]["category"]["unique_count"] == 2
    assert summary["row_count"] == 4
    assert (
        detect_duplicates(dataframe, DuplicateInput(preview_limit=10))["duplicate_row_count"] == 1
    )


def test_correlation_and_outliers(dataframe: pd.DataFrame) -> None:
    correlation = get_correlation(
        dataframe, CorrelationInput(columns=["value", "other"], method="pearson")
    )
    assert correlation["matrix"]["value"]["other"] == pytest.approx(1.0)
    outliers = detect_outliers(dataframe, OutlierInput(column="value", method="iqr"))
    assert outliers["affected_row_count"] == 0

    extreme = dataframe.copy()
    extreme.loc[len(extreme)] = ["2024-04-01", "c", 1_000.0, 2_000.0]
    assert detect_outliers(extreme, OutlierInput(column="value"))["affected_row_count"] == 1


def test_filter_sort_group_and_trend(dataframe: pd.DataFrame) -> None:
    filtered = filter_dataset(
        dataframe,
        FilterInput(conditions=[FilterCondition(column="category", operator="eq", value="a")]),
    )
    assert filtered["row_count"] == 2
    grouped = group_by_analysis(
        dataframe,
        GroupByInput(group_by=["category"], aggregations={"value": "sum"}),
    )
    assert {row["value_sum"] for row in grouped["rows"]} == {3.0, 200.0}
    trend = get_time_trends(
        dataframe, TrendInput(datetime_column="date", metric_column="value", interval="month")
    )
    assert len(trend["rows"]) == 3


def test_missing_values_and_chart_spec(dataframe: pd.DataFrame) -> None:
    dataframe.loc[0, "value"] = None
    missing = registry.execute("get_missing_values", dataframe, {"columns": ["value"]})
    assert missing["columns"]["value"]["count"] == 1
    assert missing["columns"]["value"]["percentage"] == 25.0
    chart = generate_chart(
        dataframe,
        ChartInput(chart_type="scatter", x_column="category", y_column="other"),
    )
    assert chart["data"][0]["type"] == "scatter"
    assert "x" in chart["data"][0] and "y" in chart["data"][0]


def test_edge_cases_are_controlled(dataframe: pd.DataFrame) -> None:
    with pytest.raises(AnalyticalError):
        registry.execute(
            "get_correlation",
            pd.DataFrame({"constant": [1, 1], "text": ["a", "b"]}),
            {"columns": ["constant", "text"]},
        )
    with pytest.raises(AnalyticalError):
        registry.execute(
            "get_time_trends",
            pd.DataFrame({"date": ["not-a-date"], "value": [1]}),
            {"datetime_column": "date", "metric_column": "value"},
        )


def test_registry_rejects_unknown_tool_and_bad_columns(dataframe: pd.DataFrame) -> None:
    with pytest.raises(AnalyticalError):
        registry.execute("not_a_tool", dataframe, {})
    with pytest.raises(AnalyticalError):
        registry.execute("get_summary_statistics", dataframe, {"columns": ["missing"]})


def test_analytics_api_and_ownership(client: TestClient) -> None:
    upload = client.post(
        "/api/v1/datasets",
        files={"file": ("analytics.csv", io.BytesIO(b"category,value\na,1\nb,2\n"), "text/csv")},
    )
    dataset_id = upload.json()["id"]
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/analytics",
        json={
            "tool_name": "get_summary_statistics",
            "parameters": {"columns": ["value"]},
        },
    )
    assert response.status_code == 200
    assert response.json()["result"]["numeric"]["value"]["mean"] == 1.5
    assert (
        client.post(
            f"/api/v1/datasets/{dataset_id}/analytics",
            json={"tool_name": "unknown", "parameters": {}},
        ).status_code
        == 400
    )
    from sqlalchemy import select

    from app.db.models import AnalyticalExecution
    from tests.conftest import TestSessionLocal

    with TestSessionLocal() as db:
        execution = db.scalar(
            select(AnalyticalExecution).where(
                AnalyticalExecution.dataset_id == UUID(dataset_id)
            )
        )
        assert execution is not None
        assert execution.status.value == "succeeded"
    assert client.delete(f"/api/v1/datasets/{dataset_id}").status_code == 204
