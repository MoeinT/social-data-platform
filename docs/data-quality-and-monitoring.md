# Data Quality and Monitoring

## Blocking checks

The local quality service persists a result per `(run_id, check_name)` and updates it on retry. It verifies:

- Every persisted image path resolves to a file.
- Post-image and post-author references resolve.
- Posts without images are counted and accepted; posts with multiple images are counted and accepted.
- Analyzer payloads are validated before persistence, including confidence in `[0, 1]` and normalized boxes within image bounds.
- Database constraints protect natural keys, analysis versions, confidence ranges, bounding-box geometry, assignment periods, and nonnegative trend counts.

Broken image files or relational references fail the run. Image-less posts are a valid source state, not a quality failure. The warehouse performs a final uniqueness/count validation before marking the pipeline run successful.

## Operational signals

Application logs use standard Python logging with structured `extra` fields for run and batch IDs. The operational tables retain run status, start/end timestamps, counters, batch status, and named quality results. Airflow task state, retry count, duration, and per-task logs provide the local orchestration view. Compose health checks gate startup on each PostgreSQL service, the Airflow webserver, and scheduler health.

For a production deployment, alert on repeated task failures, stale crawl cursors, ingestion lag, analyzer failure/latency, missing-object rates, and failed/late Snowflake loads. Add run-level metrics and warehouse freshness checks before increasing parallelism. No hosted monitoring service is required by this prototype.