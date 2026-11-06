import csv
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd


class DatasetValidationError(ValueError):
    pass


def validate_csv_structure(path: Path) -> None:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file, strict=True)
            expected_columns: int | None = None
            for row in reader:
                if not row:
                    continue
                if expected_columns is None:
                    expected_columns = len(row)
                    continue
                if len(row) != expected_columns:
                    raise DatasetValidationError("The uploaded CSV has inconsistent columns")
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise DatasetValidationError("The uploaded CSV could not be read") from exc


def detect_format(path: Path, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".xlsx":
        with path.open("rb") as file:
            if file.read(4) != b"PK\x03\x04":
                raise DatasetValidationError("The uploaded XLSX file is invalid")
        return "xlsx"
    if suffix == ".csv":
        validate_csv_structure(path)
        return "csv"
    raise DatasetValidationError("Only CSV and XLSX files are supported")


def read_dataset(path: Path, file_format: str) -> pd.DataFrame:
    try:
        if file_format == "csv":
            return pd.read_csv(path, low_memory=False)
        return pd.read_excel(path, engine="openpyxl")
    except (
        OSError,
        ValueError,
        UnicodeDecodeError,
        BadZipFile,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ) as exc:
        raise DatasetValidationError("The uploaded dataset could not be read") from exc


def validate_dataset_shape(
    dataframe: pd.DataFrame, max_rows: int, max_columns: int
) -> None:
    if dataframe.empty:
        raise DatasetValidationError("The uploaded dataset is empty")
    if dataframe.shape[0] > max_rows:
        raise DatasetValidationError("The uploaded dataset exceeds the row limit")
    if dataframe.shape[1] > max_columns:
        raise DatasetValidationError("The uploaded dataset exceeds the column limit")
    if dataframe.columns.empty or any(not str(column).strip() for column in dataframe.columns):
        raise DatasetValidationError("The uploaded dataset must have named columns")
    if dataframe.columns.duplicated().any():
        raise DatasetValidationError("The uploaded dataset contains duplicate columns")
