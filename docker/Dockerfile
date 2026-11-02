FROM apache/airflow:2.10.5-python3.12

ARG AIRFLOW_VERSION=2.10.5

USER airflow
COPY --chown=airflow:root pyproject.toml README.md ./
COPY --chown=airflow:root src ./src
COPY --chown=airflow:root migrations ./migrations
COPY --chown=airflow:root alembic.ini ./alembic.ini

RUN pip install --no-cache-dir \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-3.12.txt" \
    .

ENV PYTHONPATH="/opt/airflow/src"