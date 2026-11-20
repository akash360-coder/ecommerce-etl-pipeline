"""Central project paths and expected Olist source files."""

from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_ROOT = Path(os.environ.get("ETL_OUTPUT_DIR", PROJECT_ROOT)).expanduser().resolve()
RAW_DATA_DIR = Path(
    os.environ.get("ETL_RAW_DIR", DATA_DIR / "raw")
).expanduser().resolve()
SAMPLE_RAW_DATA_DIR = DATA_DIR / "sample" / "raw"
SAMPLE_OUTPUT_DIR = DATA_DIR / "sample" / "output"
PROCESSED_DATA_RELATIVE_PATH = Path("data") / "processed"
DASHBOARD_DATA_RELATIVE_PATH = Path("dashboard") / "data"
DATABASE_RELATIVE_PATH = Path("database") / "olist.sqlite3"
PIPELINE_RUN_SUMMARY_RELATIVE_PATH = Path("pipeline_run_summary.json")
PROCESSED_DATA_DIR = OUTPUT_ROOT / PROCESSED_DATA_RELATIVE_PATH
CLEANING_SUMMARY_PATH = PROCESSED_DATA_DIR / "cleaning_summary.csv"
LOAD_QUALITY_REPORT_PATH = PROCESSED_DATA_DIR / "load_quality_report.csv"
DATABASE_PATH = Path(
    os.environ.get("ETL_DB_PATH", PROJECT_ROOT / "database" / "olist.sqlite3")
).expanduser().resolve()
DATABASE_DIR = DATABASE_PATH.parent
SAMPLE_DATABASE_PATH = SAMPLE_OUTPUT_DIR / DATABASE_RELATIVE_PATH
SCHEMA_SQL_PATH = PROJECT_ROOT / "sql" / "create_schema.sql"
SAMPLE_QUERIES_PATH = PROJECT_ROOT / "sql" / "sample_queries.sql"
NOTEBOOK_FIGURES_DIR = PROJECT_ROOT / "notebooks" / "figures"
DASHBOARD_DATA_DIR = OUTPUT_ROOT / DASHBOARD_DATA_RELATIVE_PATH
PIPELINE_RUN_SUMMARY_PATH = OUTPUT_ROOT / PIPELINE_RUN_SUMMARY_RELATIVE_PATH
MIN_DELIVERED_ITEMS_PER_STATE = 100
MIN_REVIEWS_PER_CATEGORY = 50
LOGS_DIR = OUTPUT_ROOT / "logs"
PIPELINE_LOG_PATH = LOGS_DIR / "pipeline.log"

EXPECTED_RAW_FILES: dict[str, str] = {
    "customers": "olist_customers_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "product_category_name_translation": (
        "product_category_name_translation.csv"
    ),
}
