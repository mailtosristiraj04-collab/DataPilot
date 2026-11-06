from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnalysisRequest(BaseModel):
    tool_name: str = Field(min_length=1, max_length=128)
    parameters: dict[str, Any] = Field(default_factory=dict)


class SummaryInput(BaseModel):
    columns: list[str] | None = None


class MissingInput(BaseModel):
    columns: list[str] | None = None


class DuplicateInput(BaseModel):
    preview_limit: int = Field(default=20, ge=0, le=100)


class CorrelationInput(BaseModel):
    columns: list[str] | None = None
    method: Literal["pearson", "spearman"] = "pearson"


class OutlierInput(BaseModel):
    column: str
    method: Literal["iqr", "zscore"] = "iqr"
    threshold: float | None = Field(default=None, gt=0)


class FilterCondition(BaseModel):
    column: str
    operator: Literal[
        "eq",
        "ne",
        "gt",
        "gte",
        "lt",
        "lte",
        "contains",
        "starts_with",
        "ends_with",
        "is_null",
        "is_not_null",
    ]
    value: Any = None

    @model_validator(mode="after")
    def validate_value(self) -> "FilterCondition":
        if self.operator in {"is_null", "is_not_null"} and self.value is not None:
            raise ValueError("Null-check operators do not accept a value")
        if self.operator not in {"is_null", "is_not_null"} and self.value is None:
            raise ValueError("This operator requires a value")
        return self


class FilterInput(BaseModel):
    conditions: list[FilterCondition] = Field(min_length=1, max_length=10)
    limit: int = Field(default=100, ge=1, le=1_000)


class SortInput(BaseModel):
    columns: list[str] = Field(min_length=1, max_length=10)
    direction: Literal["asc", "desc"] = "asc"
    limit: int = Field(default=100, ge=1, le=1_000)


class GroupByInput(BaseModel):
    group_by: list[str] = Field(min_length=1, max_length=10)
    aggregations: dict[str, Literal["count", "sum", "mean", "median", "min", "max"]]
    limit: int = Field(default=100, ge=1, le=1_000)


class TrendInput(BaseModel):
    datetime_column: str
    metric_column: str
    interval: Literal["day", "week", "month", "quarter", "year"] = "month"


class ChartInput(BaseModel):
    chart_type: Literal["bar", "line", "scatter", "histogram", "box", "pie"]
    x_column: str | None = None
    y_column: str | None = None
    color_column: str | None = None
    limit: int = Field(default=500, ge=1, le=2_000)


class AnalysisResponse(BaseModel):
    execution_id: str
    tool_name: str
    status: Literal["succeeded"]
    result: dict[str, Any]


class ToolInfo(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    input_schema: dict[str, Any]
