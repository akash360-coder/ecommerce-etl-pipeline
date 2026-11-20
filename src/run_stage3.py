"""Load the SQLite star schema and validate data quality."""

import math
import re
from pathlib import Path

import pandas as pd
from sqlalchemy import Connection, text

from src.config import (
    DATABASE_PATH,
    LOAD_QUALITY_REPORT_PATH,
    SAMPLE_QUERIES_PATH,
)
from src.load import (
    TABLE_NAMES,
    build_star_schema,
    load_dataframes,
    open_sqlite_engine,
    read_cleaned_tables,
)
from src.logger import get_logger


PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "dim_customers": ("customer_id",),
    "dim_products": ("product_id",),
    "dim_sellers": ("seller_id",),
    "dim_date": ("date_key",),
    "dim_geolocation": ("geolocation_zip_code_prefix",),
    "fact_sales": ("order_id", "order_item_id"),
    "fact_payments": ("order_id", "payment_sequential"),
    "fact_reviews": ("review_id",),
}

FOREIGN_KEYS: dict[str, tuple[str, str]] = {
    "customer_id": ("dim_customers", "customer_id"),
    "product_id": ("dim_products", "product_id"),
    "seller_id": ("dim_sellers", "seller_id"),
    "purchase_date_key": ("dim_date", "date_key"),
}


def _quality_result(
    check_name: str, expected: object, actual: object, passed: bool
) -> dict[str, str]:
    """Format one quality check result for logging and CSV reporting."""
    return {
        "check_name": check_name,
        "status": "PASS" if passed else "FAIL",
        "expected": str(expected),
        "actual": str(actual),
    }


def _orphan_count(connection: Connection, foreign_key: str) -> int:
    """Count fact_sales references without a matching dimension row."""
    dimension_table, dimension_key = FOREIGN_KEYS[foreign_key]
    query = text(
        f"SELECT COUNT(*) FROM fact_sales AS f "
        f"LEFT JOIN {dimension_table} AS d "
        f"ON f.{foreign_key} = d.{dimension_key} "
        f"WHERE d.{dimension_key} IS NULL"
    )
    return int(connection.execute(query).scalar_one())


def _duplicate_key_count(
    connection: Connection, table_name: str, key_columns: tuple[str, ...]
) -> int:
    """Count duplicated primary-key groups in a loaded table."""
    group_columns = ", ".join(key_columns)
    query = text(
        f"SELECT COUNT(*) FROM (SELECT {group_columns} FROM {table_name} "
        f"GROUP BY {group_columns} HAVING COUNT(*) > 1)"
    )
    return int(connection.execute(query).scalar_one())


def _sql_sum(connection: Connection, table_name: str, column_name: str) -> float:
    """Return a numeric SQLite column sum, using zero for an empty table."""
    result = connection.execute(
        text(f"SELECT COALESCE(SUM({column_name}), 0) FROM {table_name}")
    ).scalar_one()
    return float(result)


