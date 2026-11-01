import sqlalchemy as sa
from alembic import op

revision = "0018_preferences"
down_revision = "0017_document_pins"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "preferences_profile",
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("archy.accounts_user.id"), primary_key=True),
        sa.Column("university", sa.String(100), nullable=False, server_default=""),
        sa.Column("department", sa.String(100), nullable=False, server_default=""),
        sa.Column("ui_language", sa.String(2), nullable=False, server_default="en"),
        sa.Column("summary_language", sa.String(4), nullable=False, server_default="auto"),
        sa.Column("note_format", sa.String(36), nullable=False, server_default="outline"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "ui_language IN ('en','ko')", name=op.f("ck_preferences_profile_ui_language_valid")
        ),
        sa.CheckConstraint(
            "summary_language IN ('auto','en','ko')",
            name=op.f("ck_preferences_profile_summary_language_valid"),
        ),
        schema="archy",
    )
    op.create_table(
        "preferences_format",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("archy.accounts_user.id"), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("instructions", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(btrim(name)) BETWEEN 1 AND 60 AND name = btrim(name)",
            name=op.f("ck_preferences_format_name_valid"),
        ),
        sa.CheckConstraint(
            "length(btrim(instructions)) BETWEEN 1 AND 300",
            name=op.f("ck_preferences_format_instructions_valid"),
        ),
        schema="archy",
    )
    op.create_index(
        "ix_preferences_format_owner_id", "preferences_format", ["owner_id"], schema="archy"
    )


def downgrade():
    op.drop_table("preferences_format", schema="archy")
    op.drop_table("preferences_profile", schema="archy")
