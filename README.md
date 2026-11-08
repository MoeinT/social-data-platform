# social-data-platform

A local prototype for social post/image ingestion, versioned image analysis, segment history, and trend-ready analytics. The crawler and analyzer are deterministic mocks; the production analytical warehouse target is **Snowflake**. PostgreSQL is the local operational store and does not replace Snowflake.

## Requirements

- Python 3.12 and [`uv`](https://docs.astral.sh/uv/)
- Docker Engine with Docker Compose v2 (for PostgreSQL and Airflow)

## Install

```bash
uv sync --extra dev
cp .env.example .env
```

## Run locally without Airflow

Start the application PostgreSQL database:

```bash
docker compose up -d app-db
docker compose ps app-db
```

Apply the schema and run the complete mock pipeline:

```bash
uv run alembic upgrade head
uv run python scripts/generate_sample_data.py
```

The run persists operational metadata and analysis in PostgreSQL, image files in `./data/images`, quality results in the database, and a rebuildable local weekly trend table. `uv run crawltech` is an equivalent CLI entry point. Stop only the app database with `docker compose stop app-db`.

## Run with Airflow

Build and start PostgreSQL, Airflow metadata storage, initialization, webserver, and scheduler:

```bash
docker compose up --build -d
docker compose ps
```

Open [http://localhost:8080](http://localhost:8080) and sign in using `AIRFLOW_ADMIN_USERNAME` and `AIRFLOW_ADMIN_PASSWORD` in `.env` (`admin` / `localdev` by default). Unpause and trigger the manual DAG:

```bash
docker compose exec airflow-webserver airflow dags unpause crawltech_social_image_pipeline
docker compose exec airflow-webserver airflow dags trigger crawltech_social_image_pipeline
docker compose exec airflow-webserver airflow dags list-runs -d crawltech_social_image_pipeline
```

Inspect task output in the Airflow UI or tail service logs with `docker compose logs -f airflow-scheduler airflow-webserver`. Task logs are also mounted under `./airflow-logs`. The DAG maps bounded author batches; it does not create one task per post or image.

## Tests and checks

```bash
uv run ruff check src dags tests
uv run ruff format --check src dags tests
uv run mypy src/crawltech
uv run pytest -q
```

The default test suite is deterministic and uses in-memory SQLite. To run the PostgreSQL integration test against the Compose database:

```bash
docker compose up -d app-db
CRAWLTECH_TEST_DATABASE_URL=postgresql+psycopg2://crawltech:crawltech@localhost:5433/crawltech uv run pytest -m integration -q
```

The DAG structural test runs when Airflow is installed; the CI workflow additionally parses it inside the pinned Airflow Compose image. Install pre-commit hooks locally with `uv run pre-commit install`.

## Stop and clean up

```bash
docker compose down
```

That stops containers while preserving database volumes and generated image files. To remove both PostgreSQL databases and reset Airflow metadata:

```bash
docker compose down -v
```

Image files remain under `./data/images`; remove that directory manually when you intentionally want to delete generated samples. Local Compose credentials are for development only; change them before exposing services beyond localhost.

## Design notes

- [Architecture](docs/architecture.md)
- [Data model](docs/data-model.md)
- [Orchestration and scaling](docs/orchestration-and-scaling.md)
- [Data quality and monitoring](docs/data-quality-and-monitoring.md)
- [Trade-offs and future work](docs/trade-offs-and-future-work.md)
- [Snowflake trend transformation SQL](sql/transformations/trend_dataset.sql), representative and not executed against Snowflake
