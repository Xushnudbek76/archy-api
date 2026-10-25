import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_document_pages"
down_revision = "0005_documents"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents_document", sa.Column("pages", JSONB, nullable=True), schema="archy")


def downgrade():
    op.drop_column("documents_document", "pages", schema="archy")
