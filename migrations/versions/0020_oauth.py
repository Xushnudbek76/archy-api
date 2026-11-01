import sqlalchemy as sa
from alembic import op

revision = "0020_oauth"
down_revision = "0019_account_closure"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "oauth_identity",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid,
            sa.ForeignKey("archy.accounts_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(10), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "subject"),
        schema="archy",
    )
    op.create_index("ix_oauth_identity_owner", "oauth_identity", ["owner_id"], schema="archy")
    op.create_table(
        "oauth_state",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("browser_digest", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(10), nullable=False),
        sa.Column("nonce", sa.String(64), nullable=False),
        sa.Column("verifier", sa.String(128), nullable=False),
        sa.Column("return_to", sa.String(100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        schema="archy",
    )
    op.create_index("ix_oauth_state_expiry", "oauth_state", ["expires_at"], schema="archy")


def downgrade():
    op.drop_table("oauth_state", schema="archy")
    op.drop_table("oauth_identity", schema="archy")
