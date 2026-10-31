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
