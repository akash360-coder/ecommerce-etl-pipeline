"""Integration tests for the complete pipeline using committed sample inputs."""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.config import (
    DATABASE_RELATIVE_PATH,
    LOAD_QUALITY_REPORT_PATH,
    PIPELINE_RUN_SUMMARY_RELATIVE_PATH,
    PROCESSED_DATA_RELATIVE_PATH,
    PROJECT_ROOT,
    SAMPLE_RAW_DATA_DIR,
)


def test_pipeline_runs_successfully_with_sample_data_and_temp_outputs(
    tmp_path: Path,
) -> None:
    """The sample pipeline loads all tables and writes valid reports in isolation."""
    output_directory = tmp_path / "sample-output"
    database_path = output_directory / DATABASE_RELATIVE_PATH
    environment = os.environ.copy()
    environment["ETL_RAW_DIR"] = str(SAMPLE_RAW_DATA_DIR)
    environment["ETL_OUTPUT_DIR"] = str(output_directory)
    environment["ETL_DB_PATH"] = str(database_path)

    completed = subprocess.run(
        [sys.executable, "-m", "src.run_pipeline"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    summary_path = output_directory / PIPELINE_RUN_SUMMARY_RELATIVE_PATH
    quality_report_path = output_directory / PROCESSED_DATA_RELATIVE_PATH / (
        LOAD_QUALITY_REPORT_PATH.name
    )
    assert summary_path.is_file()
    assert quality_report_path.is_file()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "SUCCESS"
    assert set(summary["steps"]) == {
        "validate_raw",
        "extract_transform",
        "load_star_schema",
        "quality_checks",
        "dashboard_export",
    }
    assert all(step["status"] == "SUCCESS" for step in summary["steps"].values())
    assert summary["quality_check_counts"]["failed"] == 0

    quality_report = pd.read_csv(quality_report_path)
    assert not quality_report.empty
    assert set(quality_report["status"]) == {"PASS"}
    assert summary["quality_check_counts"]["passed"] == len(quality_report)

    expected_tables = {
        "dim_customers",
        "dim_products",
        "dim_sellers",
        "dim_date",
        "dim_geolocation",
        "fact_sales",
        "fact_payments",
        "fact_reviews",
    }
    with sqlite3.connect(database_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert expected_tables.issubset(table_names)
