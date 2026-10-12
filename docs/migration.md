# FastAPI migration

The migration keeps the existing account, course, upload and recording tables and their files. SQLAlchemy maps their original PostgreSQL constraints and indexes. The migration tool checks the schema before adopting it; the API never changes schema at startup.

At cutover, users sign in again. Existing Django sessions and pending confirmation/reset links are not accepted by the replacement. Pending links must be requested again. Password hashes remain usable and upgrade to Argon2id after successful login.

Chunk reception may return 429 with Retry-After when four uploads are already receiving data in a worker. The frontend retries that same chunk with bounded delays. Paused uploads remain resumable. Duration policy is introduced only after framework parity is verified.

## Administration

The registered legacy AccountAdmin supports searching email/profile, inspecting and editing email, display name, password, active/staff/superuser state and last login. It exposes framework groups and user permissions; the application itself does not use those permissions. CourseAdmin supports listing/filtering archival state, searching titles, selecting an owner and editing course fields. No recording administrator is registered. These registrations describe capabilities, not evidence of previous operator activity.

The replacement uses trusted local administration commands with hidden password prompts. Framework groups and permission tables stay in the database outside Alembic management; no replacement HTTP administrator is exposed.

## Verification environments

All synthetic data and destructive rehearsals use the guarded loopback archy_api_test database. Browser flows and transactional tests run sequentially because browser-created accounts persist until explicit cleanup. The Django and FastAPI virtual environments stay separate during migration.

Default account limits use the immediate peer address. Through the Next.js proxy this is a shared bucket, and is not sufficient production brute-force protection. Deployment must add a trusted ingress/account limit before public use.

## Framework cutover

The framework switch completed on 2026-10-12 after exact schema comparison, full local verification and confirmation of the seven-connection budget against the 15-connection session pool. Django was stopped before the private snapshot/media backup. Baseline adoption and the additive auth migration were applied separately from runtime startup. Existing domain rows and password bytes matched their pre-cutover digests. FastAPI now runs as one worker on port 3007; liveness/readiness and the Next.js proxy passed. The old runtime/configuration is preserved privately for reviewed snapshot recovery.

After the budget is established, stop the existing Django writer, take a consistent private PostgreSQL snapshot and copy the private media while writes are quiescent. Preserve old runtime/configuration separately. Apply the reviewed adoption/auth revisions with migration credentials, start one FastAPI worker and verify TLS, readiness, existing rows and private files before normal traffic.

`python -m scripts.snapshot_db --env .env.migrations --pg-bin /path/to/postgresql/bin` creates a custom-format `archy` schema snapshot in `.local/backups`. The directory is 0700 and dump file is 0600. PostgreSQL client tools must be at least as new as the server. Credentials are passed through the private subprocess environment, never command arguments or logs. Copy media separately while the writer remains stopped.

A rollback is a reviewed pre-cutover snapshot restoration, not transparent rolling rollback. It loses writes made after the snapshot, including password upgrades and new recordings. Restore the matching private files as well as database state. Do not automatically restart Django against passwords upgraded to Argon2id without a compatible legacy verifier.

## Duration policy release

The separate `0003_duration_policy` migration adds only the nullable duration snapshot and positive constraint. It was applied after an additional quiesced private database/media backup and independent format/browser verification. Existing rows, passwords and session/token data matched their pre-policy digests; old upload snapshots stayed null. New admissions use 1200 seconds by default. Set MAX_AUDIO_DURATION_SECONDS=900 and restart the API for 15 minutes; already admitted uploads keep their original snapshot. Readiness verifies every mapped column, so an unapplied policy column cannot report healthy.
