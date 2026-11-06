from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from app.analytics.errors import AnalyticalError
from app.analytics.schemas import (
    ChartInput,
    CorrelationInput,
    DuplicateInput,
    FilterInput,
    GroupByInput,
    MissingInput,
    OutlierInput,
    SortInput,
    SummaryInput,
    TrendInput,
)
from app.analytics.utils import ensure_columns, json_safe, records


def get_summary_statistics(dataframe: pd.DataFrame, inputs: SummaryInput) -> dict[str, Any]:
    columns = inputs.columns or list(dataframe.columns)
    ensure_columns(dataframe, columns)
    numeric: dict[str, Any] = {}
    categorical: dict[str, Any] = {}
    for column in columns:
        series = dataframe[column]
        if pd.api.types.is_numeric_dtype(series):
            values = series.dropna()
            numeric[column] = {
                "count": int(values.count()),
                "mean": values.mean(),
                "median": values.median(),
                "std": values.std(),
                "min": values.min(),
                "max": values.max(),
                "quartiles": {
                    "q1": values.quantile(0.25),
                    "q2": values.quantile(0.5),
                    "q3": values.quantile(0.75),
                },
            }
        else:
            counts = series.value_counts(dropna=False)
            categorical[column] = {
                "unique_count": int(series.nunique(dropna=True)),
                "most_frequent": json_safe(counts.index[0]) if not counts.empty else None,
                "frequency_distribution": {
                    str(json_safe(key)): int(value) for key, value in counts.items()
                },
            }
    return json_safe(
        {
            "row_count": len(dataframe),
            "column_count": len(dataframe.columns),
            "numeric": numeric,
            "categorical": categorical,
        }
    )


def get_missing_values(dataframe: pd.DataFrame, inputs: MissingInput) -> dict[str, Any]:
    columns = inputs.columns or list(dataframe.columns)
    ensure_columns(dataframe, columns)
    result = {}
    for column in columns:
        count = int(dataframe[column].isna().sum())
        result[column] = {
            "count": count,
            "percentage": count / len(dataframe) * 100 if len(dataframe) else 0,
        }
    return {"columns": result}


def detect_duplicates(dataframe: pd.DataFrame, inputs: DuplicateInput) -> dict[str, Any]:
    duplicate_mask = dataframe.duplicated(keep=False)
    preview = dataframe.loc[duplicate_mask].head(inputs.preview_limit)
    return {
        "duplicate_row_count": int(dataframe.duplicated().sum()),
        "affected_row_count": int(duplicate_mask.sum()),
        "preview": records(preview),
    }


def get_correlation(dataframe: pd.DataFrame, inputs: CorrelationInput) -> dict[str, Any]:
    columns = inputs.columns or list(dataframe.select_dtypes(include=np.number).columns)
    ensure_columns(dataframe, columns)
    if len(columns) < 2:
        raise AnalyticalError("At least two numeric columns are required")
    non_numeric = [
        column for column in columns if not pd.api.types.is_numeric_dtype(dataframe[column])
    ]
    if non_numeric:
        raise AnalyticalError(f"Correlation requires numeric columns: {', '.join(non_numeric)}")
    matrix = dataframe[columns].corr(method=inputs.method)
    return {"method": inputs.method, "columns": columns, "matrix": json_safe(matrix.to_dict())}


def detect_outliers(dataframe: pd.DataFrame, inputs: OutlierInput) -> dict[str, Any]:
    ensure_columns(dataframe, [inputs.column])
    if not pd.api.types.is_numeric_dtype(dataframe[inputs.column]):
        raise AnalyticalError("Outlier detection requires a numeric column")
    series = dataframe[inputs.column]
    values = series.dropna()
    if values.empty:
        return {
            "method": inputs.method,
            "column": inputs.column,
            "threshold": None,
            "affected_row_count": 0,
            "rows": [],
        }
    if inputs.method == "iqr":
        q1, q3 = values.quantile([0.25, 0.75])
        iqr = q3 - q1
        threshold = inputs.threshold if inputs.threshold is not None else 1.5
        lower, upper = q1 - threshold * iqr, q3 + threshold * iqr
        mask = (series < lower) | (series > upper)
        details = {"lower_bound": lower, "upper_bound": upper}
    else:
        threshold = inputs.threshold if inputs.threshold is not None else 3.0
        zscores = pd.Series(stats.zscore(values, nan_policy="omit"), index=values.index)
        mask = series.index.to_series().map(zscores).abs() > threshold
        details = {"zscore_threshold": threshold}
    return json_safe(
        {
            "method": inputs.method,
            "column": inputs.column,
            "threshold": threshold,
            "affected_row_count": int(mask.fillna(False).sum()),
            "rows": records(dataframe.loc[mask.fillna(False)].head(100)),
            **details,
        }
    )


