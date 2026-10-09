# Development

Keep feature code in its Django app. Views own HTTP, serializers validate contracts, services
coordinate workflows, and models/migrations enforce persistence. Use Django's existing primitives
before introducing another abstraction or dependency.

Run `ruff check .`, `ruff format --check .`, `pytest` and Django checks before committing.
Database tests must use loopback `archy_api_test`; never test destructively against hosted data.
Keep runtime credentials separate from migration/bootstrap credentials. Never print or commit secrets.

Use short commits describing actual changes: `feat: add auth`, `fix: validate input`.
Use the human's GitHub identity `Xushnudbek76` and preserve their mapped author email.
Verify authenticated identity before publishing. Do not rewrite published history or backdate commits.
