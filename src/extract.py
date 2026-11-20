"""Read the expected Olist source files into pandas DataFrames."""

import pandas as pd

from src.config import EXPECTED_RAW_FILES, RAW_DATA_DIR
from src.logger import get_logger


def extract_all() -> dict[str, pd.DataFrame]:
    """Read every configured raw CSV and return tables keyed by table name.

    Raises:
        FileNotFoundError: If an expected CSV is missing.
        ValueError: If an expected CSV contains no data rows.
    """
    logger = get_logger(__name__)
    tables: dict[str, pd.DataFrame] = {}

    for table_name, filename in EXPECTED_RAW_FILES.items():
        file_path = RAW_DATA_DIR / filename
        if not file_path.is_file():
            logger.error("Required raw CSV is missing: %s", file_path)
            raise FileNotFoundError(f"Required raw CSV is missing: {file_path}")

        try:
            dataframe = pd.read_csv(file_path)
        except pd.errors.EmptyDataError as error:
            logger.error("Required raw CSV is empty: %s", file_path)
            raise ValueError(f"Required raw CSV is empty: {file_path}") from error
        except Exception:
            logger.exception("Could not read raw CSV: %s", file_path)
            raise

        if dataframe.empty:
            logger.error("Required raw CSV has no data rows: %s", file_path)
            raise ValueError(
                f"Required raw CSV has no data rows: {file_path}"
            )

        tables[table_name] = dataframe
        logger.info(
            "Read %s: rows=%d columns=%d",
            table_name,
            len(dataframe),
            len(dataframe.columns),
        )

    return tables