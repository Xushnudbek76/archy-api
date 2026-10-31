# Demo workspace

The demo uses a reserved ordinary account with two original sample PDFs, saved notes,
five-question quizzes and saved tutor exchanges. Results have `provider: demo`: they
are hand-written examples, not proof of live model quality. No provider call is made.

Use a separate demo database prepared through the existing bootstrap/migration commands.
Copy `.env.example` to a private `.env.demo`, configure that database and private media
volume, then explicitly set `DEMO_ENABLED=true` before running:

```sh
.venv-fastapi/bin/python -m scripts.seed_demo --env .env.demo --confirm-demo
```

The command refuses a conflicting reserved account and can be repeated without duplicating
rows. It never resets or deletes accounts. Existing sample PDFs must match the original
bytes; mismatched files require inspection instead of an automatic overwrite. Database
configuration and credentials are never included in command output.

`GET /v1/demo` advertises availability only when the flag and active sample account
are present. `POST /v1/demo/session` requires the normal Origin and CSRF checks and
returns an ordinary HttpOnly session lasting 15 minutes. Existing regular sessions
are never replaced. A shared per-process entry limiter and a maximum of 100 active
demo sessions bound admission; deploy an ingress limiter as well.

All resource writes, including binary uploads and tutor generation, reject sample
sessions before reading input bytes or calling a provider. Logout revokes only the
current visitor's session. Turning the flag off blocks existing sample sessions on
the next resource request. Normal users still have private, writable workspaces.
