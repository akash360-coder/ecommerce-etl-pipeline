"""Build a small, referentially consistent raw-data sample."""

import pandas as pd

from src.config import EXPECTED_RAW_FILES, RAW_DATA_DIR, SAMPLE_RAW_DATA_DIR
from src.logger import get_logger


SAMPLE_ORDER_COUNT = 500
RANDOM_SEED = 42
MAX_SAMPLE_BYTES = 5 * 1024 * 1024


def _read_raw_table(table_name: str) -> pd.DataFrame:
    """Read one configured raw source table or raise a clear missing-file error."""
    filename = EXPECTED_RAW_FILES[table_name]
    path = RAW_DATA_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Required raw CSV is missing: {path}")
    return pd.read_csv(path, low_memory=False)


def _normalized_zip_prefixes(values: pd.Series) -> set[str]:
    """Normalize ZIP-prefix keys for matching across raw CSV files."""
    normalized = values.dropna().astype("string").str.replace(r"\.0$", "", regex=True)
    return set(normalized.str.zfill(5))


def build_sample() -> dict[str, int]:
    """Write a seeded, related subset of all nine raw CSVs and return file sizes."""
    logger = get_logger(__name__)
    orders = _read_raw_table("orders")
    if orders.empty:
        raise ValueError("The raw orders CSV contains no rows; cannot build a sample")

    sampled_orders = orders.sample(
        n=min(SAMPLE_ORDER_COUNT, len(orders)), random_state=RANDOM_SEED
    )
    order_ids = set(sampled_orders["order_id"])
    items = _read_raw_table("order_items")
    sampled_items = items.loc[items["order_id"].isin(order_ids)].copy()
    customer_ids = set(sampled_orders["customer_id"])
    customers = _read_raw_table("customers")
    sampled_customers = customers.loc[customers["customer_id"].isin(customer_ids)].copy()
    product_ids = set(sampled_items["product_id"])
    products = _read_raw_table("products")
    sampled_products = products.loc[products["product_id"].isin(product_ids)].copy()
    seller_ids = set(sampled_items["seller_id"])
    sellers = _read_raw_table("sellers")
    sampled_sellers = sellers.loc[sellers["seller_id"].isin(seller_ids)].copy()

    needed_zip_prefixes = _normalized_zip_prefixes(
        pd.concat(
            [
                sampled_customers["customer_zip_code_prefix"],
                sampled_sellers["seller_zip_code_prefix"],
            ],
            ignore_index=True,
        )
    )
    geolocation = _read_raw_table("geolocation")
    geolocation_keys = geolocation["geolocation_zip_code_prefix"].dropna()
    normalized_geolocation_keys = geolocation_keys.astype("string").str.replace(
        r"\.0$", "", regex=True
    ).str.zfill(5)
    sampled_geolocation = geolocation.loc[
        normalized_geolocation_keys.isin(needed_zip_prefixes)
    ].groupby("geolocation_zip_code_prefix", sort=False).head(5).copy()

    sampled_tables = {
        "customers": sampled_customers,
        "orders": sampled_orders,
        "order_items": sampled_items,
        "order_payments": _read_raw_table("order_payments").query(
            "order_id in @order_ids"
        ),
        "order_reviews": _read_raw_table("order_reviews").query(
            "order_id in @order_ids"
        ),
        "products": sampled_products,
        "sellers": sampled_sellers,
        "geolocation": sampled_geolocation,
        "product_category_name_translation": _read_raw_table(
            "product_category_name_translation"
        ),
    }

    SAMPLE_RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_sizes: dict[str, int] = {}
    for table_name, dataframe in sampled_tables.items():
        filename = EXPECTED_RAW_FILES[table_name]
        output_path = SAMPLE_RAW_DATA_DIR / filename
        dataframe.to_csv(output_path, index=False)
        file_sizes[filename] = output_path.stat().st_size
        logger.info(
            "Sampled %s: rows=%d bytes=%d",
            filename,
            len(dataframe),
            file_sizes[filename],
        )

    total_bytes = sum(file_sizes.values())
    if total_bytes >= MAX_SAMPLE_BYTES:
        raise ValueError(
            f"Generated sample is {total_bytes} bytes; expected less than "
            f"{MAX_SAMPLE_BYTES} bytes (5 MB)."
        )

    logger.info(
        "Sample created at %s: orders=%d total_bytes=%d",
        SAMPLE_RAW_DATA_DIR,
        len(sampled_orders),
        total_bytes,
    )
    return file_sizes


def main() -> None:
    """Build the sample data subset and report success through the logger."""
    logger = get_logger(__name__)
    try:
        build_sample()
    except Exception as error:
        logger.error("Sample data generation failed: %s", error)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
