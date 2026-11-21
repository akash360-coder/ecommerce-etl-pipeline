"""Tests for dashboard-data exports using a small in-memory SQLite database."""

from pathlib import Path
from collections.abc import Iterator

import pandas as pd
import pytest
from sqlalchemy import Engine, create_engine, text

from src import export_dashboard_data


@pytest.fixture
def export_engine() -> Iterator[Engine]:
    """Create an in-memory SQLite database with small star-schema fixtures."""
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE dim_date (date_key INTEGER, full_date TEXT, year INTEGER, "
            "month INTEGER, month_name TEXT)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE dim_customers (customer_id TEXT, customer_unique_id TEXT, "
            "customer_state TEXT)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE dim_products (product_id TEXT, product_category_name TEXT, "
            "product_category_name_english TEXT)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE dim_sellers (seller_id TEXT, seller_state TEXT)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE fact_sales (order_id TEXT, order_item_id INTEGER, "
            "purchase_date_key INTEGER, purchase_timestamp TEXT, order_status TEXT, "
            "customer_id TEXT, product_id TEXT, seller_id TEXT, price REAL, "
            "freight_value REAL, total_item_value REAL, delivery_days REAL, "
            "delivery_delay_days REAL, is_late INTEGER)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE fact_reviews (review_id TEXT, order_id TEXT, review_score INTEGER)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE fact_payments (order_id TEXT, payment_type TEXT, "
            "payment_value REAL, payment_installments INTEGER)"
        )
        connection.execute(
            text("INSERT INTO dim_date VALUES (:key, :date, :year, :month, :name)"),
            [
                {"key": 20170101, "date": "2017-01-01", "year": 2017, "month": 1, "name": "January"},
                {"key": 20170102, "date": "2017-01-02", "year": 2017, "month": 1, "name": "January"},
                {"key": 20180903, "date": "2018-09-03", "year": 2018, "month": 9, "name": "September"},
            ],
        )
        connection.execute(
            text("INSERT INTO dim_customers VALUES (:id, :unique_id, :state)"),
            [
                {"id": "c1", "unique_id": "u1", "state": "SP"},
                {"id": "c2", "unique_id": "u2", "state": "RJ"},
            ],
        )
        connection.execute(
            text("INSERT INTO dim_products VALUES (:id, :category, :english)"),
            [
                {"id": "p1", "category": "alpha", "english": "Alpha"},
                {"id": "p2", "category": "beta", "english": "Beta"},
                {"id": "p3", "category": "cancel", "english": "Canceled category"},
            ],
        )
        connection.execute(
            text("INSERT INTO dim_sellers VALUES (:id, :state)"),
            [{"id": "s1", "state": "AA"}, {"id": "s2", "state": "BB"}],
        )
        sales = [
            ("o1", 1, 20170101, "2017-01-01 10:00:00", "delivered", "c1", "p1", "s1", 10, 1, 11, 3, -1, 0),
            ("o2", 1, 20170102, "2017-01-02 10:00:00", "delivered", "c1", "p1", "s1", 20, 1, 21, 5, 1, 1),
            ("o3", 1, 20170102, "2017-01-02 11:00:00", "delivered", "c2", "p2", "s2", 5, 1, 6, 2, -1, 0),
            ("o4", 1, 20170102, "2017-01-02 12:00:00", "canceled", "c2", "p3", "s2", 100, 1, 101, None, None, None),
            ("o5", 1, 20170102, "2017-01-02 13:00:00", "unavailable", "c2", "p3", "s2", 50, 1, 51, None, None, None),
            ("o6", 1, 20180903, "2018-09-03 09:00:00", "delivered", "c1", "p1", "s1", 99, 1, 100, 2, -1, 0),
        ]
        connection.execute(
            text("INSERT INTO fact_sales VALUES "
                 "(:order_id, :item_id, :date_key, :timestamp, :status, :customer, "
                 ":product, :seller, :price, :freight, :total, :days, :delay, :late)"),
            [
                dict(zip(("order_id", "item_id", "date_key", "timestamp", "status", "customer", "product", "seller", "price", "freight", "total", "days", "delay", "late"), row))
                for row in sales
            ],
        )
        connection.execute(
            text("INSERT INTO fact_reviews VALUES (:review_id, :order_id, :score)"),
            [
                {"review_id": "r1", "order_id": "o1", "score": 5},
                {"review_id": "r2", "order_id": "o2", "score": 4},
                {"review_id": "r3", "order_id": "o3", "score": 3},
                {"review_id": "r4", "order_id": "o6", "score": 5},
            ],
        )
        connection.execute(
            text("INSERT INTO fact_payments VALUES (:order_id, :type, :value, :installments)"),
            [
                {"order_id": "o1", "type": "credit_card", "value": 11, "installments": 1},
                {"order_id": "o2", "type": "boleto", "value": 21, "installments": 1},
                {"order_id": "o3", "type": "credit_card", "value": 6, "installments": 2},
                {"order_id": "o4", "type": "voucher", "value": 101, "installments": 1},
                {"order_id": "o6", "type": "credit_card", "value": 100, "installments": 2},
            ],
        )
    yield engine
    engine.dispose()


