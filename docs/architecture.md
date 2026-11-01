# Architecture

The Next.js frontend handles presentation and same-origin cookie transport. FastAPI owns authentication, courses, recording uploads and private playback. PostgreSQL persists state; private disk storage holds audio bytes.

`app/components` groups accounts, academics, courses, documents, recordings, processing, study, tutor, preferences, OAuth and billing. Each feature has a router, strict input/output schemas, persistence models and small workflow services. `app/libs` contains settings, security, mail, request limits and shared HTTP behavior. `app/database` owns the synchronous engine and session factory. Alembic revisions run through guarded commands, never API startup.

Synchronous routes run database work in the bounded AnyIO worker pool. Async chunk and playback routes call complete worker units for authorization and persistence; each unit closes its session before returning immutable metadata. Chunk reception and network streaming occupy neither a connection nor a worker while awaiting client data. Playback reads at most 64 KiB at a time.

Each worker has 40 AnyIO thread tokens and a PostgreSQL pool of five connections, zero overflow and a two-second checkout timeout. Connection establishment has its own five-second limit, and database statement/lock timeouts are five seconds. These are separate bounds, not a two-second total request deadline. Start one Uvicorn worker and reserve two additional database connections for administration/migrations. The configured connection budget covers `API workers * 5 + processing workers * 2 + 2`; separately scheduled billing commands also need room within the hosted pool.

Four receiving chunk requests are admitted per process. A fifth authorized request receives 429 and Retry-After: 2 before body reads. The frontend retries the same offset and bytes at most three times. Other errors pause for explicit resume; completion requests are not automatically repeated.

The API generates request IDs, logs route templates rather than URLs, hides SQL parameters and returns safe errors. It never logs request bodies, passwords, cookies, tokens or exception messages. A response-stream failure closes the response and logs sanitized diagnostics without appending JSON to audio.

The processing component owns durable PostgreSQL jobs, transcripts and notes. One separate worker uses a two-connection pool, expiring leases and fenced writes; no connection is held during preparation/provider calls. Private disk audio is prepared through bounded PyAV subprocesses. Next.js reads saved status/results through its same-origin proxy. See [processing](processing.md).

Student-facing academic, preference and provider boundaries are documented in [product workspace](product-workspace.md) and [providers and test billing](providers-and-billing.md).