def filter_dataset(dataframe: pd.DataFrame, inputs: FilterInput) -> dict[str, Any]:
    result = dataframe
    for condition in inputs.conditions:
        ensure_columns(dataframe, [condition.column])
        series = result[condition.column]
        if condition.operator == "eq":
            result = result[series == condition.value]
        elif condition.operator == "ne":
            result = result[series != condition.value]
        elif condition.operator in {"gt", "gte", "lt", "lte"}:
            try:
                if condition.operator == "gt":
                    mask = series > condition.value
                elif condition.operator == "gte":
                    mask = series >= condition.value
                elif condition.operator == "lt":
                    mask = series < condition.value
                else:
                    mask = series <= condition.value
                result = result[mask]
            except TypeError as exc:
                raise AnalyticalError("Comparison is invalid for the selected column") from exc
        elif condition.operator in {"contains", "starts_with", "ends_with"}:
            text = series.astype("string")
            if condition.operator == "contains":
                mask = text.str.contains(str(condition.value), na=False)
            elif condition.operator == "starts_with":
                mask = text.str.startswith(str(condition.value), na=False)
            else:
                mask = text.str.endswith(str(condition.value), na=False)
            result = result[mask]
        elif condition.operator == "is_null":
            result = result[series.isna()]
        else:
            result = result[series.notna()]
    return {"row_count": len(result), "rows": records(result.head(inputs.limit))}


def sort_dataset(dataframe: pd.DataFrame, inputs: SortInput) -> dict[str, Any]:
    ensure_columns(dataframe, inputs.columns)
    return {
        "row_count": len(dataframe),
        "rows": records(
            dataframe.sort_values(inputs.columns, ascending=inputs.direction == "asc").head(
                inputs.limit
            )
        ),
    }


def group_by_analysis(dataframe: pd.DataFrame, inputs: GroupByInput) -> dict[str, Any]:
    ensure_columns(dataframe, inputs.group_by + list(inputs.aggregations))
    grouped = (
        dataframe.groupby(inputs.group_by, dropna=False).agg(inputs.aggregations).reset_index()
    )
    grouped.columns = inputs.group_by + [
        f"{column}_{aggregation}" for column, aggregation in inputs.aggregations.items()
    ]
    return {
        "group_by": inputs.group_by,
        "row_count": len(grouped),
        "rows": records(grouped.head(inputs.limit)),
    }


def get_time_trends(dataframe: pd.DataFrame, inputs: TrendInput) -> dict[str, Any]:
    ensure_columns(dataframe, [inputs.datetime_column, inputs.metric_column])
    if not pd.api.types.is_numeric_dtype(dataframe[inputs.metric_column]):
        raise AnalyticalError("Trend metric must be numeric")
    dates = pd.to_datetime(dataframe[inputs.datetime_column], errors="coerce")
    valid = dataframe.assign(_date=dates).dropna(subset=["_date", inputs.metric_column])
    if len(valid) < 2:
        raise AnalyticalError("At least two valid observations are required for a trend")
    frequency = {"day": "D", "week": "W", "month": "ME", "quarter": "QE", "year": "YE"}[
        inputs.interval
    ]
    trend = (
        valid.set_index("_date")[inputs.metric_column]
        .resample(frequency)
        .agg(["count", "mean", "sum"])
        .reset_index()
    )
    return {
        "datetime_column": inputs.datetime_column,
        "metric_column": inputs.metric_column,
        "interval": inputs.interval,
        "rows": records(trend),
    }


def generate_chart(dataframe: pd.DataFrame, inputs: ChartInput) -> dict[str, Any]:
    columns = [
        column for column in (inputs.x_column, inputs.y_column, inputs.color_column) if column
    ]
    ensure_columns(dataframe, columns)
    if inputs.chart_type in {"bar", "line", "scatter"} and not inputs.x_column:
        raise AnalyticalError("This chart type requires x_column")
    if inputs.chart_type in {"bar", "line", "scatter"} and not inputs.y_column:
        raise AnalyticalError("This chart type requires y_column")
    if inputs.chart_type in {"histogram", "box"} and not inputs.x_column:
        raise AnalyticalError("This chart type requires x_column")
    if inputs.chart_type == "pie" and not inputs.x_column:
        raise AnalyticalError("Pie charts require x_column")
    data = dataframe.head(inputs.limit)
    spec: dict[str, Any] = {
        "data": [{"type": "pie" if inputs.chart_type == "pie" else inputs.chart_type}],
        "layout": {"title": f"{inputs.chart_type.title()} chart"},
    }
    trace = spec["data"][0]
    if inputs.x_column:
        trace["x" if inputs.chart_type not in {"histogram", "box", "pie"} else "labels"] = data[
            inputs.x_column
        ].tolist()
    if inputs.y_column:
        trace["y"] = data[inputs.y_column].tolist()
    if inputs.color_column:
        trace["marker"] = {"color": data[inputs.color_column].tolist()}
    return json_safe(spec)