def test_exports_exclude_canceled_revenue_and_apply_thresholds(
    export_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Revenue excludes ineligible states and volume filters constrain rankings."""
    monkeypatch.setattr(export_dashboard_data, "MIN_DELIVERED_ITEMS_PER_STATE", 2)
    monkeypatch.setattr(export_dashboard_data, "MIN_REVIEWS_PER_CATEGORY", 2)

    export_dashboard_data.export_dashboard_data(export_engine, tmp_path)

    monthly = pd.read_csv(tmp_path / "monthly_revenue.csv")
    assert monthly["revenue"].sum() == pytest.approx(35)
    assert "2018-09" not in monthly["year_month"].tolist()
    delivery = pd.read_csv(tmp_path / "delivery_by_state.csv")
    assert delivery["seller_state"].tolist() == ["AA"]
    reviews = pd.read_csv(tmp_path / "review_summary.csv")
    category_rows = reviews.loc[reviews["summary_type"] == "category_average"]
    assert category_rows["category"].tolist() == ["Alpha"]
    kpis = pd.read_csv(tmp_path / "kpi_summary.csv")
    kpi_values = dict(zip(kpis["kpi_name"], kpis["kpi_value"]))
    assert kpi_values["total_revenue"] == pytest.approx(134)
    assert kpi_values["total_orders"] == pytest.approx(4)
    assert kpi_values["total_items_sold"] == pytest.approx(4)
    monthly_delivery = pd.read_csv(tmp_path / "monthly_delivery.csv")
    assert monthly_delivery["year_month"].tolist() == ["2017-01"]
    assert monthly_delivery["delivered_items"].item() == 3


def test_exports_have_expected_csv_columns(
    export_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All export files use documented, stable column names."""
    monkeypatch.setattr(export_dashboard_data, "MIN_DELIVERED_ITEMS_PER_STATE", 1)
    monkeypatch.setattr(export_dashboard_data, "MIN_REVIEWS_PER_CATEGORY", 1)

    export_dashboard_data.export_dashboard_data(export_engine, tmp_path)

    expected_columns = {
        "monthly_revenue.csv": ["year", "month", "month_name", "year_month", "revenue", "orders", "average_order_value", "mom_growth_pct"],
        "category_revenue.csv": ["category", "revenue", "items", "orders", "revenue_share_pct"],
        "delivery_by_state.csv": ["seller_state", "delivered_items", "late_items", "late_delivery_rate_pct"],
        "customer_state_revenue.csv": ["customer_state", "revenue", "orders", "items"],
        "review_summary.csv": ["summary_type", "review_score", "category", "review_count", "average_review_score", "share_pct"],
        "payment_mix.csv": ["payment_type", "payment_value", "payment_share_pct"],
        "sales_detail.csv": ["order_id", "order_item_id", "purchase_date_key", "purchase_timestamp", "order_status", "customer_id", "customer_unique_id", "customer_state", "product_id", "product_category_name", "category", "seller_id", "seller_state", "price", "freight_value", "total_item_value", "revenue", "revenue_eligible", "delivery_days", "delivery_delay_days", "is_late"],
        "kpi_summary.csv": ["kpi_name", "kpi_value", "kpi_unit"],
        "monthly_delivery.csv": ["year_month", "delivered_items", "late_items", "late_delivery_rate_pct", "average_delivery_days", "average_review_score"],
    }
    for filename, columns in expected_columns.items():
        exported = pd.read_csv(tmp_path / filename)
        assert exported.columns.tolist() == columns
    detail = pd.read_csv(tmp_path / "sales_detail.csv")
    assert detail.loc[detail["order_status"] == "canceled", "revenue"].item() == 0
