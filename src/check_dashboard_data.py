"""Validate generated dashboard CSV files for encoding and analysis readiness."""

import re
from pathlib import Path

import pandas as pd

from src.config import DASHBOARD_DATA_DIR
from src.logger import get_logger


KEY_COLUMNS: dict[str, list[str]] = {
    "category_revenue.csv": ["category"],
    "customer_state_revenue.csv": ["customer_state"],
    "delivery_by_state.csv": ["seller_state"],
    "kpi_summary.csv": ["kpi_name"],
    "monthly_delivery.csv": ["year_month"],
    "monthly_revenue.csv": ["year_month"],
    "payment_mix.csv": ["payment_type"],
    "review_summary.csv": ["summary_type"],
    "sales_detail.csv": ["order_id", "order_item_id"],
}

DATE_COLUMNS: dict[str, list[str]] = {
    "monthly_delivery.csv": ["year_month"],
    "monthly_revenue.csv": ["year_month"],
    "sales_detail.csv": ["purchase_timestamp"],
}

NUMERIC_COLUMN_NAMES = (
    "revenue",
    "orders",
    "items",
    "value",
    "payment",
    "price",
    "freight",
    "share",
    "growth",
    "rate",
    "days",
    "delay",
    "score",
    "count",
    "kpi_value",
)


def _log_check(
    logger: object,
    passed: bool,
    file_name: str,
    check_name: str,
    detail: str = "",
) -> None:
    """Log one named PASS or FAIL readiness check."""
    status = "PASS" if passed else "FAIL"
    message = f"{status}: {check_name} - {file_name}"
    if detail:
        message += f" ({detail})"
    getattr(logger, "info" if passed else "error")(message)


def _is_numeric_column(column_name: str) -> bool:
    """Return whether a column name represents numeric dashboard data."""
    lower_name = column_name.lower()
    return (
        lower_name in NUMERIC_COLUMN_NAMES
        or any(token in lower_name for token in NUMERIC_COLUMN_NAMES)
        or lower_name in {"year", "month", "purchase_date_key"}
    )


def check_dashboard_data(directory: Path = DASHBOARD_DATA_DIR) -> bool:
    """Check every dashboard CSV and return True only if all checks pass."""
    logger = get_logger(__name__)
    csv_paths = sorted(directory.glob("*.csv")) if directory.is_dir() else []
    if not csv_paths:
        logger.error("FAIL: file discovery - no CSV files found in %s", directory)
        return False

    all_passed = True
    for csv_path in csv_paths:
        file_name = csv_path.name

        try:
            csv_path.read_text(encoding="utf-8")
            utf8_passed = True
            utf8_detail = ""
        except UnicodeDecodeError as error:
            utf8_passed = False
            utf8_detail = str(error)
        except OSError as error:
            utf8_passed = False
            utf8_detail = str(error)
        _log_check(logger, utf8_passed, file_name, "UTF-8 encoding", utf8_detail)
        all_passed &= utf8_passed

        file_size = csv_path.stat().st_size
        empty_passed = file_size > 0
        _log_check(
            logger,
            empty_passed,
            file_name,
            "no empty file",
            f"{file_size} bytes",
        )
        all_passed &= empty_passed
        if not utf8_passed or not empty_passed:
            continue

        try:
            dataframe = pd.read_csv(csv_path, encoding="utf-8")
        except (pd.errors.ParserError, UnicodeDecodeError, OSError) as error:
            _log_check(logger, False, file_name, "readable CSV", str(error))
            all_passed = False
            continue

        rows_passed = len(dataframe) > 0
        _log_check(
            logger,
            rows_passed,
            file_name,
            "no empty rows",
            f"{len(dataframe)} data rows",
        )
        all_passed &= rows_passed

        key_columns = KEY_COLUMNS.get(file_name, [])
        missing_keys = [column for column in key_columns if column not in dataframe.columns]
        if missing_keys:
            null_passed = False
            null_detail = f"missing key columns: {', '.join(missing_keys)}"
        else:
            present_keys = [column for column in key_columns if column in dataframe.columns]
            null_columns = [
                column
                for column in present_keys
                if dataframe[column].isna().any()
            ]
            null_passed = not null_columns
            null_detail = (
                "no null key values"
                if null_passed
                else f"nulls in: {', '.join(null_columns)}"
            )
        _log_check(logger, null_passed, file_name, "no nulls in key columns", null_detail)
        all_passed &= null_passed

        date_columns = DATE_COLUMNS.get(file_name, [])
        invalid_dates: list[str] = []
        for column in date_columns:
            if column not in dataframe.columns:
                invalid_dates.append(f"{column} (missing)")
                continue
            year_month_pattern = re.compile(r"^\d{4}-\d{2}$")
            timestamp_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ T].*)?$")
            for value in dataframe[column].dropna().astype(str):
                pattern = year_month_pattern if column == "year_month" else timestamp_pattern
                if not pattern.match(value):
                    invalid_dates.append(f"{column}: {value}")
        date_passed = not invalid_dates
        date_detail = "ISO dates valid" if date_passed else "; ".join(invalid_dates)
        _log_check(logger, date_passed, file_name, "dates in ISO format", date_detail)
        all_passed &= date_passed

        numeric_invalid: list[str] = []
        for column in dataframe.columns:
            if not _is_numeric_column(column):
                continue
            for value in dataframe[column].dropna().astype(str):
                if re.search(r"[$€£,%]", value):
                    numeric_invalid.append(f"{column}: {value}")
        numeric_passed = not numeric_invalid
        numeric_detail = (
            "plain numeric values"
            if numeric_passed
            else "; ".join(numeric_invalid[:10])
        )
        _log_check(
            logger,
            numeric_passed,
            file_name,
            "numeric columns without separators or symbols",
            numeric_detail,
        )
        all_passed &= numeric_passed

        negative_revenue: list[str] = []
        for column in dataframe.columns:
            if "revenue" not in column.lower():
                continue
            if pd.api.types.is_numeric_dtype(dataframe[column]):
                negatives = dataframe.loc[dataframe[column] < 0, column]
                negative_revenue.extend(
                    f"{column}: {value}" for value in negatives.astype(str).tolist()
                )
        if file_name == "kpi_summary.csv" and "kpi_name" in dataframe.columns:
            revenue_rows = dataframe.loc[
                dataframe["kpi_name"].eq("total_revenue"),
                "kpi_value",
            ]
            negative_revenue.extend(
                f"kpi_value: {value}"
                for value in revenue_rows[pd.to_numeric(revenue_rows, errors="coerce") < 0].tolist()
            )
        revenue_passed = not negative_revenue
        revenue_detail = (
            "no negative revenue"
            if revenue_passed
            else "; ".join(negative_revenue)
        )
        _log_check(logger, revenue_passed, file_name, "no negative revenue", revenue_detail)
        all_passed &= revenue_passed

        logger.info(
            "SUMMARY: %s | rows=%d | columns=%d | file_size=%d bytes",
            file_name,
            len(dataframe),
            len(dataframe.columns),
            file_size,
        )

    logger.info(
        "Dashboard data check completed: %s",
        "PASS" if all_passed else "FAIL",
    )
    return all_passed


def main() -> int:
    """Run dashboard data readiness checks and return a process exit code."""
    return 0 if check_dashboard_data() else 1


if __name__ == "__main__":
    raise SystemExit(main())
