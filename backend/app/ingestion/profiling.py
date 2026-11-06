from pathlib import Path
from typing import Any

from app.ingestion.validation import read_dataset, validate_dataset_shape


def profile_dataset(
    path: Path,
    file_format: str,
    max_rows: int,
    max_columns: int,
) -> tuple[int, int, dict[str, Any]]:
    dataframe = read_dataset(path, file_format)
    validate_dataset_shape(dataframe, max_rows, max_columns)
    columns = {
        str(column): {
            "data_type": str(dataframe[column].dtype),
            "missing_count": int(dataframe[column].isna().sum()),
        }
        for column in dataframe.columns
    }
    profile = {
        "columns": columns,
        "duplicate_row_count": int(dataframe.duplicated().sum()),
        "memory_usage_bytes": int(dataframe.memory_usage(deep=True).sum()),
    }
    return dataframe.shape[0], dataframe.shape[1], profile
