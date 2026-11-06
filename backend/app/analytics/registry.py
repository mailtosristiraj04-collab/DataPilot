from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd
from pydantic import BaseModel, ValidationError

from app.analytics import tools
from app.analytics.errors import AnalyticalError
from app.analytics.schemas import (
    ChartInput,
    ChartSpecOutput,
    CorrelationInput,
    CorrelationOutput,
    DuplicateInput,
    DuplicateOutput,
    FilterInput,
    GroupByInput,
    GroupByOutput,
    MissingInput,
    MissingOutput,
    OutlierInput,
    OutlierOutput,
    RowsOutput,
    SortInput,
    SummaryInput,
    SummaryOutput,
    ToolInfo,
    TrendInput,
    TrendOutput,
)
from app.analytics.utils import json_safe


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    implementation: Callable[[pd.DataFrame, Any], dict[str, Any]]

    def info(self) -> ToolInfo:
        return ToolInfo(
            name=self.name,
            description=self.description,
            input_schema=self.input_model.model_json_schema(),
            output_schema=self.output_model.model_json_schema(),
        )


class ToolRegistry:
    def __init__(self) -> None:
        self._tools = {
            definition.name: definition
            for definition in (
                ToolDefinition(
                    "get_summary_statistics",
                    "Summarize numeric and categorical columns.",
                    SummaryInput,
                    SummaryOutput,
                    tools.get_summary_statistics,
                ),
                ToolDefinition(
                    "get_missing_values",
                    "Count missing values per column.",
                    MissingInput,
                    MissingOutput,
                    tools.get_missing_values,
                ),
                ToolDefinition(
                    "detect_duplicates",
                    "Detect duplicate rows and return a bounded preview.",
                    DuplicateInput,
                    DuplicateOutput,
                    tools.detect_duplicates,
                ),
                ToolDefinition(
                    "get_correlation",
                    "Calculate Pearson or Spearman correlations.",
                    CorrelationInput,
                    CorrelationOutput,
                    tools.get_correlation,
                ),
                ToolDefinition(
                    "detect_outliers",
                    "Detect numeric outliers using IQR or Z-score.",
                    OutlierInput,
                    OutlierOutput,
                    tools.detect_outliers,
                ),
                ToolDefinition(
                    "filter_dataset",
                    "Filter rows with allow-listed operators.",
                    FilterInput,
                    RowsOutput,
                    tools.filter_dataset,
                ),
                ToolDefinition(
                    "sort_dataset",
                    "Sort rows by validated columns.",
                    SortInput,
                    RowsOutput,
                    tools.sort_dataset,
                ),
                ToolDefinition(
                    "group_by_analysis",
                    "Group rows with allow-listed aggregations.",
                    GroupByInput,
                    GroupByOutput,
                    tools.group_by_analysis,
                ),
                ToolDefinition(
                    "get_time_trends",
                    "Aggregate a numeric metric over time.",
                    TrendInput,
                    TrendOutput,
                    tools.get_time_trends,
                ),
                ToolDefinition(
                    "generate_chart",
                    "Generate a Plotly-compatible chart specification.",
                    ChartInput,
                    ChartSpecOutput,
                    tools.generate_chart,
                ),
            )
        }

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise AnalyticalError(f"Unknown analytical tool: {name}") from exc

    def list(self) -> list[ToolInfo]:
        return [definition.info() for definition in self._tools.values()]

    def execute(
        self, name: str, dataframe: pd.DataFrame, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        definition = self.get(name)
        try:
            inputs = definition.input_model.model_validate(parameters)
        except ValidationError as exc:
            raise AnalyticalError("Invalid analytical tool parameters") from exc
        try:
            result = definition.implementation(dataframe, inputs)
        except AnalyticalError:
            raise
        except Exception as exc:
            raise AnalyticalError("The analytical operation could not be completed") from exc
        try:
            return definition.output_model.model_validate(json_safe(result)).model_dump(mode="json")
        except Exception as exc:
            raise AnalyticalError("The analytical operation returned an invalid result") from exc


registry = ToolRegistry()
