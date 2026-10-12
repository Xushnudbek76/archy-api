# Verification

Use a disposable loopback PostgreSQL database named `archy_api_test`. All three URLs must pass the test role/host/database guards. CI creates PostgreSQL 17, bootstraps independent roles and applies reviewed migrations before running the checks.

Backend checks:

```sh
.venv-fastapi/bin/python -m ruff check .
.venv-fastapi/bin/python -m ruff format --check .
.venv-fastapi/bin/python -m pytest
.venv-fastapi/bin/python -m pip check
```

Set `PG_BIN` to the directory containing compatible `pg_dump` and `pg_restore` for the snapshot recovery check. CI installs PostgreSQL 17 clients explicitly. Without client tools the recovery check is skipped; the remaining database tests still run.

Tests cover legacy password compatibility, token races, cookies/CSRF, owner isolation, schema adoption, runtime privilege separation, resumable uploads, checksum/publication retries, actual media probing and Range/HEAD behavior. Actual Uvicorn tests hold audio streams open, saturate the five-connection pool and require local liveness under 500 ms. They hold four request bodies open, prove a fifth gets 429 before sending bytes and confirm disconnection releases slots. Streaming oversized-body tests use 20/100 MiB generators and verify bounded memory.

For real frontend verification, run the guarded test API in one terminal:

```sh
.venv-fastapi/bin/python -m scripts.test_server
```

In `../archy-next`:

```sh
REAL_API=1 AUTH_EMAIL_DIR=/Users/user/Desktop/archy-api/.local/recordings-test-mail npm run test:e2e
```

Set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` if using an installed browser. The test server binds only loopback, uses private fixture mail and relaxes account limits for multi-account scenarios. Separate tests verify the ordinary limits. Run browser flows and transactional suites sequentially; browser-created rows persist until guarded cleanup.

Evidence from 2026-10-11/12: the corrected Django baseline passed 129 tests. The final FastAPI suite passed 116 tests, including a private PostgreSQL snapshot/restore rehearsal and review regressions for stale reset links, invalid-token hashing, shutdown cancellation and missing authentication schema/grants. Frontend checks passed 45 tests, formatting, lint, types and a production build. The real FastAPI browser suite passed 11 tests, with two fixture-only fault scenarios skipped. It included account recovery, courses, private hours-long audio/resume/seek, temporary overload recovery and a progressing upload lasting over three minutes. Normalized comparison matched all 28 captured legacy responses; logout deliberately preserves HttpOnly on the deletion cookie as required by the new cookie policy.

The independent duration-policy checks cover frozen admission limits, restart/configuration changes, null legacy backfill, exact tolerance, terminal cleanup, missing-duration browser WebM/Opus and probe-resource failures. Actual 900/1200-second Opus files remuxed from browser packets passed fallback measurement; actual MP3, AAC/M4A, FLAC and Opus/Ogg encoding/probe cases all passed under the unchanged subprocess limits. These generated fixtures are disposable and do not replace the committed short browser capture. The policy browser suite passed 12 tests with two fixture-only skips, including a rejected long new upload followed by a fresh accepted browser recording and explicit legacy three-hour resume/privacy. Frontend policy checks passed 48 tests and a production build.

Legacy fixtures are synthetic and contain no real passwords, DSNs or links. Their generators require the legacy Django checkout at commit `3ca101fb0de0723a4a299387f687df76f977e7e1` with the fixture scripts copied into it; run only against the guarded disposable database. They are evidence-generation tools, not application runtime modules.

Final policy release verification on 2026-10-12: 144 backend tests passed, including the missing-policy-column readiness regression; 48 frontend tests/build/types/lint/format passed; 12 real browser tests passed with two fixture-only skips. Hosted `0003_duration_policy` application preserved existing row digests and null legacy policy snapshots. Verified TLS, main API liveness/readiness 200, authenticated policy read protected with 403 for anonymous callers, and the Next.js proxy/login/recordings routes.
