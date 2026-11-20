"""Build the Olist star schema and load it into SQLite."""

from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL

from src.config import DATABASE_PATH, PROCESSED_DATA_DIR, SCHEMA_SQL_PATH
from src.logger import get_logger


TABLE_NAMES = (
    "dim_customers",
    "dim_products",
    "dim_sellers",
    "dim_date",
    "dim_geolocation",
    "fact_sales",
    "fact_payments",
    "fact_reviews",
)


def _read_csv(path: Path, date_columns: tuple[str, ...] = ()) -> pd.DataFrame:
    """Read a cleaned CSV and parse the named date columns explicitly."""
    dataframe = pd.read_csv(path, low_memory=False)
    for column in date_columns:
        if column in dataframe.columns:
            dataframe[column] = pd.to_datetime(
                dataframe[column], errors="coerce", format="mixed"
            )
    return dataframe


def read_cleaned_tables(processed_dir: Path = PROCESSED_DATA_DIR) -> dict[str, pd.DataFrame]:
    """Read the eight cleaned source tables needed to populate the schema."""
    date_columns = {
        "orders": (
            "order_purchase_timestamp",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ),
        "order_items": ("shipping_limit_date",),
        "order_reviews": ("review_creation_date", "review_answer_timestamp"),
    }
    table_names = (
        "customers",
        "products",
        "sellers",
        "geolocation",
        "orders",
        "order_items",
        "order_payments",
        "order_reviews",
    )
    tables: dict[str, pd.DataFrame] = {}
    for table_name in table_names:
        file_path = processed_dir / f"{table_name}.csv"
        if not file_path.is_file():
            raise FileNotFoundError(f"Cleaned table CSV is missing: {file_path}")
        tables[table_name] = _read_csv(file_path, date_columns.get(table_name, ()))
    return tables


def _select_columns(
    dataframe: pd.DataFrame, columns: tuple[str, ...], table_name: str
) -> pd.DataFrame:
    """Select schema columns and raise a clear error if any are absent."""
    missing_columns = set(columns).difference(dataframe.columns)
    if missing_columns:
        missing_list = ", ".join(sorted(missing_columns))
        raise ValueError(f"{table_name} is missing required columns: {missing_list}")
    selected = dataframe.loc[:, columns].copy()
    return selected


def _validate_primary_key(
    dataframe: pd.DataFrame, columns: tuple[str, ...], table_name: str
) -> None:
    """Reject null or duplicated primary-key values before database loading."""
    if dataframe.loc[:, columns].isna().any(axis=None):
        raise ValueError(f"{table_name} contains null primary-key values")
    if dataframe.duplicated(subset=list(columns)).any():
        raise ValueError(f"{table_name} contains duplicate primary-key values")


def build_dim_date(orders: pd.DataFrame) -> pd.DataFrame:
    """Generate one date dimension row per day in the purchase date range."""
    if "order_purchase_timestamp" not in orders.columns:
        raise ValueError("orders is missing required column: order_purchase_timestamp")
    purchase_dates = pd.to_datetime(
        orders["order_purchase_timestamp"], errors="coerce", format="mixed"
    ).dropna().dt.normalize()
    if purchase_dates.empty:
        raise ValueError("Cannot build dim_date without valid purchase timestamps")

    calendar = pd.date_range(purchase_dates.min(), purchase_dates.max(), freq="D")
    dimension = pd.DataFrame({"full_date": calendar})
    dimension["date_key"] = dimension["full_date"].dt.strftime("%Y%m%d").astype(int)
    dimension["year"] = dimension["full_date"].dt.year
    dimension["quarter"] = dimension["full_date"].dt.quarter
    dimension["month"] = dimension["full_date"].dt.month
    dimension["month_name"] = dimension["full_date"].dt.month_name()
    dimension["day"] = dimension["full_date"].dt.day
    dimension["day_of_week"] = dimension["full_date"].dt.dayofweek
    dimension["day_name"] = dimension["full_date"].dt.day_name()
    dimension["is_weekend"] = dimension["full_date"].dt.dayofweek.ge(5).astype(int)
    dimension["full_date"] = dimension["full_date"].dt.strftime("%Y-%m-%d")
    return dimension.loc[
        :,
        [
            "date_key",
            "full_date",
            "year",
            "quarter",
            "month",
            "month_name",
            "day",
            "day_of_week",
            "day_name",
            "is_weekend",
        ],
    ]


