# Verification

The foundation is verified through real PostgreSQL model, permission and API tests. Auth clients
enforce CSRF, and email is in-memory during tests. Hosted checks are read-only after migrations;
destructive tests run exclusively against loopback `archy_api_test`.

Covered behavior includes case-insensitive email uniqueness, title/ownership constraints,
credential validation, liveness without a database, readiness against migrated tables, anonymous
CSRF enforcement, privilege-field rejection, session rotation/logout, recovery-token expiry/replay,
password-reset session invalidation, disabled-user behavior and per-IP admission limits.

Release gates: full pytest, Ruff lint/format, Django system checks, no migration drift, production
configuration checks, hosted verified-TLS readiness, runtime privilege inspection and GitHub CI.

A fresh read-only review of the complete initial project runs before publication. Any material
findings are addressed with regression tests. Frontend/browser login and public deployment are
separate work; backend tests do not establish those flows as complete.

## Initial verification — 2026-10-09

- Full suite: 62 passing tests on isolated PostgreSQL 18.4.
- Ruff lint and formatting: passed.
- Django system check and production deployment check: no issues.
- Migration drift: no changes detected; migrations applied from empty locally and hosted.
- Separate runtime API process: liveness and hosted readiness returned HTTP 200.
- Production-config WSGI process: HTTPS-scheme liveness/readiness returned 200.
- Hosted runtime: table DML allowed; schema creation and migration-history reads denied.
- Supabase `anon`/`authenticated`: no usage on the private application namespace.
- Existing Next.js checkout: unchanged and clean.

The independent whole-project review identified signup-attempt binding, disabled-account activation,
private email storage, runtime command compatibility and admin email normalization issues. Regression
tests failed before the corrections and passed afterward. Password recovery also now checks the actual
account's password policy. Both orderings of competing signup attempts are tested.

Runtime staff provisioning passed against the disposable database. GitHub PostgreSQL 17 CI is checked
after publication.
