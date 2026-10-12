# Development

Keep features under `app/components/<feature>`. Routers own HTTP, schemas validate contracts,
services coordinate workflows, and models/Alembic revisions enforce persistence. Prefer small,
explicit functions over extra abstractions. Add comments only when a decision needs explanation.

Use synchronous SQLAlchemy sessions for synchronous routes. Async uploads and playback call
complete worker units which create and close their own sessions and return immutable data.
Never keep a session or worker occupied while waiting for client bytes or streaming a response.

Run `ruff check .`, `ruff format --check .` and `pytest` before committing. Database tests must
use loopback `archy_api_test`; never test destructively against hosted data. Schema changes
run only through the migration command. Keep runtime/migration/bootstrap credentials separate.
Never print or commit secrets.

Use short commits describing actual changes. Ask the human before committing this migration.
Use the human's GitHub identity `Xushnudbek76` and preserve their mapped author email.
Verify authenticated identity before publishing. Do not rewrite published history or backdate commits.
