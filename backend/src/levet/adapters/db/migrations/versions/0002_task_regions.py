"""tasks are shown as regions of the exam pages

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Plain ALTER TABLE statements: SQLite supports these directly, and they
    # avoid rebuilding a table that three others reference.
    op.execute("ALTER TABLE tasks RENAME COLUMN figure_keys TO image_keys")
    op.drop_column("tasks", "source_pages")
    op.add_column("tasks", sa.Column("title", sa.String(length=300), nullable=True))
    op.add_column("tasks", sa.Column("position", sa.Integer(), nullable=False, server_default="0"))
    for name in ("regions", "solution_regions", "solution_image_keys"):
        op.add_column("tasks", sa.Column(name, sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    for name in ("solution_image_keys", "solution_regions", "regions", "position", "title"):
        op.drop_column("tasks", name)
    op.add_column(
        "tasks", sa.Column("source_pages", sa.JSON(), nullable=False, server_default="[]")
    )
    op.execute("ALTER TABLE tasks RENAME COLUMN image_keys TO figure_keys")
