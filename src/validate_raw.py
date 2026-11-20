"""Check that all expected raw CSV files exist and can be read."""

import pandas as pd

from src.config import EXPECTED_RAW_FILES, RAW_DATA_DIR
from src.logger import get_logger


def main() -> None:
    """Validate the raw dataset and log basic file-level statistics."""
    logger = get_logger(__name__)
    missing_files = [
        filename
        for filename in EXPECTED_RAW_FILES.values()
        if not (RAW_DATA_DIR / filename).is_file()
    ]

    if missing_files:
        for filename in missing_files:
            logger.error("Missing required raw CSV: %s", RAW_DATA_DIR / filename)
        missing_list = ", ".join(missing_files)
        raise SystemExit(
            "Raw data validation failed. Add the missing CSV file(s) to "
            f"{RAW_DATA_DIR}: {missing_list}"
        )

    for dataset_name, filename in EXPECTED_RAW_FILES.items():
        file_path = RAW_DATA_DIR / filename
        try:
            dataframe = pd.read_csv(file_path)
        except Exception as error:
            logger.exception("Could not read %s", file_path)
            raise SystemExit(
                f"Raw data validation failed while reading {file_path}: {error}"
            ) from error

        null_count = int(dataframe.isna().sum().sum())
        logger.info(
            "%s (%s): rows=%d columns=%d null_cells=%d",
            dataset_name,
            filename,
            len(dataframe),
            len(dataframe.columns),
            null_count,
        )

    logger.info("Raw data validation completed successfully.")


if __name__ == "__main__":
    main()
