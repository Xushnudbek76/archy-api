import sqlalchemy as sa
from alembic import op

revision = "0021_billing"
down_revision = "0020_oauth"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "billing_customer",
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("archy.accounts_user.id"), primary_key=True),
        sa.Column("customer_key", sa.String(50), nullable=False, unique=True),
        sa.Column("billing_key", sa.Text),
        schema="archy",
    )
    op.create_table(
        "billing_subscription",
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("archy.accounts_user.id"), primary_key=True),
        sa.Column("plan", sa.String(10), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancel_at_period_end", sa.Boolean, nullable=False),
        sa.Column("latest_order", sa.String(50), nullable=False),
        schema="archy",
    )
    op.create_index(
        "ix_billing_subscription_due", "billing_subscription", ["period_end"], schema="archy"
    )
    op.create_table(
        "billing_order",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("archy.accounts_user.id"), nullable=False),
        sa.Column("request_id", sa.Uuid, nullable=False),
        sa.Column("plan", sa.String(10), nullable=False),
        sa.Column("amount", sa.Integer, nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("phase", sa.String(12), nullable=False),
        sa.Column("auth_digest", sa.String(64)),
        sa.Column("auth_key", sa.Text),
        sa.Column("payment_key", sa.String(200), unique=True),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease", sa.Uuid),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.UniqueConstraint("owner_id", "request_id"),
        sa.CheckConstraint(
            "status IN ('pending','processing','paid','failed','review','cancelled')",
            name=op.f("ck_billing_order_status_valid"),
        ),
        sa.CheckConstraint(
            "amount > 0 AND attempts BETWEEN 0 AND 8", name=op.f("ck_billing_order_bounds_valid")
        ),
        schema="archy",
    )
    op.create_index(
        "ix_billing_order_owner", "billing_order", ["owner_id", "created_at"], schema="archy"
    )
    op.create_index("ix_billing_order_due", "billing_order", ["available_at"], schema="archy")


def downgrade():
    for name in ("billing_order", "billing_subscription", "billing_customer"):
        op.drop_table(name, schema="archy")
