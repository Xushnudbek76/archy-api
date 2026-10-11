# Architecture

Archy uses a modular Django application with a separate Next.js frontend. Each feature app owns
its persistence and HTTP contracts. A single deployable backend keeps transactions and development
simple while preserving boundaries for future features.

```text
Next.js → HTTP views → serializers → feature services → Django ORM → PostgreSQL
                                  ↘ Django auth, sessions and email
```

Views select status codes and permissions. Serializers validate input and expose explicit fields.
Feature services coordinate account, course and recording transactions. Database constraints protect
invariants even when writes come from administration or concurrent requests.

`config` handles validated environment, deployment policy and URL composition. `core` provides
health, strict input validation and safe error formatting. `accounts` owns identity; `courses`
owns persistence and owner-scoped create, list, rename and archive workflows.
Django administration is a restricted staff interface. No generic repository layer is needed
because Django already supplies an ORM and transaction boundaries.

## Database boundary

All application tables, including sessions and Django metadata, live in private schema `archy`.
The migration role owns this namespace. The API uses a separate role with table DML and sequence
usage; it cannot create application objects or read migration history. Migration commands refresh
runtime grants after schema changes. Bootstrap refuses existing namespace/role names.

Hosted connections require certificate and hostname verification. Connection, statement and lock
waits are bounded. Credential files, virtual environments, local emails and scratch files are ignored.

## Identity boundary

Django passwords and persisted sessions are authoritative. Public input cannot set account
permissions. Staff role is derived from the current database row on each request. Email confirmation
uses a separate pending signup attempt so the confirmed link selects its own credentials. Provisioned
or previously confirmed disabled accounts cannot re-enter signup. Confirmation records completion and
discards pending attempts, preventing replay.
Password-reset tokens are validated under a row lock and become invalid after the password changes.
Existing sessions lose authorization through Django's password-authentication hash check.

## Deployment boundary

Run behind HTTPS with explicit hosts and a same-site frontend or same-origin session proxy.
Production settings enable secure cookies, redirects and HSTS. Do not trust arbitrary forwarded
headers; terminate TLS at a server whose forwarding policy is explicitly configured.

Before public deployment: configure SMTP, a shared cache and edge admission limits, observability,
a production WSGI server, static file serving and backups.
Current local throttles are approximate per-process admission controls, not a distributed security boundary.

## Recording boundary

`recordings` owns upload state, course-scoped metadata, audio validation and private playback.
Its storage module handles disk paths and atomic file operations; PostgreSQL holds ownership
and confirmed offsets. The frontend transfers bounded chunks and streams playback through
fixed same-origin routes. No public file directory or credential-bearing playback URL is used.
See [recording storage](recordings.md) for persistent-volume and WSGI deployment requirements.
