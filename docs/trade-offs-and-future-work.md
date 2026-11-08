# Trade-offs and Future Work

## Deliberate prototype choices

- The crawler and analyzer are deterministic mocks: the data and workflow are realistic enough to test contracts without scraping or calling a vision API.
- PostgreSQL and a local filesystem make development self-contained. In production, Snowflake remains the target analytical warehouse; PostgreSQL is only the operational/local implementation.
- SQLAlchemy repository methods use explicit transactions and natural keys. They favor clarity over high-throughput bulk ingestion; batching and upsert statements are a next optimization.
- Airflow `LocalExecutor` is a real scheduler/task-execution setup suitable for a single-machine assessment. It is not a distributed production executor.
- The local trend table is a rebuildable demonstration. Snowflake SQL in `sql/transformations/trend_dataset.sql` is representative production SQL and has not been executed against Snowflake.

## Before production

1. Replace mocks with API-compliant crawler/analyzer clients, credential management, request budgets, and source-specific cursor semantics.
2. Put images in durable object storage, persist object version/ETag and checksum, and define retention and access controls.
3. Implement a Snowflake warehouse adapter with staged bulk loads, idempotent `MERGE`, schema evolution, least-privilege roles, and load audit records.
4. Add concurrency-safe assignment constraints and temporal overlap validation for the production database, plus point-in-time segment attribution where the business requires historical rather than current membership.
5. Add production secrets, network/TLS policies, backups, retention, alerting, data contracts, and measured capacity/load tests.
6. Scale orchestration only after measuring bottlenecks; use bounded partitions, pools, and backpressure. Kubernetes, Kafka, and infrastructure-as-code are intentionally outside this assessment prototype.
