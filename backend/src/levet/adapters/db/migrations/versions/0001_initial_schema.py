"""initial schema

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subjects",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("exam_date", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("code", name="pk_subjects"),
    )

    op.create_table(
        "topics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["subject_code"],
            ["subjects.code"],
            name="fk_topics_subject_code_subjects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_topics"),
        sa.UniqueConstraint("subject_code", "name", name="uq_topics_subject_code_name"),
    )
    op.create_index("ix_topics_subject_code", "topics", ["subject_code"])

    op.create_table(
        "exams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_code", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("pdf_key", sa.String(length=300), nullable=False),
        sa.Column("solution_pdf_key", sa.String(length=300), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("solution_page_count", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["subject_code"],
            ["subjects.code"],
            name="fk_exams_subject_code_subjects",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_exams"),
        sa.UniqueConstraint("subject_code", "label", name="uq_exams_subject_code_label"),
    )
    op.create_index("ix_exams_subject_code", "exams", ["subject_code"])
    op.create_index("ix_exams_status", "exams", ["status"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exam_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("points", sa.Double(), nullable=True),
        sa.Column("solution_text", sa.Text(), nullable=True),
        sa.Column("figure_keys", sa.JSON(), nullable=False),
        sa.Column("source_pages", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["exam_id"], ["exams.id"], name="fk_tasks_exam_id_exams", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["tasks.id"],
            name="fk_tasks_parent_id_tasks",
            ondelete="SET NULL",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tasks"),
    )
    op.create_index("ix_tasks_exam_id", "tasks", ["exam_id"])

    op.create_table(
        "task_topics",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name="fk_task_topics_task_id_tasks", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"], ["topics.id"], name="fk_task_topics_topic_id_topics", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("task_id", "topic_id", name="pk_task_topics"),
    )
    op.create_index("ix_task_topics_topic_id", "task_topics", ["topic_id"])

    op.create_table(
        "attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(), nullable=False),
        sa.Column("grade", sa.String(length=10), nullable=False),
        sa.Column("time_spent_seconds", sa.Double(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name="fk_attempts_task_id_tasks", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_attempts"),
    )
    op.create_index("ix_attempts_task_id", "attempts", ["task_id"])
    op.create_index("ix_attempts_attempted_at", "attempts", ["attempted_at"])

    op.create_table(
        "review_states",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("due", sa.DateTime(), nullable=False),
        sa.Column("phase", sa.String(length=12), nullable=False),
        sa.Column("step", sa.Integer(), nullable=True),
        sa.Column("stability", sa.Double(), nullable=True),
        sa.Column("difficulty", sa.Double(), nullable=True),
        sa.Column("last_review", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name="fk_review_states_task_id_tasks", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("task_id", name="pk_review_states"),
    )
    op.create_index("ix_review_states_due", "review_states", ["due"])


def downgrade() -> None:
    op.drop_table("review_states")
    op.drop_table("attempts")
    op.drop_table("task_topics")
    op.drop_table("tasks")
    op.drop_table("exams")
    op.drop_table("topics")
    op.drop_table("subjects")
