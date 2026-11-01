import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0015_course_schedules"
down_revision = "0014_academics"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "courses_course",
        sa.Column("professor", sa.String(100), nullable=False, server_default=""),
        schema="archy",
    )
    op.add_column(
        "courses_course",
        sa.Column("color", sa.String(7), nullable=False, server_default="#396c50"),
        schema="archy",
    )
    op.add_column("courses_course", sa.Column("timetable_id", sa.Uuid), schema="archy")
    op.create_foreign_key(
        "fk_courses_timetable_owner",
        "courses_course",
        "academics_timetable",
        ["owner_id", "timetable_id"],
        ["owner_id", "id"],
        source_schema="archy",
        referent_schema="archy",
    )
    op.create_check_constraint(
        op.f("ck_courses_course_color_valid"),
        "courses_course",
        "color ~ '^#[0-9a-fA-F]{6}$'",
        schema="archy",
    )
    op.create_table(
        "academics_schedule",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "course_id",
            sa.Uuid,
            sa.ForeignKey("archy.courses_course.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("days", JSONB, nullable=False),
        sa.Column("start_time", sa.String(5), nullable=False),
        sa.Column("end_time", sa.String(5), nullable=False),
        sa.Column("room", sa.String(100), nullable=False),
        sa.UniqueConstraint("course_id", "position"),
        sa.CheckConstraint(
            "start_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$' AND end_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$' AND start_time < end_time",
            name=op.f("ck_academics_schedule_times_valid"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(days) = 'array' AND jsonb_array_length(days) BETWEEN 1 AND 7",
            name=op.f("ck_academics_schedule_days_valid"),
        ),
        schema="archy",
    )
    op.create_index(
        "ix_academics_schedule_course_id", "academics_schedule", ["course_id"], schema="archy"
    )


def downgrade():
    op.drop_table("academics_schedule", schema="archy")
    op.drop_constraint(
        "fk_courses_timetable_owner", "courses_course", schema="archy", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("ck_courses_course_color_valid"), "courses_course", schema="archy", type_="check"
    )
    for name in ["timetable_id", "color", "professor"]:
        op.drop_column("courses_course", name, schema="archy")
