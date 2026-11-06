import io
import json
from uuid import UUID

import numpy as np
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
from app.analytics.service import AnalyticalService
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


@pytest.mark.parametrize(
    ("chart_type", "parameters"),
    [
        ("bar", {"x_column": "category", "y_column": "value"}),
        ("line", {"x_column": "date", "y_column": "value"}),
        ("scatter", {"x_column": "value", "y_column": "other"}),
        ("histogram", {"x_column": "value"}),
        ("box", {"x_column": "value"}),
        ("pie", {"x_column": "category", "y_column": "value"}),
    ],
)
def test_all_chart_types_have_valid_specs(
    dataframe: pd.DataFrame, chart_type: str, parameters: dict[str, str]
) -> None:
    result = registry.execute(
        "generate_chart", dataframe, {"chart_type": chart_type, **parameters}
    )
    assert len(result["data"]) == 1
    assert result["data"][0]["type"] == ("scatter" if chart_type == "line" else chart_type)
    assert result["layout"]["title"]
    if chart_type == "line":
        assert result["data"][0]["mode"] == "lines"
    if chart_type == "pie":
        assert result["data"][0]["labels"] and result["data"][0]["values"]


def test_registry_validates_every_registered_output(dataframe: pd.DataFrame) -> None:
    parameters = {
        "get_summary_statistics": {},
        "get_missing_values": {},
        "detect_duplicates": {},
        "get_correlation": {"columns": ["value", "other"]},
        "detect_outliers": {"column": "value"},
        "filter_dataset": {
            "conditions": [{"column": "category", "operator": "eq", "value": "a"}]
        },
        "sort_dataset": {"columns": ["value"]},
        "group_by_analysis": {"group_by": ["category"], "aggregations": {"value": "sum"}},
        "get_time_trends": {
            "datetime_column": "date",
            "metric_column": "value",
        },
        "generate_chart": {
            "chart_type": "scatter",
            "x_column": "value",
            "y_column": "other",
        },
    }
    for tool_name, tool_parameters in parameters.items():
        result = registry.execute(tool_name, dataframe, tool_parameters)
        assert isinstance(result, dict)
        json.dumps(result)


def test_correlation_reports_undefined_pairs() -> None:
    result = registry.execute(
        "get_correlation",
        pd.DataFrame({"constant": [1, 1, 1], "empty": [np.nan, np.nan, np.nan]}),
        {"columns": ["constant", "empty"], "method": "spearman"},
    )
    assert {item["reason"] for item in result["undefined_pairs"]} == {
        "insufficient observations"
    }


def test_all_null_numeric_and_constant_zscore_are_explicit() -> None:
    dataframe = pd.DataFrame({"empty": [np.nan, np.nan], "constant": [4.0, 4.0]})
    summary = registry.execute("get_summary_statistics", dataframe, {})
    assert summary["numeric"]["empty"]["count"] == 0
    assert summary["numeric"]["empty"]["mean"] is None
    outliers = registry.execute(
        "detect_outliers", dataframe, {"column": "constant", "method": "zscore"}
    )
    assert outliers["affected_row_count"] == 0


def test_contains_is_literal_and_sorting_puts_nulls_last() -> None:
    dataframe = pd.DataFrame({"text": ["a.b", "axb", None], "value": [1, None, 2]})
    filtered = registry.execute(
        "filter_dataset",
        dataframe,
        {"conditions": [{"column": "text", "operator": "contains", "value": "."}]},
    )
    assert [row["text"] for row in filtered["rows"]] == ["a.b"]
    sorted_result = registry.execute("sort_dataset", dataframe, {"columns": ["value"]})
    assert [row["value"] for row in sorted_result["rows"]] == [1.0, 2.0, None]


def test_trends_normalize_timezone_aware_datetimes(dataframe: pd.DataFrame) -> None:
    dataframe["date"] = [
        "2024-01-31T23:00:00-02:00",
        "2024-02-01T01:00:00+00:00",
        "2024-03-01T00:00:00Z",
        "not-a-date",
    ]
    result = registry.execute(
        "get_time_trends",
        dataframe,
        {"datetime_column": "date", "metric_column": "value", "interval": "month"},
    )
    assert result["rows"][0]["_date"].startswith("2024-02")
    assert sum(row["count"] for row in result["rows"]) == 3


def test_chart_schema_rejects_missing_required_columns() -> None:
    with pytest.raises(ValueError):
        ChartInput(chart_type="pie", x_column="category")


def test_direct_and_registry_column_errors_are_analytical(dataframe: pd.DataFrame) -> None:
    with pytest.raises(AnalyticalError):
        get_summary_statistics(dataframe, SummaryInput(columns=["missing"]))
    with pytest.raises(AnalyticalError):
        registry.execute("get_summary_statistics", dataframe, {"columns": ["missing"]})


def test_unexpected_failures_persist_failed_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings
    from app.core.security import Principal
    from app.db.models import AnalyticalExecution, Dataset, ExecutionStatus
    from tests.conftest import TestSessionLocal

    class FailingRegistry:
        def execute(
            self, name: str, dataframe: pd.DataFrame, parameters: dict[str, object]
        ) -> dict[str, object]:
            raise RuntimeError("simulated failure")

    monkeypatch.setattr(
        "app.analytics.service.read_dataset",
        lambda path, file_format: (_ for _ in ()).throw(RuntimeError("read failure")),
    )
    with TestSessionLocal() as db:
        dataset = Dataset(
            owner_id="test-user",
            original_filename="failure.csv",
            storage_key="failure.csv",
            file_format="csv",
            file_size_bytes=1,
        )
        db.add(dataset)
        db.commit()
        service = AnalyticalService(get_settings(), FailingRegistry())
        with pytest.raises(AnalyticalError):
            service.execute(
                dataset,
                "get_summary_statistics",
                {},
                db,
                Principal("test-user"),
            )
        execution = db.query(AnalyticalExecution).one()
        assert execution.status is ExecutionStatus.failed
        assert execution.error_details == {
            "message": "The analytical operation could not be completed"
        }


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
