# API and worker deployment

This configuration prepares a Linux host; it does not deploy a service or provision a database.
Run the separate Next.js frontend behind the same public HTTPS origin used by
`FRONTEND_ORIGIN`. Keep the API's container port bound to loopback and proxy it through
a trusted HTTPS ingress. Authentication limits must run at that ingress because FastAPI
sees the Next.js peer rather than each browser. Never trust arbitrary browser IP headers.

1. Prepare a separate PostgreSQL database using `docs/database.md`. Use runtime, migration
   and bootstrap credentials separately. Back up an existing schema before migration.
2. Copy `deploy/environment.example` to private `.env.production`; fill real runtime/SMTP
   values and place the database CA at `.local/certificates/ca.pem`. Hosted connections
   require `sslmode=verify-full`. Keep both locations outside source control.
3. Build with `docker compose build api`. The image runs as UID/GID 10001 and copies no
   environment files, tests, caches or local credentials. API startup never migrates.
4. Apply migrations once with migration credentials, using the existing migration command
   and a private configuration whose CA path is valid in that process. Do not grant the
   runtime role schema ownership or migration permissions. Keep runtime and migrations
   on the same reviewed release through `0013_tutor_usage` or later.
5. Start with `docker compose up -d api` and check readiness through the ingress. Confirm
   HTTPS, cookie flags, email confirmation/reset delivery and private file access before
   inviting visitors. Monitor readiness and host disk usage.

The `media` named volume holds private PDFs, recordings and worker files. Back it up with
the database and restore both together; retaining only the database loses source files.
Do not use `docker compose down -v` on a deployment you intend to keep. Keep the signing
secret stable across restarts. Do not expose the loopback API port directly to the internet.

## Sample content

After migrations, enable `DEMO_ENABLED=true` only on the intended demo deployment. Run
`docker compose run --rm --no-deps -v "$PWD/.env.production:/run/demo.env:ro" api python -m scripts.seed_demo --env /run/demo.env --confirm-demo`
with the private runtime configuration mounted read-only.
The command uses the same media volume as the API. See `docs/demo.md` for seed behavior.

## Optional live processing

Keep AI disabled for the sample workspace. To process real account uploads later, configure
`GROQ_API_KEY` privately, set `AI_BACKEND=groq`, `PROCESSING_WORKERS=1` and
`DATABASE_CONNECTION_BUDGET=9` (minimum for one API and one worker). Recreate the API with
those values, then start `docker compose --profile ai up -d worker`. The worker shares the
media volume and permits one owner through its filesystem lock. Do not run multiple copies
or put this volume on a filesystem without reliable advisory locks. Validate real Korean and
English results separately; saved demo content is hand-written and does not exercise Groq.

Use `docker compose config --quiet` to validate the populated Compose file locally. This
prints no expanded configuration; avoid dumping resolved environment values into logs.
Reference: https://docs.docker.com/compose/how-tos/profiles/
