import sqlalchemy as sa
from alembic import op

revision = "0022_billing_renewal_consent"
down_revision = "0021_billing"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "billing_order",
        sa.Column("cancel_renewal", sa.Boolean, nullable=False, server_default=sa.false()),
        schema="archy",
    )


def downgrade():
    op.drop_column("billing_order", "cancel_renewal", schema="archy")
