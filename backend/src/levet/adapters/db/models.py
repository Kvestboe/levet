"""SQLAlchemy table mappings. These rows are persistence detail; the rest of the
application works with the domain entities they are converted to and from."""

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    MetaData,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class UtcDateTime(TypeDecorator):
    """Timezone-aware datetime stored as naive UTC, which is all SQLite can hold."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime cannot be stored; attach a timezone")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect):  # noqa: ANN001
        return None if value is None else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class SubjectRow(Base):
    __tablename__ = "subjects"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    exam_date: Mapped[date | None]


class TopicRow(Base):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("subject_code", "name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    subject_code: Mapped[str] = mapped_column(
        ForeignKey("subjects.code", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))


class ExamRow(Base):
    __tablename__ = "exams"
    __table_args__ = (UniqueConstraint("subject_code", "label"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    subject_code: Mapped[str] = mapped_column(
        ForeignKey("subjects.code", ondelete="RESTRICT"), index=True
    )
    label: Mapped[str] = mapped_column(String(200))
    pdf_key: Mapped[str] = mapped_column(String(300))
    solution_pdf_key: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), index=True)
    error: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None]
    solution_page_count: Mapped[int | None]
    uploaded_at: Mapped[datetime] = mapped_column(UtcDateTime)


class TaskRow(Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    exam_id: Mapped[UUID] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    # Deferred so a sub-task and its parent can be saved in either order within a transaction.
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL", deferrable=True, initially="DEFERRED")
    )
    number: Mapped[str] = mapped_column(String(32))
    title: Mapped[str | None] = mapped_column(String(300))
    position: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    points: Mapped[float | None]
    solution_text: Mapped[str | None] = mapped_column(Text)
    # Regions are stored as lists of [page, top, bottom, left, right].
    regions: Mapped[list[list[float]]] = mapped_column(JSON)
    image_keys: Mapped[list[str]] = mapped_column(JSON)
    solution_regions: Mapped[list[list[float]]] = mapped_column(JSON)
    solution_image_keys: Mapped[list[str]] = mapped_column(JSON)

    topic_links: Mapped[list["TaskTopicRow"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class TaskTopicRow(Base):
    __tablename__ = "task_topics"

    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class AttemptRow(Base):
    __tablename__ = "attempts"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    attempted_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    grade: Mapped[str] = mapped_column(String(10))
    time_spent_seconds: Mapped[float | None]
    answer: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)


class ReviewStateRow(Base):
    __tablename__ = "review_states"

    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    due: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    phase: Mapped[str] = mapped_column(String(12))
    step: Mapped[int | None]
    stability: Mapped[float | None]
    difficulty: Mapped[float | None]
    last_review: Mapped[datetime | None] = mapped_column(UtcDateTime)
