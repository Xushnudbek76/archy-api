# Courses

Course endpoints require an active Django session. POST and PATCH additionally require the
CSRF cookie and `X-CSRFToken` header. Responses are private and never cached.

| Method | Endpoint | Body / query | Result |
| --- | --- | --- | --- |
| GET | `/v1/courses` | `archived=false`, `page=1` | Up to 20 courses, newest first |
| POST | `/v1/courses` | `{ "title": "Linear algebra" }` | Created course (201) |
| PATCH | `/v1/courses/{uuid}` | `{ "title": "Calculus" }` | Renamed active course |
| POST | `/v1/courses/{uuid}/archive` | `{}` | Archived course |

A course contains `id`, `title`, `archivedAt` (nullable), `createdAt` and `updatedAt`.
List responses contain `items`, `total` and `nextPage` (nullable). No private backend URLs
or owner details are returned. Page size is fixed at 20; invalid queries return 400 and
out-of-range pages return 404.

Titles are trimmed and must contain 1–100 characters. Unsupported fields are rejected.
Ownership always comes from the authenticated user; clients cannot set it. Foreign and
missing course IDs both return 404. Staff use these endpoints with the same ownership rules.

Archiving keeps the database record and moves it out of the active list. An archived course
cannot be renamed. Repeating archive returns the existing archived course without changing
its timestamps. Rename and archive lock the owned row inside a transaction to serialize writes.
Restoring and deleting courses are outside this step.

The existing model and database grants support these endpoints; no new migration is needed.
Feature tests cover persistence, two-user isolation, CSRF, strict validation, pagination and
archive behavior using only the disposable loopback `archy_api_test` database.
