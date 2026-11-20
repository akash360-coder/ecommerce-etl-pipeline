"""Run the complete Olist ETL pipeline with timed steps and a JSON summary."""

import argparse
import importlib
import json
import os
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _run_step(
    logger: Any,
    step_name: str,
    operation: Callable[[], object],
    step_results: dict[str, dict[str, object]],
) -> tuple[bool, object | None]:
    """Run one operation, log timing, and record its status and failure detail."""
    logger.info("Step %s started.", step_name)
    started_at = time.perf_counter()
    result: object | None = None
    error_message: str | None = None
    try:
        result = operation()
        status = "SUCCESS"
    except (Exception, SystemExit) as error:
        status = "FAILED"
        error_message = str(error) or error.__class__.__name__
        logger.error("Step %s failed: %s", step_name, error_message)
    duration = round(time.perf_counter() - started_at, 3)
    step_result: dict[str, object] = {
        "status": status,
        "duration_seconds": duration,
    }
    if error_message is not None:
        step_result["error"] = error_message
    step_results[step_name] = step_result
    logger.info(
        "Step %s ended with status=%s duration_seconds=%.3f.",
        step_name,
        status,
        duration,
    )
    return status == "SUCCESS", result


def _write_run_summary(summary_path: Path, summary: dict[str, object]) -> None:
    """Write a readable JSON run summary, creating its parent directory."""
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_pipeline(sample: bool = False) -> int:
    """Run validation, extraction, cleaning, loading, checks, and dashboard export."""
    from src import config

    if sample:
        os.environ["ETL_RAW_DIR"] = str(config.SAMPLE_RAW_DATA_DIR)
        os.environ["ETL_OUTPUT_DIR"] = str(config.SAMPLE_OUTPUT_DIR)
        os.environ["ETL_DB_PATH"] = str(config.SAMPLE_DATABASE_PATH)
        importlib.reload(config)

    from src.logger import get_logger

    logger = get_logger(__name__)
    summary: dict[str, object] = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "RUNNING",
        "steps": {},
        "row_counts": {},
        "quality_check_counts": {"passed": 0, "failed": 0},
    }
    step_results = summary["steps"]
    if not isinstance(step_results, dict):
        raise RuntimeError("Invalid run summary initialization")
    pipeline_started_at = time.perf_counter()
    logger.info(
        "Pipeline run started: sample=%s raw_dir=%s output_root=%s database=%s",
        sample,
        config.RAW_DATA_DIR,
        config.OUTPUT_ROOT,
        config.DATABASE_PATH,
    )

    def validate_raw() -> None:
        """Validate configured raw source files."""
        from src.validate_raw import main as validate_raw_main

        validate_raw_main()

    def extract_transform() -> object:
        """Run the reusable Stage 2 extract and clean step."""
        from src.run_stage2 import run_stage2

        return run_stage2()

    pipeline_state: dict[str, object] = {}

    def load_star_schema() -> dict[str, int]:
        """Build the star-schema frames and load them into the configured SQLite DB."""
        from src.load import build_star_schema, load_dataframes, read_cleaned_tables

        source_tables = read_cleaned_tables(config.PROCESSED_DATA_DIR)
        schema_frames = build_star_schema(source_tables)
        row_counts = load_dataframes(
            schema_frames,
            database_path=config.DATABASE_PATH,
            schema_path=config.SCHEMA_SQL_PATH,
        )
        pipeline_state["source_tables"] = source_tables
        pipeline_state["schema_frames"] = schema_frames
        summary["row_counts"] = row_counts
        return row_counts

    def run_quality_checks() -> dict[str, int]:
        """Run Stage 3 data-quality checks and stop if any check fails."""
        from src.run_stage3 import run_quality_checks as check_loaded_data

        source_tables = pipeline_state["source_tables"]
        schema_frames = pipeline_state["schema_frames"]
        if not isinstance(source_tables, dict) or not isinstance(schema_frames, dict):
            raise RuntimeError("Loaded data is unavailable for quality checks")
        report = check_loaded_data(
            source_tables,
            schema_frames,
            database_path=config.DATABASE_PATH,
            report_path=config.LOAD_QUALITY_REPORT_PATH,
        )
        passed = int(report["status"].eq("PASS").sum())
        failed = int(report["status"].eq("FAIL").sum())
        summary["quality_check_counts"] = {"passed": passed, "failed": failed}
        if failed:
            failed_names = report.loc[report["status"] == "FAIL", "check_name"]
            raise RuntimeError(f"Quality checks failed: {', '.join(failed_names)}")
        return {"passed": passed, "failed": failed}

    def export_dashboard() -> dict[str, tuple[int, list[str]]]:
        """Run the existing dashboard exporter into the configured output root."""
        from sqlalchemy.engine import URL
        from sqlalchemy import create_engine

        from src.export_dashboard_data import export_dashboard_data

        engine = create_engine(URL.create("sqlite", database=str(config.DATABASE_PATH)))
        try:
            return export_dashboard_data(engine, config.DASHBOARD_DATA_DIR)
        finally:
            engine.dispose()

    operations: tuple[tuple[str, Callable[[], object]], ...] = (
        ("validate_raw", validate_raw),
        ("extract_transform", extract_transform),
        ("load_star_schema", load_star_schema),
        ("quality_checks", run_quality_checks),
        ("dashboard_export", export_dashboard),
    )
    successful = True
    for step_name, operation in operations:
        step_succeeded, _ = _run_step(
            logger, step_name, operation, step_results
        )
        if not step_succeeded:
            successful = False
            break

    summary["status"] = "SUCCESS" if successful else "FAILED"
    summary["duration_seconds"] = round(time.perf_counter() - pipeline_started_at, 3)
    try:
        _write_run_summary(config.PIPELINE_RUN_SUMMARY_PATH, summary)
        logger.info("Run summary written to %s", config.PIPELINE_RUN_SUMMARY_PATH)
    except OSError as error:
        logger.error("Could not write pipeline run summary: %s", error)
        successful = False
        summary["status"] = "FAILED"

    logger.info(
        "Pipeline run ended with status=%s duration_seconds=%.3f.",
        summary["status"],
        summary["duration_seconds"],
    )
    return 0 if successful else 1


def main(argv: list[str] | None = None) -> int:
    """Parse command-line options and run the selected pipeline configuration."""
    parser = argparse.ArgumentParser(description="Run the complete Olist ETL pipeline.")
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Use committed sample data and isolate every generated output.",
    )
    arguments = parser.parse_args(argv)
    return run_pipeline(sample=arguments.sample)


if __name__ == "__main__":
    sys.exit(main())
