"""Airflow orchestration for bounded mock social-image ingestion batches."""

from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
from typing import Any

import pendulum
from airflow.decorators import dag, task
from airflow.exceptions import AirflowException
from airflow.utils.state import State
from airflow.utils.trigger_rule import TriggerRule

from crawltech.config import Settings
from crawltech.main import create_runtime
from crawltech.models.schemas import CrawledAuthor

DEFAULT_ARGS = {
    "owner": "crawltech",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "execution_timeout": timedelta(minutes=30),
}


@dag(
    dag_id="crawltech_social_image_pipeline",
    description="Ingest mock social posts and images, analyze them, and build trend data.",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["crawltech", "local-prototype"],
)
def crawltech_social_image_pipeline() -> None:
    """Validate settings, map bounded author batches, and run quality and analytics."""

    @task
    def validate_configuration() -> int:
        """Validate app settings before creating any run or touching the database."""
        return Settings().crawl_batch_size

    @task
    def start_run(batch_size: int) -> str:
        """Create the durable operational run record."""
        del batch_size
        with create_runtime() as runtime:
            return runtime.repository.start_run()

    @task
    def discover_author_batches(batch_size: int) -> list[dict[str, Any]]:
        """Return bounded, JSON-safe author records for dynamic task mapping."""
        with create_runtime() as runtime:
            batches = runtime.ingestion.discover_batches(batch_size)
        if not batches:
            batches = [[]]
        return [
            {
                "batch_number": batch_number,
                "authors": [author.model_dump(mode="json") for author in authors],
            }
            for batch_number, authors in enumerate(batches)
        ]

    @task
    def ingest_author_batch(crawl_run_id: str, batch: dict[str, Any]) -> dict[str, int]:
        """Crawl, persist, store and analyze one bounded author batch idempotently."""
        authors = [CrawledAuthor.model_validate(value) for value in batch["authors"]]
        with create_runtime() as runtime:
            report = runtime.ingestion.process_batch(crawl_run_id, batch["batch_number"], authors)
        return asdict(report)

    @task
    def check_data_quality(crawl_run_id: str) -> dict[str, int]:
        """Persist and enforce post-ingestion referential and image-file checks."""
        with create_runtime() as runtime:
            report = runtime.quality.run(crawl_run_id)
        return asdict(report)

    @task
    def build_trend_dataset(crawl_run_id: str) -> int:
        """Materialize the local trend-ready dataset through the warehouse port."""
        with create_runtime() as runtime:
            return runtime.warehouse.build_trend_dataset(crawl_run_id)

    @task
    def validate_final_output() -> bool:
        """Fail the run when the materialized trend output violates its contract."""
        with create_runtime() as runtime:
            valid = runtime.warehouse.validate_trend_dataset()
        if not valid:
            raise AirflowException("Trend-ready dataset validation failed")
        return True

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def finalize_run(crawl_run_id: str) -> None:
        """Persist terminal status even when a prior task failed or was skipped."""
        from airflow.operators.python import get_current_context

        context = get_current_context()
        task_instances = context["dag_run"].get_task_instances()
        required_instances = [
            instance for instance in task_instances if instance.task_id != "finalize_run"
        ]
        succeeded = all(instance.state == State.SUCCESS for instance in required_instances)
        batch_values = context["ti"].xcom_pull(task_ids="ingest_author_batch")
        if isinstance(batch_values, dict):
            batch_values = [batch_values]
        if not isinstance(batch_values, list):
            batch_values = []
        posts_seen = sum(int(value.get("posts_seen", 0)) for value in batch_values if value)
        images_seen = sum(int(value.get("images_seen", 0)) for value in batch_values if value)
        with create_runtime() as runtime:
            runtime.repository.finish_run(
                crawl_run_id,
                "succeeded" if succeeded else "failed",
                posts_seen,
                images_seen,
            )
        if not succeeded:
            raise AirflowException("One or more required pipeline tasks did not succeed")

    batch_size = validate_configuration()
    run_id = start_run(batch_size)
    batches = discover_author_batches(batch_size)
    batch_results = ingest_author_batch.partial(crawl_run_id=run_id).expand(batch=batches)
    quality_result = check_data_quality(crawl_run_id=run_id)
    trend_count = build_trend_dataset(crawl_run_id=run_id)
    final_validation = validate_final_output()
    finalization = finalize_run(crawl_run_id=run_id)

    batch_results >> quality_result >> trend_count >> final_validation >> finalization


crawltech_social_image_pipeline()
