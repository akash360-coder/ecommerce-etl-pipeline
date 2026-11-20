"""Tests for star-schema construction and SQLite loading."""

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text

from src.load import (
    TABLE_NAMES,
    build_dim_date,
    build_fact_sales,
    build_star_schema,
    load_dataframes,
    open_sqlite_engine,
)
from src.run_stage3 import run_quality_checks


def _sample_source_tables() -> dict[str, pd.DataFrame]:
    """Return small cleaned source tables covering every schema table."""
    return {
        "customers": pd.DataFrame(
            {
                "customer_id": ["c1"],
                "customer_unique_id": ["u1"],
                "customer_zip_code_prefix": [100],
                "customer_city": ["city"],
                "customer_state": ["SP"],
            }
        ),
        "products": pd.DataFrame(
            {
                "product_id": ["p1"],
                "product_category_name": ["category"],
                "product_category_name_english": ["category"],
                "product_name_length": [10],
                "product_description_length": [100],
                "product_photos_qty": [1],
                "product_weight_g": [200],
                "product_length_cm": [10],
                "product_height_cm": [5],
                "product_width_cm": [8],
            }
        ),
        "sellers": pd.DataFrame(
            {
                "seller_id": ["s1"],
                "seller_zip_code_prefix": [200],
                "seller_city": ["town"],
                "seller_state": ["RJ"],
            }
        ),
        "geolocation": pd.DataFrame(
            {
                "geolocation_zip_code_prefix": [100],
                "geolocation_lat": [-20.0],
                "geolocation_lng": [-40.0],
                "geolocation_city": ["city"],
                "geolocation_state": ["SP"],
            }
        ),
        "orders": pd.DataFrame(
            {
                "order_id": ["o1"],
                "customer_id": ["c1"],
                "order_status": ["delivered"],
                "order_purchase_timestamp": [pd.Timestamp("2024-01-02 12:00:00")],
                "order_delivered_customer_date": [pd.Timestamp("2024-01-04")],
                "order_estimated_delivery_date": [pd.Timestamp("2024-01-05")],
                "delivery_days": [2.0],
                "estimated_delivery_days": [3.0],
                "delivery_delay_days": [-1.0],
                "is_late": [False],
            }
        ),
        "order_items": pd.DataFrame(
            {
                "order_id": ["o1", "o1"],
                "order_item_id": [1, 2],
                "product_id": ["p1", "p1"],
                "seller_id": ["s1", "s1"],
                "shipping_limit_date": [pd.Timestamp("2024-01-03")] * 2,
                "price": [10.0, 20.0],
                "freight_value": [1.0, 2.0],
                "total_item_value": [11.0, 22.0],
            }
        ),
        "order_payments": pd.DataFrame(
            {
                "order_id": ["o1"],
                "payment_sequential": [1],
                "payment_type": ["credit_card"],
                "payment_installments": [1],
                "payment_value": [33.0],
            }
        ),
        "order_reviews": pd.DataFrame(
            {
                "review_id": ["r1"],
                "order_id": ["o1"],
                "review_score": [5],
                "has_comment": [True],
                "review_creation_date": [pd.Timestamp("2024-01-05")],
                "review_answer_timestamp": [pd.Timestamp("2024-01-06")],
            }
        ),
    }


def test_build_dim_date_covers_every_day_inclusive() -> None:
    """The date dimension includes all calendar days between order dates."""
    orders = pd.DataFrame(
        {
            "order_purchase_timestamp": [
                "2024-01-02 12:00:00",
                "2024-01-04 08:00:00",
            ]
        }
    )

    dimension = build_dim_date(orders)

    assert dimension["full_date"].tolist() == [
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
    ]
    assert dimension["date_key"].tolist() == [20240102, 20240103, 20240104]
    assert dimension["is_weekend"].tolist() == [0, 0, 0]


def test_build_fact_sales_joins_items_to_order_attributes() -> None:
    """Each order item inherits customer/status and purchase date from its order."""
    source_tables = _sample_source_tables()

    sales = build_fact_sales(source_tables["order_items"], source_tables["orders"])

    assert len(sales) == 2
    assert sales["order_item_id"].tolist() == [1, 2]
    assert sales["customer_id"].tolist() == ["c1", "c1"]
    assert sales["order_status"].tolist() == ["delivered", "delivered"]
    assert sales["purchase_date_key"].tolist() == [20240102, 20240102]
    assert sales["price"].tolist() == [10.0, 20.0]


def test_load_is_idempotent_and_recreates_tables(tmp_path: Path) -> None:
    """Loading the same frames twice leaves exactly one copy in each table."""
    frames = build_star_schema(_sample_source_tables())
    database_path = tmp_path / "test_olist.sqlite3"

    first_counts = load_dataframes(frames, database_path)
    second_counts = load_dataframes(frames, database_path)

    assert first_counts == second_counts
    assert set(first_counts) == set(TABLE_NAMES)
    assert second_counts["fact_sales"] == 2
    engine = open_sqlite_engine(database_path)
    try:
        with engine.connect() as connection:
            count = connection.execute(
                text("SELECT COUNT(*) FROM fact_sales")
            ).scalar_one()
    finally:
        engine.dispose()
    assert count == 2


def test_quality_checks_detect_orphan_fact_sales_foreign_key(
    tmp_path: Path,
) -> None:
    """An inserted orphan customer reference is reported as a failed check."""
    source_tables = _sample_source_tables()
    frames = build_star_schema(source_tables)
    database_path = tmp_path / "orphan_test.sqlite3"
    report_path = tmp_path / "load_quality_report.csv"
    load_dataframes(frames, database_path)

    engine = open_sqlite_engine(database_path)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
            connection.commit()
            connection.execute(
                text(
                    "INSERT INTO fact_sales "
                    "(order_id, order_item_id, customer_id, product_id, seller_id, "
                    "purchase_date_key, order_status, price, freight_value, "
                    "total_item_value, purchase_timestamp, delivered_customer_date, "
                    "delivery_days, estimated_delivery_days, delivery_delay_days, is_late) "
                    "VALUES ('orphan-order', 1, 'missing-customer', 'p1', 's1', "
                    "20240102, 'delivered', 1, 0, 1, '2024-01-02 12:00:00', "
                    "NULL, NULL, NULL, NULL, NULL)"
                )
            )
            connection.commit()
    finally:
        engine.dispose()

    report = run_quality_checks(
        source_tables, frames, database_path=database_path, report_path=report_path
    )
    orphan_check = report.set_index("check_name").loc[
        "orphan_fact_sales_customer_id"
    ]

    assert orphan_check["status"] == "FAIL"
    assert orphan_check["actual"] == "1"
    assert report_path.is_file()
