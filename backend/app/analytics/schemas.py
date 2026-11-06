from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnalysisRequest(BaseModel):
    tool_name: str = Field(min_length=1, max_length=128)
    parameters: dict[str, Any] = Field(default_factory=dict)


class SummaryInput(BaseModel):
    columns: list[str] | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def validate_columns(self) -> "SummaryInput":
        if self.columns is not None and len(set(self.columns)) != len(self.columns):
            raise ValueError("columns must be unique")
        return self


class MissingInput(BaseModel):
    columns: list[str] | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def validate_columns(self) -> "MissingInput":
        if self.columns is not None and len(set(self.columns)) != len(self.columns):
            raise ValueError("columns must be unique")
        return self


class DuplicateInput(BaseModel):
    preview_limit: int = Field(default=20, ge=0, le=100)


class CorrelationInput(BaseModel):
    columns: list[str] | None = Field(default=None, min_length=2, max_length=20)
    method: Literal["pearson", "spearman"] = "pearson"

    @model_validator(mode="after")
    def validate_columns(self) -> "CorrelationInput":
        if self.columns is not None and len(set(self.columns)) != len(self.columns):
            raise ValueError("columns must be unique")
        return self


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

    @model_validator(mode="after")
    def validate_columns(self) -> "SortInput":
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("columns must be unique")
        return self


class GroupByInput(BaseModel):
    group_by: list[str] = Field(min_length=1, max_length=10)
    aggregations: dict[str, Literal["count", "sum", "mean", "median", "min", "max"]] = Field(
        min_length=1, max_length=20
    )
    limit: int = Field(default=100, ge=1, le=1_000)

    @model_validator(mode="after")
    def validate_columns(self) -> "GroupByInput":
        if len(set(self.group_by)) != len(self.group_by):
            raise ValueError("group_by columns must be unique")
        return self


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

    @model_validator(mode="after")
    def validate_chart_columns(self) -> "ChartInput":
        if self.chart_type in {"bar", "line", "scatter"} and (
            self.x_column is None or self.y_column is None
        ):
            raise ValueError(f"{self.chart_type} charts require x_column and y_column")
        if self.chart_type in {"histogram", "box"} and self.x_column is None:
            raise ValueError(f"{self.chart_type} charts require x_column")
        if self.chart_type == "pie" and (self.x_column is None or self.y_column is None):
            raise ValueError("pie charts require x_column and y_column")
        return self


class NumericSummary(BaseModel):
    count: int
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    min: float | None = None
    max: float | None = None
    quartiles: dict[str, float | None]


class CategoricalSummary(BaseModel):
    unique_count: int
    most_frequent: Any = None
    frequency_distribution: dict[str, int]


class SummaryOutput(BaseModel):
    row_count: int
    column_count: int
    numeric: dict[str, NumericSummary]
    categorical: dict[str, CategoricalSummary]


class MissingValueOutput(BaseModel):
    count: int
    percentage: float


class MissingOutput(BaseModel):
    columns: dict[str, MissingValueOutput]


class DuplicateOutput(BaseModel):
    duplicate_row_count: int
    affected_row_count: int
    preview: list[dict[str, Any]]
    truncated: bool = False


class CorrelationOutput(BaseModel):
    method: Literal["pearson", "spearman"]
    columns: list[str]
    matrix: dict[str, dict[str, float | None]]
    undefined_pairs: list[dict[str, Any]] = Field(default_factory=list)


class OutlierOutput(BaseModel):
    method: Literal["iqr", "zscore"]
    column: str
    threshold: float | None
    affected_row_count: int
    rows: list[dict[str, Any]]
    lower_bound: float | None = None
    upper_bound: float | None = None
    zscore_threshold: float | None = None
    truncated: bool = False


class RowsOutput(BaseModel):
    row_count: int
    rows: list[dict[str, Any]]
    truncated: bool = False


class GroupByOutput(BaseModel):
    group_by: list[str]
    row_count: int
    rows: list[dict[str, Any]]
    truncated: bool = False


class TrendOutput(BaseModel):
    datetime_column: str
    metric_column: str
    interval: Literal["day", "week", "month", "quarter", "year"]
    rows: list[dict[str, Any]]
    truncated: bool = False


class ChartTrace(BaseModel):
    type: Literal["bar", "scatter", "histogram", "box", "pie"]
    x: list[Any] | None = None
    y: list[Any] | None = None
    labels: list[Any] | None = None
    values: list[Any] | None = None
    marker: dict[str, Any] | None = None
    mode: Literal["lines", "markers"] | None = None


class ChartLayout(BaseModel):
    title: str


class ChartSpecOutput(BaseModel):
    data: list[ChartTrace] = Field(min_length=1)
    layout: ChartLayout


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
    output_schema: dict[str, Any]