def _build_dim_customers(customers: pd.DataFrame) -> pd.DataFrame:
    """Map cleaned customers to the customer dimension schema."""
    columns = (
        "customer_id",
        "customer_unique_id",
        "customer_zip_code_prefix",
        "customer_city",
        "customer_state",
    )
    result = _select_columns(customers, columns, "customers")
    _validate_primary_key(result, ("customer_id",), "dim_customers")
    return result


def _build_dim_products(products: pd.DataFrame) -> pd.DataFrame:
    """Map cleaned products to the product dimension schema."""
    columns = (
        "product_id",
        "product_category_name",
        "product_category_name_english",
        "product_name_length",
        "product_description_length",
        "product_photos_qty",
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    )
    result = _select_columns(products, columns, "products")
    _validate_primary_key(result, ("product_id",), "dim_products")
    return result


def _build_dim_sellers(sellers: pd.DataFrame) -> pd.DataFrame:
    """Map cleaned sellers to the seller dimension schema."""
    columns = (
        "seller_id",
        "seller_zip_code_prefix",
        "seller_city",
        "seller_state",
    )
    result = _select_columns(sellers, columns, "sellers")
    _validate_primary_key(result, ("seller_id",), "dim_sellers")
    return result


def _build_dim_geolocation(geolocation: pd.DataFrame) -> pd.DataFrame:
    """Map cleaned ZIP-prefix coordinates to the geolocation dimension."""
    columns = (
        "geolocation_zip_code_prefix",
        "geolocation_lat",
        "geolocation_lng",
        "geolocation_city",
        "geolocation_state",
    )
    result = _select_columns(geolocation, columns, "geolocation").rename(
        columns={
            "geolocation_lat": "latitude",
            "geolocation_lng": "longitude",
            "geolocation_city": "city",
            "geolocation_state": "state",
        }
    )
    _validate_primary_key(
        result, ("geolocation_zip_code_prefix",), "dim_geolocation"
    )
    return result


