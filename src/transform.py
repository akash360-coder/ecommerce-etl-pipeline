"""Clean the Olist source tables for downstream analysis."""

from collections.abc import Mapping

import pandas as pd

from src.config import EXPECTED_RAW_FILES
from src.logger import get_logger


def _strip_text_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with leading and trailing whitespace removed from text."""
    cleaned = dataframe.copy()
    text_columns = cleaned.select_dtypes(include=["object", "string"]).columns
    for column in text_columns:
        cleaned[column] = cleaned[column].map(
            lambda value: value.strip() if isinstance(value, str) else value
        )
    return cleaned


def _clean_common(dataframe: pd.DataFrame, table_name: str) -> pd.DataFrame:
    """Remove exact duplicates, trim text, and log duplicate counts."""
    logger = get_logger(__name__)
    duplicate_count = int(dataframe.duplicated().sum())
    cleaned = _strip_text_columns(dataframe.drop_duplicates())
    logger.info("%s: removed %d exact duplicate rows", table_name, duplicate_count)
    return cleaned


def _require_columns(
    dataframe: pd.DataFrame, required_columns: set[str], table_name: str
) -> None:
    """Raise a clear error if a required table column is absent."""
    missing_columns = required_columns.difference(dataframe.columns)
    if missing_columns:
        missing_list = ", ".join(sorted(missing_columns))
        raise ValueError(f"{table_name} is missing required columns: {missing_list}")


def _parse_date_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Parse columns named as date, timestamp, or time fields when present."""
    parsed = dataframe.copy()
    date_columns = [
        column
        for column in parsed.columns
        if column.endswith(("_date", "_timestamp", "_at"))
    ]
    for column in date_columns:
        parsed[column] = pd.to_datetime(parsed[column], errors="coerce")
    return parsed


def _standardize_location(
    dataframe: pd.DataFrame, city_column: str, state_column: str
) -> pd.DataFrame:
    """Normalize a location's city and state values when those columns exist."""
    standardized = dataframe.copy()
    if city_column in standardized.columns:
        standardized[city_column] = (
            standardized[city_column].astype("string").str.strip().str.lower()
        )
    if state_column in standardized.columns:
        standardized[state_column] = (
            standardized[state_column].astype("string").str.strip().str.upper()
        )
    return standardized


def _coerce_nonnegative_numeric(
    dataframe: pd.DataFrame, columns: tuple[str, ...], table_name: str
) -> pd.DataFrame:
    """Convert selected columns to numbers and reject invalid or negative values."""
    cleaned = dataframe.copy()
    for column in columns:
        original_values = cleaned[column]
        numeric_values = pd.to_numeric(original_values, errors="coerce")
        invalid_values = original_values.notna() & numeric_values.isna()
        if invalid_values.any():
            raise ValueError(
                f"{table_name}.{column} contains non-numeric values"
            )
        if numeric_values.lt(0).any():
            raise ValueError(f"{table_name}.{column} contains negative values")
        cleaned[column] = numeric_values
    return cleaned


