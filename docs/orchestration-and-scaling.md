# Orchestration and Scaling

## Local Airflow

Compose runs pinned Apache Airflow `2.10.5` on Python 3.12 with `LocalExecutor`, a separate persistent PostgreSQL metadata database, a webserver, and a scheduler. The app database has its own PostgreSQL container and volume. The `app-migrate` one-shot service upgrades the app schema before Airflow initialization and scheduler startup.

From the repository root:

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
```

Open `http://localhost:8080` and sign in with `AIRFLOW_ADMIN_USERNAME` / `AIRFLOW_ADMIN_PASSWORD` from `.env` (local defaults: `admin` / `localdev`). The DAG is paused at creation and has no schedule. Unpause `crawltech_social_image_pipeline` and trigger it from the UI, or use:

```bash
docker compose exec airflow-webserver airflow dags unpause crawltech_social_image_pipeline
docker compose exec airflow-webserver airflow dags trigger crawltech_social_image_pipeline
docker compose exec airflow-webserver airflow dags list-runs -d crawltech_social_image_pipeline
```

Task logs are available in the Airflow UI and under `./airflow-logs`. Follow service output with `docker compose logs -f airflow-scheduler airflow-webserver`. Stop services while preserving state using `docker compose down`; remove local database volumes only when intentionally resetting the data using `docker compose down -v`. The image directory is bind-mounted at `./data/images` and is not removed by `down -v`.

## Task boundaries

The DAG validates settings, creates a durable run, discovers bounded author batches, maps one task per author batch, then runs persisted quality checks, trend materialization, final validation, and terminal run-state persistence. The default local batch size is five authors and configuration caps it at 100. A mapped task never corresponds to a post or image. XCom carries serialized author metadata and small counters/IDs only; image bytes and bulk result sets stay in storage and databases.

Mapped ingestion tasks use two retries and a 30-minute execution timeout. Repository natural keys and versioned-analysis constraints make retrying an interrupted batch safe. `max_active_runs=1` keeps the local full-rebuild materialization simple; production can increase concurrency after adding run-scoped staging, warehouse merge semantics, and resource limits.

## Production scaling path

For higher volume, partition crawler work by source/network cursor and bounded author ranges; store cursor/checkpoint state durably. Move images from a shared local volume to object storage and send only object URIs to analyzers. Keep batches sized to API and database throughput, apply per-adapter rate limits, and use bulk writes. Load changed operational records into Snowflake through CDC or an idempotent staged extract keyed by stable IDs and `updated_at`/version timestamps. Merge dimensions and facts on natural/surrogate keys, then incrementally refresh trend transformations. Airflow orchestrates these operations; it is not the bulk data transport layer.