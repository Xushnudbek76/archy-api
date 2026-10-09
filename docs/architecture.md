# Architecture

Archy uses a modular Django application with a separate Next.js frontend. Each feature app owns
its persistence and HTTP contracts. A single deployable backend keeps transactions and development
simple while preserving boundaries for future features.

```text
Next.js → HTTP views → serializers → account services → Django ORM → PostgreSQL
                                  ↘ Django auth, sessions and email
```

Views select status codes and permissions. Serializers validate input and expose explicit fields.
Account services coordinate confirmation and recovery transactions. Database constraints protect
invariants even when writes come from administration or concurrent requests.

`config` handles validated environment, deployment policy and URL composition. `core` provides
health and safe error formatting. `accounts` owns identity; `courses` owns course persistence.
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
a production WSGI/ASGI server, static file serving, backups and frontend authentication integration.
Current local throttles are approximate per-process admission controls, not a distributed security boundary.
