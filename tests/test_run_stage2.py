"""Integration tests for the Stage 2 output runner."""

from pathlib import Path

import pandas as pd
import pytest

from src import run_stage2


def _sample_tables() -> dict[str, pd.DataFrame]:
    """Return minimal in-memory tables accepted by every Stage 2 cleaner."""
    return {
        "customers": pd.DataFrame(
            {"customer_city": [" Sample City "], "customer_state": [" sp "]}
        ),
        "orders": pd.DataFrame(
            {
                "order_purchase_timestamp": ["2024-01-01"],
                "order_delivered_customer_date": ["2024-01-03"],
                "order_estimated_delivery_date": ["2024-01-04"],
            }
        ),
        "order_items": pd.DataFrame({"price": [10], "freight_value": [2]}),
        "order_payments": pd.DataFrame({"payment_value": [12]}),
        "order_reviews": pd.DataFrame(
            {
                "review_id": ["r1"],
                "review_comment_title": [None],
                "review_comment_message": ["  "],
            }
        ),
        "products": pd.DataFrame({"product_category_name": [None]}),
        "sellers": pd.DataFrame(
            {"seller_city": [" Sample City "], "seller_state": [" sp "]}
        ),
        "geolocation": pd.DataFrame(
            {
                "geolocation_zip_code_prefix": [100],
                "geolocation_lat": [-20.0],
                "geolocation_lng": [-40.0],
                "geolocation_city": [" Sample City "],
                "geolocation_state": ["sp"],
            }
        ),
        "product_category_name_translation": pd.DataFrame(
            {
                "product_category_name": ["pet_shop"],
                "product_category_name_english": ["pet supplies"],
            }
        ),
    }


def test_main_writes_clean_tables_and_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runner saves one CSV per table and all requested summary columns."""
    output_directory = tmp_path / "processed"
    summary_path = output_directory / "cleaning_summary.csv"
    tables = _sample_tables()

    def extract_sample_tables() -> dict[str, pd.DataFrame]:
        """Supply the in-memory tables instead of reading raw files."""
        return tables

    monkeypatch.setattr(run_stage2, "extract_all", extract_sample_tables)
    monkeypatch.setattr(run_stage2, "PROCESSED_DATA_DIR", output_directory)
    monkeypatch.setattr(run_stage2, "CLEANING_SUMMARY_PATH", summary_path)

    run_stage2.main()

    summary = pd.read_csv(summary_path)
    assert summary.columns.tolist() == [
        "table",
        "rows_before",
        "rows_after",
        "duplicates_removed",
        "null_cells_before",
        "null_cells_after",
    ]
    assert len(summary) == 9
    assert set(summary["table"]) == set(tables)
    assert all((output_directory / f"{table_name}.csv").is_file() for table_name in tables)
