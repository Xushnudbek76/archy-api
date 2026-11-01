import sqlalchemy as sa
from alembic import op

revision = "0014_academics"
down_revision = "0013_tutor_usage"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "academics_term",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("archy.accounts_user.id"), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "id"),
        sa.CheckConstraint(
            "length(btrim(name)) > 0 AND name = btrim(name)",
            name=op.f("ck_academics_term_name_valid"),
        ),
        schema="archy",
    )
    op.create_index("ix_academics_term_owner_id", "academics_term", ["owner_id"], schema="archy")
    op.create_table(
        "academics_timetable",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, nullable=False),
        sa.Column("term_id", sa.Uuid, nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "id"),
        sa.ForeignKeyConstraint(
            ["owner_id", "term_id"], ["archy.academics_term.owner_id", "archy.academics_term.id"]
        ),
        sa.CheckConstraint(
            "length(btrim(name)) > 0 AND name = btrim(name)",
            name=op.f("ck_academics_timetable_name_valid"),
        ),
        schema="archy",
    )
    op.create_index(
        "ix_academics_timetable_owner_id", "academics_timetable", ["owner_id"], schema="archy"
    )
    op.create_index(
        "ix_academics_primary_per_term",
        "academics_timetable",
        ["term_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
        schema="archy",
    )
    op.create_table(
        "academics_selection",
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("archy.accounts_user.id"), primary_key=True),
        sa.Column("timetable_id", sa.Uuid, nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id", "timetable_id"],
            ["archy.academics_timetable.owner_id", "archy.academics_timetable.id"],
        ),
        schema="archy",
    )


def downgrade():
    op.drop_table("academics_selection", schema="archy")
    op.drop_table("academics_timetable", schema="archy")
    op.drop_table("academics_term", schema="archy")