def build_fact_sales(
    order_items: pd.DataFrame, orders: pd.DataFrame
) -> pd.DataFrame:
    """Join order items with order attributes at one row per order item."""
    item_columns = (
        "order_id",
        "order_item_id",
        "product_id",
        "seller_id",
        "price",
        "freight_value",
        "total_item_value",
    )
    order_columns = (
        "order_id",
        "customer_id",
        "order_status",
        "order_purchase_timestamp",
        "order_delivered_customer_date",
        "delivery_days",
        "estimated_delivery_days",
        "delivery_delay_days",
        "is_late",
    )
    items = _select_columns(order_items, item_columns, "order_items")
    order_data = _select_columns(orders, order_columns, "orders")
    joined = items.merge(
        order_data,
        on="order_id",
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    missing_orders = int(joined["_merge"].eq("left_only").sum())
    if missing_orders:
        raise ValueError(f"Found {missing_orders} order item(s) without a matching order")
    joined = joined.drop(columns="_merge")

    purchase_dates = pd.to_datetime(
        joined["order_purchase_timestamp"], errors="coerce", format="mixed"
    )
    if purchase_dates.isna().any():
        raise ValueError("fact_sales has missing or invalid purchase timestamps")
    joined["purchase_date_key"] = purchase_dates.dt.strftime("%Y%m%d").astype(int)
    joined["purchase_timestamp"] = purchase_dates
    joined["delivered_customer_date"] = pd.to_datetime(
        joined["order_delivered_customer_date"], errors="coerce", format="mixed"
    )
    joined["is_late"] = joined["is_late"].map({True: 1, False: 0})

    result_columns = (
        "order_id",
        "order_item_id",
        "customer_id",
        "product_id",
        "seller_id",
        "purchase_date_key",
        "order_status",
        "price",
        "freight_value",
        "total_item_value",
        "purchase_timestamp",
        "delivered_customer_date",
        "delivery_days",
        "estimated_delivery_days",
        "delivery_delay_days",
        "is_late",
    )
    result = joined.loc[:, result_columns].copy()
    _validate_primary_key(result, ("order_id", "order_item_id"), "fact_sales")
    return result


def _build_fact_payments(payments: pd.DataFrame) -> pd.DataFrame:
    """Map cleaned payment rows to the payment fact schema."""
    columns = (
        "order_id",
        "payment_sequential",
        "payment_type",
        "payment_installments",
        "payment_value",
    )
    result = _select_columns(payments, columns, "order_payments")
    _validate_primary_key(result, ("order_id", "payment_sequential"), "fact_payments")
    return result


def _build_fact_reviews(reviews: pd.DataFrame) -> pd.DataFrame:
    """Map cleaned review rows to the review fact schema."""
    columns = (
        "review_id",
        "order_id",
        "review_score",
        "has_comment",
        "review_creation_date",
        "review_answer_timestamp",
    )
    result = _select_columns(reviews, columns, "order_reviews")
    result["has_comment"] = result["has_comment"].astype(int)
    for column in ("review_creation_date", "review_answer_timestamp"):
        result[column] = pd.to_datetime(
            result[column], errors="coerce", format="mixed"
        )
    _validate_primary_key(result, ("review_id",), "fact_reviews")
    return result


def build_star_schema(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Build all dimension and fact DataFrames from cleaned source tables."""
    required_tables = {
        "customers",
        "products",
        "sellers",
        "geolocation",
        "orders",
        "order_items",
        "order_payments",
        "order_reviews",
    }
    missing_tables = required_tables.difference(tables)
    if missing_tables:
        raise ValueError(f"Missing cleaned tables: {', '.join(sorted(missing_tables))}")

    return {
        "dim_customers": _build_dim_customers(tables["customers"]),
        "dim_products": _build_dim_products(tables["products"]),
        "dim_sellers": _build_dim_sellers(tables["sellers"]),
        "dim_date": build_dim_date(tables["orders"]),
        "dim_geolocation": _build_dim_geolocation(tables["geolocation"]),
        "fact_sales": build_fact_sales(tables["order_items"], tables["orders"]),
        "fact_payments": _build_fact_payments(tables["order_payments"]),
        "fact_reviews": _build_fact_reviews(tables["order_reviews"]),
    }


def _create_sqlite_engine(database_path: Path) -> Engine:
    """Create a SQLAlchemy SQLite engine for a file-backed database."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    url = URL.create("sqlite", database=str(database_path))
    return create_engine(url)


def _execute_schema(connection: Any, schema_path: Path) -> None:
    """Execute each statement in the schema SQL file on an open connection."""
    if not schema_path.is_file():
        raise FileNotFoundError(f"Schema SQL file is missing: {schema_path}")
    schema_sql = schema_path.read_text(encoding="utf-8")
    statements = [statement.strip() for statement in schema_sql.split(";")]
    for statement in statements:
        if statement:
            connection.exec_driver_sql(statement)


def load_dataframes(
    frames: dict[str, pd.DataFrame],
    database_path: Path = DATABASE_PATH,
    schema_path: Path = SCHEMA_SQL_PATH,
) -> dict[str, int]:
    """Recreate the SQLite schema and load each supplied table DataFrame."""
    missing_tables = set(TABLE_NAMES).difference(frames)
    if missing_tables:
        raise ValueError(f"Missing schema DataFrames: {', '.join(sorted(missing_tables))}")

    logger = get_logger(__name__)
    engine = _create_sqlite_engine(database_path)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            foreign_keys_enabled = connection.exec_driver_sql(
                "PRAGMA foreign_keys"
            ).scalar_one()
            if foreign_keys_enabled != 1:
                raise RuntimeError("SQLite foreign key enforcement could not be enabled")
            connection.commit()

            with connection.begin():
                _execute_schema(connection, schema_path)
                for table_name in TABLE_NAMES:
                    frames[table_name].to_sql(
                        table_name,
                        con=connection,
                        if_exists="append",
                        index=False,
                        method="multi",
                        chunksize=50,
                    )
                violations = connection.exec_driver_sql(
                    "PRAGMA foreign_key_check"
                ).fetchall()
                if violations:
                    raise ValueError(f"SQLite foreign key violations: {violations[:5]}")

                row_counts = {
                    table_name: int(
                        connection.exec_driver_sql(
                            f"SELECT COUNT(*) FROM {table_name}"
                        ).scalar_one()
                    )
                    for table_name in TABLE_NAMES
                }
        for table_name, row_count in row_counts.items():
            logger.info("Loaded %s: rows=%d", table_name, row_count)
        return row_counts
    finally:
        engine.dispose()


def load_cleaned_data(
    processed_dir: Path = PROCESSED_DATA_DIR,
    database_path: Path = DATABASE_PATH,
    schema_path: Path = SCHEMA_SQL_PATH,
) -> dict[str, int]:
    """Read cleaned CSVs, build the star schema, and load it into SQLite."""
    tables = read_cleaned_tables(processed_dir)
    frames = build_star_schema(tables)
    return load_dataframes(frames, database_path, schema_path)


def open_sqlite_engine(database_path: Path = DATABASE_PATH) -> Engine:
    """Create an engine with SQLite foreign-key enforcement enabled per connection."""
    engine = _create_sqlite_engine(database_path)

    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection: Any, connection_record: Any) -> None:
        """Enable SQLite foreign keys on each newly opened DBAPI connection."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine
