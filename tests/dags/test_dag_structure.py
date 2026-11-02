"""Airflow DAG import and structural checks; skipped in the lightweight dev extra."""

from pathlib import Path

import pytest


def test_pipeline_dag_imports_without_errors() -> None:
    """The scheduler can parse the DAG module and resolve the expected DAG ID."""
    pytest.importorskip("airflow")
    from airflow.models import DagBag

    dag_file = Path(__file__).parents[2] / "dags" / "crawltech_pipeline.py"
    dag_bag = DagBag(dag_folder=str(dag_file), include_examples=False)

    assert dag_bag.import_errors == {}
    dag = dag_bag.get_dag("crawltech_social_image_pipeline")
    assert dag is not None
    assert dag.task_ids == [
        "build_trend_dataset",
        "check_data_quality",
        "discover_author_batches",
        "finalize_run",
        "ingest_author_batch",
        "start_run",
        "validate_configuration",
        "validate_final_output",
    ]
    assert dag.get_task("ingest_author_batch").retries == 2
    assert dag.get_task("finalize_run").trigger_rule == "all_done"
