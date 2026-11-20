"""Unit tests for Stage 2 table cleaning functions."""

import pandas as pd

from src.transform import (
    clean_customers,
    clean_geolocation,
    clean_order_items,
    clean_order_payments,
    clean_order_reviews,
    clean_orders,
    clean_product_category_name_translation,
    clean_products,
    clean_sellers,
)


def test_clean_customers_removes_exact_duplicates_and_normalizes_location() -> None:
    """Customer duplicates are removed and city/state casing is normalized."""
    customers = pd.DataFrame(
        {
            "customer_id": ["c1", "c1"],
            "customer_city": [" Sample City ", " Sample City "],
            "customer_state": [" sp ", " sp "],
        }
    )

    cleaned = clean_customers(customers)

    assert len(cleaned) == 1
    assert cleaned.loc[0, "customer_city"] == "sample city"
    assert cleaned.loc[0, "customer_state"] == "SP"


def test_clean_orders_parses_dates_and_calculates_delivery_fields() -> None:
    """Orders include late, on-time, and undelivered delivery outcomes."""
    orders = pd.DataFrame(
        {
            "order_purchase_timestamp": [
                "2024-01-01 00:00:00",
                "2024-01-01 00:00:00",
                "2024-01-01 00:00:00",
            ],
            "order_approved_at": [
                "2024-01-01 01:00:00",
                "2024-01-01 01:00:00",
                None,
            ],
            "order_delivered_customer_date": [
                "2024-01-05 00:00:00",
                "2024-01-04 00:00:00",
                None,
            ],
            "order_estimated_delivery_date": [
                "2024-01-04 00:00:00",
                "2024-01-05 00:00:00",
                "2024-01-06 00:00:00",
            ],
        }
    )

    cleaned = clean_orders(orders)

    assert pd.api.types.is_datetime64_any_dtype(
        cleaned["order_purchase_timestamp"]
    )
    assert cleaned.loc[0, "delivery_delay_days"] == 1
    assert bool(cleaned.loc[0, "is_late"])
    assert cleaned.loc[1, "delivery_delay_days"] == -1
    assert not bool(cleaned.loc[1, "is_late"])
    assert pd.isna(cleaned.loc[2, "delivery_days"])
    assert pd.isna(cleaned.loc[2, "delivery_delay_days"])
    assert pd.isna(cleaned.loc[2, "is_late"])


def test_clean_order_items_parses_shipping_date_and_calculates_value() -> None:
    """Item values become numeric, dates parse, and exact duplicates disappear."""
    order_items = pd.DataFrame(
        {
            "shipping_limit_date": ["2024-02-01 12:00:00"] * 2,
            "price": ["10.50", "10.50"],
            "freight_value": ["2.25", "2.25"],
        }
    )

    cleaned = clean_order_items(order_items)

    assert len(cleaned) == 1
    assert pd.api.types.is_datetime64_any_dtype(cleaned["shipping_limit_date"])
    assert cleaned.loc[0, "total_item_value"] == 12.75


def test_clean_order_payments_normalizes_type_and_amount() -> None:
    """Payment type text is lowercase and payment values are numeric."""
    payments = pd.DataFrame(
        {"payment_type": ["  CREDIT_CARD  "], "payment_value": ["35.50"]}
    )

    cleaned = clean_order_payments(payments)

    assert cleaned.loc[0, "payment_type"] == "credit_card"
    assert cleaned.loc[0, "payment_value"] == 35.5


def test_clean_order_reviews_keeps_latest_and_flags_comments() -> None:
    """Reviews keep the latest duplicate ID and identify non-empty comments."""
    reviews = pd.DataFrame(
        {
            "review_id": ["r1", "r1", "r2"],
            "review_score": [1, 5, 3],
            "review_creation_date": [
                "2024-01-01 00:00:00",
                "2024-01-02 00:00:00",
                "2024-01-01 00:00:00",
            ],
            "review_answer_timestamp": [
                "2024-01-01 01:00:00",
                "2024-01-02 01:00:00",
                "2024-01-01 01:00:00",
            ],
            "review_comment_title": [None, "Good", "  "],
            "review_comment_message": ["Old", None, None],
        }
    )

    cleaned = clean_order_reviews(reviews).set_index("review_id")

    assert len(cleaned) == 2
    assert cleaned.loc["r1", "review_score"] == 5
    assert bool(cleaned.loc["r1", "has_comment"])
    assert not bool(cleaned.loc["r2", "has_comment"])
    assert pd.api.types.is_datetime64_any_dtype(cleaned["review_creation_date"])


def test_clean_products_renames_columns_and_falls_back_to_unknown() -> None:
    """Misspelled product fields are fixed and unmatched categories are unknown."""
    products = pd.DataFrame(
        {
            "product_name_lenght": [10, 11, 12],
            "product_description_lenght": [100, 110, 120],
            "product_category_name": ["pet_shop", None, "unmapped"],
        }
    )
    translations = pd.DataFrame(
        {
            "product_category_name": ["pet_shop"],
            "product_category_name_english": ["pet supplies"],
        }
    )

    cleaned = clean_products(products, translations)

    assert "product_name_length" in cleaned.columns
    assert "product_description_length" in cleaned.columns
    assert "product_name_lenght" not in cleaned.columns
    assert cleaned["product_category_name_english"].tolist() == [
        "pet supplies",
        "unknown",
        "unknown",
    ]


def test_clean_sellers_normalizes_city_and_state() -> None:
    """Seller city and state values use lowercase and uppercase respectively."""
    sellers = pd.DataFrame(
        {"seller_city": [" Sample City "], "seller_state": [" rj "]}
    )

    cleaned = clean_sellers(sellers)

    assert cleaned.loc[0, "seller_city"] == "sample city"
    assert cleaned.loc[0, "seller_state"] == "RJ"


def test_clean_geolocation_averages_coordinates_per_zip_prefix() -> None:
    """Geolocation rows collapse to one ZIP-prefix row with mean coordinates."""
    geolocation = pd.DataFrame(
        {
            "geolocation_zip_code_prefix": [100, 100],
            "geolocation_lat": [-20.0, -22.0],
            "geolocation_lng": [-40.0, -42.0],
            "geolocation_city": [" Sample City ", "sample city"],
            "geolocation_state": ["sp", " SP "],
        }
    )

    cleaned = clean_geolocation(geolocation)

    assert len(cleaned) == 1
    assert cleaned.loc[0, "geolocation_lat"] == -21.0
    assert cleaned.loc[0, "geolocation_lng"] == -41.0
    assert cleaned.loc[0, "geolocation_city"] == "sample city"
    assert cleaned.loc[0, "geolocation_state"] == "SP"


def test_clean_category_translations_strips_text_and_removes_duplicates() -> None:
    """Translation text is trimmed and exact duplicate rows are removed."""
    translations = pd.DataFrame(
        {
            "product_category_name": [" pet_shop ", " pet_shop "],
            "product_category_name_english": [" pet supplies ", " pet supplies "],
        }
    )

    cleaned = clean_product_category_name_translation(translations)

    assert len(cleaned) == 1
    assert cleaned.loc[0, "product_category_name"] == "pet_shop"
    assert cleaned.loc[0, "product_category_name_english"] == "pet supplies"
