# Database

Use PostgreSQL with the dedicated `archy` schema. Runtime credentials identify `archy_api_runtime`; migrations identify `archy_api_migrator`. Bootstrap credentials prepare only an unused namespace and independent roles. The bootstrap command refuses an existing namespace or role; it does not reset an existing database.

Copy `.env.migrations.example` into a private `.env.migrations` file and set the migration URL. Hosted URLs use the project-specific pooler username, `sslmode=verify-full` and an existing `sslrootcert` file. Use direct PostgreSQL or the Supabase session pooler. Untrusted query options and privilege-changing URL parameters are rejected.

```sh
.venv-fastapi/bin/python -m scripts.bootstrap_db --env .env.bootstrap
.venv-fastapi/bin/python -m scripts.migrate_db .env.migrations
```

The migration tool compares every managed legacy column, constraint and index—including varchar_pattern_ops—before stamping the baseline. A mismatch stops adoption; it is not hidden by autogeneration. A fresh, bootstrapped namespace receives the baseline directly. The next revisions add opaque sessions/action tokens and the nullable upload duration snapshot. Inventory checks recognize only that exact additional column and positive-limit constraint as a pair. Existing domain IDs, password bytes, rows and files remain intact.

The ORM maps only the five original domain tables and the new auth tables. Unrelated framework tables remain in PostgreSQL outside Alembic management. Runtime grants cover only managed tables, never DDL or migration/framework history. Migration commands use a single NullPool connection and refresh the explicit grants.

PostgreSQL reflection treats the current search-path schema as implicit. Alembic comparison tests use public as the comparison path/default schema while models explicitly name archy. Runtime sessions use search_path=archy. Independent metadata comparison verifies the actual constraints and indexes in either case.

## Connection budget

One application worker uses at most five connections. Reserve two for administration/migrations and keep external headroom. Increasing workers requires reviewing both PostgreSQL and the provider session-pool size; the configured budget must cover `workers * 5 + 2`.

Inspection on 2026-10-12 confirmed hosted max_connections=60, three superuser-reserved connections, an unlimited runtime role and ten current connections before cutover. The user confirmed the shared session pool size is 15 per user/database, with 200 maximum clients. One runtime worker uses five connections, with two reserved for migration/administration, leaving external headroom. Client TLS uses verify-full and the configured CA. The framework cutover passed with this budget.

Supabase distinguishes server connections, pool size and maximum pooler clients. See [connection management](https://supabase.com/docs/guides/database/connection-management) and [pooling limits](https://supabase.com/docs/guides/database/connecting-to-postgres/pooling-and-limits).

When enabling processing, validate `UVICORN_WORKERS * 5 + PROCESSING_WORKERS * 2 + 2` across processes. One API worker plus one processing worker requires budget 9. Revision `0004_processing` adds only processing tables and grants; it leaves existing rows and upload policies unchanged. Deploy the migration before activating new code.
