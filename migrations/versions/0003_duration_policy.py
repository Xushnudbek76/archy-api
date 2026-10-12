from alembic import op

revision = "0003_duration_policy"
down_revision = "0002_auth"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE archy.recordings_upload ADD COLUMN max_duration_seconds INTEGER")
    op.execute(
        "ALTER TABLE archy.recordings_upload ADD CONSTRAINT "
        "upload_duration_policy_valid CHECK (max_duration_seconds IS NULL OR "
        "max_duration_seconds > 0)"
    )


def downgrade():
    raise RuntimeError("Duration policy rollback requires a reviewed backup restoration.")