def clean_customers(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Remove duplicate customers, trim text, and normalize city and state."""
    cleaned = _clean_common(dataframe, "customers")
    return _standardize_location(cleaned, "customer_city", "customer_state")


def clean_orders(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Parse order timestamps and add delivery duration and lateness fields."""
    cleaned = _clean_common(dataframe, "orders")
    cleaned = _parse_date_columns(cleaned)
    required_columns = {
        "order_purchase_timestamp",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    }
    _require_columns(cleaned, required_columns, "orders")

    purchase_date = cleaned["order_purchase_timestamp"]
    delivery_date = cleaned["order_delivered_customer_date"]
    estimated_date = cleaned["order_estimated_delivery_date"]
    cleaned["delivery_days"] = (
        delivery_date.sub(purchase_date).dt.total_seconds() / 86_400
    )
    cleaned["estimated_delivery_days"] = (
        estimated_date.sub(purchase_date).dt.total_seconds() / 86_400
    )
    cleaned["delivery_delay_days"] = (
        delivery_date.sub(estimated_date).dt.total_seconds() / 86_400
    )

    is_late = pd.Series(pd.NA, index=cleaned.index, dtype="boolean")
    comparable_dates = delivery_date.notna() & estimated_date.notna()
    is_late.loc[comparable_dates] = (
        delivery_date.loc[comparable_dates] > estimated_date.loc[comparable_dates]
    )
    cleaned["is_late"] = is_late
    return cleaned


def clean_order_items(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Validate item amounts and calculate price plus freight value."""
    cleaned = _clean_common(dataframe, "order_items")
    _require_columns(cleaned, {"price", "freight_value"}, "order_items")
    cleaned = _parse_date_columns(cleaned)
    cleaned = _coerce_nonnegative_numeric(
        cleaned, ("price", "freight_value"), "order_items"
    )
    cleaned["total_item_value"] = cleaned["price"] + cleaned["freight_value"]
    return cleaned


def clean_order_payments(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Validate payment amounts and standardize payment type text."""
    cleaned = _clean_common(dataframe, "order_payments")
    _require_columns(cleaned, {"payment_value"}, "order_payments")
    cleaned = _coerce_nonnegative_numeric(
        cleaned, ("payment_value",), "order_payments"
    )
    if "payment_type" in cleaned.columns:
        cleaned["payment_type"] = (
            cleaned["payment_type"].astype("string").str.strip().str.lower()
        )
    return cleaned


def clean_order_reviews(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Parse review dates, keep the latest row per review, and flag comments."""
    cleaned = _clean_common(dataframe, "order_reviews")
    _require_columns(cleaned, {"review_id"}, "order_reviews")
    cleaned = _parse_date_columns(cleaned)

    latest_date_column = next(
        (
            column
            for column in ("review_answer_timestamp", "review_creation_date")
            if column in cleaned.columns
        ),
        None,
    )
    if latest_date_column is not None:
        cleaned = cleaned.sort_values(
            latest_date_column, kind="mergesort", na_position="first"
        )

    duplicate_review_mask = cleaned["review_id"].notna() & cleaned[
        "review_id"
    ].duplicated(keep="last")
    duplicate_review_count = int(duplicate_review_mask.sum())
    cleaned = cleaned.loc[~duplicate_review_mask].copy()
    get_logger(__name__).info(
        "order_reviews: removed %d older duplicate review_id rows",
        duplicate_review_count,
    )

    comment_columns = [
        column
        for column in ("review_comment_title", "review_comment_message")
        if column in cleaned.columns
    ]
    if comment_columns:
        comment_values = cleaned[comment_columns].fillna("").astype("string")
        cleaned["has_comment"] = comment_values.apply(
            lambda row: row.str.strip().ne("").any(), axis=1
        )
    else:
        cleaned["has_comment"] = False
    return cleaned


def clean_products(
    dataframe: pd.DataFrame, translations: pd.DataFrame
) -> pd.DataFrame:
    """Fix product column names and add English categories with a fallback."""
    cleaned = _clean_common(dataframe, "products")
    rename_columns = {
        "product_name_lenght": "product_name_length",
        "product_description_lenght": "product_description_length",
    }
    cleaned = cleaned.rename(
        columns={
            misspelled: corrected
            for misspelled, corrected in rename_columns.items()
            if misspelled in cleaned.columns and corrected not in cleaned.columns
        }
    )
    _require_columns(cleaned, {"product_category_name"}, "products")
    _require_columns(
        translations,
        {"product_category_name", "product_category_name_english"},
        "product_category_name_translation",
    )

    cleaned["product_category_name"] = cleaned[
        "product_category_name"
    ].fillna("unknown")
    translation_lookup = _strip_text_columns(
        translations[["product_category_name", "product_category_name_english"]]
    ).drop_duplicates(subset=["product_category_name"], keep="last")
    cleaned = cleaned.merge(
        translation_lookup,
        on="product_category_name",
        how="left",
        validate="many_to_one",
    )
    cleaned["product_category_name_english"] = cleaned[
        "product_category_name_english"
    ].fillna("unknown")
    return cleaned


def clean_sellers(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Remove duplicate sellers, trim text, and normalize city and state."""
    cleaned = _clean_common(dataframe, "sellers")
    return _standardize_location(cleaned, "seller_city", "seller_state")


def _mode_or_missing(values: pd.Series) -> object:
    """Return the most common non-null value, or a pandas missing value."""
    modes = values.dropna().mode()
    return modes.iloc[0] if not modes.empty else pd.NA


def clean_geolocation(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Average coordinates to one row per ZIP prefix and normalize location."""
    cleaned = _clean_common(dataframe, "geolocation")
    required_columns = {
        "geolocation_zip_code_prefix",
        "geolocation_lat",
        "geolocation_lng",
        "geolocation_city",
        "geolocation_state",
    }
    _require_columns(cleaned, required_columns, "geolocation")
    cleaned = cleaned.copy()
    for column in ("geolocation_lat", "geolocation_lng"):
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")

    aggregated = cleaned.groupby(
        "geolocation_zip_code_prefix", as_index=False, dropna=False, sort=False
    ).agg(
        geolocation_lat=("geolocation_lat", "mean"),
        geolocation_lng=("geolocation_lng", "mean"),
        geolocation_city=("geolocation_city", _mode_or_missing),
        geolocation_state=("geolocation_state", _mode_or_missing),
    )
    return _standardize_location(
        aggregated, "geolocation_city", "geolocation_state"
    )


def clean_product_category_name_translation(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Remove exact duplicates and trim category translation text."""
    return _clean_common(dataframe, "product_category_name_translation")


def clean_all(tables: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Clean all nine source tables and return them under their table names."""
    missing_tables = set(EXPECTED_RAW_FILES).difference(tables)
    if missing_tables:
        missing_list = ", ".join(sorted(missing_tables))
        raise ValueError(f"Missing input table(s) for cleaning: {missing_list}")

    cleaners = {
        "customers": clean_customers,
        "orders": clean_orders,
        "order_items": clean_order_items,
        "order_payments": clean_order_payments,
        "order_reviews": clean_order_reviews,
        "sellers": clean_sellers,
        "geolocation": clean_geolocation,
        "product_category_name_translation": clean_product_category_name_translation,
    }
    cleaned_tables: dict[str, pd.DataFrame] = {}
    for table_name in EXPECTED_RAW_FILES:
        if table_name == "products":
            cleaned_tables[table_name] = clean_products(
                tables[table_name], tables["product_category_name_translation"]
            )
        else:
            cleaned_tables[table_name] = cleaners[table_name](tables[table_name])
    return cleaned_tables