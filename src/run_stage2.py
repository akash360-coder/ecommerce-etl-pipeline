"""Run extraction and cleaning, then save processed CSV outputs."""

import pandas as pd

from src.config import CLEANING_SUMMARY_PATH, PROCESSED_DATA_DIR
from src.extract import extract_all
from src.logger import get_logger
from src.transform import clean_all


def _count_duplicates_removed(table_name: str, dataframe: pd.DataFrame) -> int:
    """Count exact duplicate rows and review-ID duplicates removed by cleaning."""
    exact_duplicates = int(dataframe.duplicated().sum())
    if table_name != "order_reviews" or "review_id" not in dataframe.columns:
        return exact_duplicates

    unique_rows = dataframe.drop_duplicates()
    review_ids = unique_rows.loc[unique_rows["review_id"].notna(), "review_id"]
    return exact_duplicates + int(review_ids.duplicated().sum())


def run_stage2() -> pd.DataFrame:
    """Extract and clean raw tables, write processed CSVs, and return the summary."""
    logger = get_logger(__name__)
    tables = extract_all()
    cleaned_tables = clean_all(tables)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict[str, int | str]] = []
    for table_name, cleaned_dataframe in cleaned_tables.items():
        original_dataframe = tables[table_name]
        output_path = PROCESSED_DATA_DIR / f"{table_name}.csv"
        cleaned_dataframe.to_csv(output_path, index=False)
        summary_row: dict[str, int | str] = {
            "table": table_name,
            "rows_before": len(original_dataframe),
            "rows_after": len(cleaned_dataframe),
            "duplicates_removed": _count_duplicates_removed(
                table_name, original_dataframe
            ),
            "null_cells_before": int(original_dataframe.isna().sum().sum()),
            "null_cells_after": int(cleaned_dataframe.isna().sum().sum()),
        }
        summary_rows.append(summary_row)
        logger.info(
            "Saved %s: rows_before=%d rows_after=%d duplicates_removed=%d",
            output_path.name,
            summary_row["rows_before"],
            summary_row["rows_after"],
            summary_row["duplicates_removed"],
        )

    summary = pd.DataFrame(
        summary_rows,
        columns=[
            "table",
            "rows_before",
            "rows_after",
            "duplicates_removed",
            "null_cells_before",
            "null_cells_after",
        ],
    )
    summary.to_csv(CLEANING_SUMMARY_PATH, index=False)
    logger.info("Stage 2 completed. Summary saved to %s", CLEANING_SUMMARY_PATH)
    return summary


def main() -> None:
    """Run Stage 2 as a command-line step with logged failure handling."""
    logger = get_logger(__name__)
    try:
        run_stage2()
    except Exception as error:
        logger.error("Stage 2 pipeline failed: %s", error)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()