def run_quality_checks(
    source_tables: dict[str, pd.DataFrame],
    schema_frames: dict[str, pd.DataFrame],
    database_path: Path = DATABASE_PATH,
    report_path: Path = LOAD_QUALITY_REPORT_PATH,
) -> pd.DataFrame:
    """Run row-count, referential, sum, and primary-key checks and save results."""
    expected_counts = {
        "dim_customers": len(source_tables["customers"]),
        "dim_products": len(source_tables["products"]),
        "dim_sellers": len(source_tables["sellers"]),
        "dim_date": len(schema_frames["dim_date"]),
        "dim_geolocation": len(source_tables["geolocation"]),
        "fact_sales": len(source_tables["order_items"]),
        "fact_payments": len(source_tables["order_payments"]),
        "fact_reviews": len(source_tables["order_reviews"]),
    }
    results: list[dict[str, str]] = []
    logger = get_logger(__name__)
    engine = open_sqlite_engine(database_path)
    try:
        with engine.connect() as connection:
            for table_name in TABLE_NAMES:
                actual_count = int(
                    connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
                )
                results.append(
                    _quality_result(
                        f"row_count_{table_name}",
                        expected_counts[table_name],
                        actual_count,
                        actual_count == expected_counts[table_name],
                    )
                )

            for foreign_key in FOREIGN_KEYS:
                actual_orphans = _orphan_count(connection, foreign_key)
                results.append(
                    _quality_result(
                        f"orphan_fact_sales_{foreign_key}",
                        0,
                        actual_orphans,
                        actual_orphans == 0,
                    )
                )

            expected_sales_price = float(
                pd.to_numeric(source_tables["order_items"]["price"], errors="coerce").sum()
            )
            actual_sales_price = _sql_sum(connection, "fact_sales", "price")
            results.append(
                _quality_result(
                    "sum_price_fact_sales_matches_order_items",
                    f"{expected_sales_price:.2f}",
                    f"{actual_sales_price:.2f}",
                    math.isclose(
                        expected_sales_price,
                        actual_sales_price,
                        rel_tol=1e-10,
                        abs_tol=0.01,
                    ),
                )
            )

            expected_payment_value = float(
                pd.to_numeric(
                    source_tables["order_payments"]["payment_value"],
                    errors="coerce",
                ).sum()
            )
            actual_payment_value = _sql_sum(
                connection, "fact_payments", "payment_value"
            )
            results.append(
                _quality_result(
                    "sum_payment_value_matches_order_payments",
                    f"{expected_payment_value:.2f}",
                    f"{actual_payment_value:.2f}",
                    math.isclose(
                        expected_payment_value,
                        actual_payment_value,
                        rel_tol=1e-10,
                        abs_tol=0.01,
                    ),
                )
            )

            for table_name, key_columns in PRIMARY_KEYS.items():
                duplicate_count = _duplicate_key_count(
                    connection, table_name, key_columns
                )
                results.append(
                    _quality_result(
                        f"duplicate_primary_keys_{table_name}",
                        0,
                        duplicate_count,
                        duplicate_count == 0,
                    )
                )
    finally:
        engine.dispose()

    report = pd.DataFrame(
        results, columns=["check_name", "status", "expected", "actual"]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(report_path, index=False)
    for row in results:
        logger.info(
            "Quality check %s: %s (expected=%s actual=%s)",
            row["check_name"],
            row["status"],
            row["expected"],
            row["actual"],
        )
    return report


def _read_sample_queries(path: Path) -> list[tuple[str, str]]:
    """Parse named SQL blocks from the sample query file."""
    if not path.is_file():
        raise FileNotFoundError(f"Sample query SQL file is missing: {path}")
    query_pattern = re.compile(
        r"(?ms)^--\s*query:\s*([^\r\n]+)\s*\r?\n(.*?)(?=^--\s*query:|\Z)"
    )
    contents = path.read_text(encoding="utf-8")
    queries = [
        (match.group(1).strip(), match.group(2).strip())
        for match in query_pattern.finditer(contents)
        if match.group(2).strip()
    ]
    if not queries:
        raise ValueError(f"No named sample queries found in {path}")
    return queries


def run_sample_queries(
    database_path: Path = DATABASE_PATH,
    queries_path: Path = SAMPLE_QUERIES_PATH,
) -> dict[str, pd.DataFrame]:
    """Execute each named sample query once and log its first five rows."""
    logger = get_logger(__name__)
    results: dict[str, pd.DataFrame] = {}
    engine = open_sqlite_engine(database_path)
    try:
        with engine.connect() as connection:
            for query_name, query_sql in _read_sample_queries(queries_path):
                dataframe = pd.read_sql_query(text(query_sql), connection)
                results[query_name] = dataframe
                preview = dataframe.head(5).to_string(index=False)
                logger.info(
                    "Sample query %s returned %d rows. First rows:\n%s",
                    query_name,
                    len(dataframe),
                    preview if preview else "<no rows>",
                )
    finally:
        engine.dispose()
    return results


def main() -> None:
    """Load cleaned data, run quality checks, and verify sample queries."""
    logger = get_logger(__name__)
    try:
        source_tables = read_cleaned_tables()
        schema_frames = build_star_schema(source_tables)
        row_counts = load_dataframes(schema_frames)
        logger.info("Stage 3 loaded rows: %s", row_counts)
        report = run_quality_checks(source_tables, schema_frames)
        run_sample_queries()
        failed_checks = report.loc[report["status"] == "FAIL", "check_name"]
        if not failed_checks.empty:
            logger.error("Stage 3 quality checks failed: %s", ", ".join(failed_checks))
            raise SystemExit(1)
        logger.info("Stage 3 completed successfully.")
    except SystemExit:
        raise
    except Exception as error:
        logger.error("Stage 3 pipeline failed: %s", error)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
