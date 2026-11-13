"""SQLAlchemy implementations of the repository ports.

Each repository converts between domain entities and table rows; nothing
outside this package sees a row.
"""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from levet.adapters.db.models import (
    AttemptRow,
    ExamRow,
    ReviewStateRow,
    SettingRow,
    SubjectRow,
    TaskRow,
    TaskTopicRow,
    TopicRow,
)
from levet.domain import (
    Attempt,
    Exam,
    ExamStatus,
    Grade,
    Region,
    ReviewPhase,
    ReviewState,
    Subject,
    Task,
    Topic,
)


class SqlSubjectRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, subject: Subject) -> None:
        _merge(
            self._session,
            SubjectRow(code=subject.code, name=subject.name, exam_date=subject.exam_date),
        )

    def get(self, code: str) -> Subject | None:
        row = self._session.get(SubjectRow, code)
        return None if row is None else _subject(row)

    def list_all(self) -> list[Subject]:
        rows = self._session.scalars(select(SubjectRow).order_by(SubjectRow.code))
        return [_subject(row) for row in rows]

    def delete(self, code: str) -> None:
        self._session.execute(delete(SubjectRow).where(SubjectRow.code == code))


class SqlTopicRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, topic: Topic) -> None:
        _merge(
            self._session, TopicRow(id=topic.id, subject_code=topic.subject_code, name=topic.name)
        )

    def get(self, topic_id: UUID) -> Topic | None:
        row = self._session.get(TopicRow, topic_id)
        return None if row is None else _topic(row)

    def list_by_subject(self, subject_code: str) -> list[Topic]:
        rows = self._session.scalars(
            select(TopicRow).where(TopicRow.subject_code == subject_code).order_by(TopicRow.name)
        )
        return [_topic(row) for row in rows]

    def delete(self, topic_id: UUID) -> None:
        self._session.flush()
        self._session.execute(delete(TopicRow).where(TopicRow.id == topic_id))

    def delete_unused(self, subject_code: str) -> None:
        self._session.flush()
        used = select(TaskTopicRow.topic_id)
        self._session.execute(
            delete(TopicRow).where(TopicRow.subject_code == subject_code, TopicRow.id.not_in(used))
        )


class SqlExamRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, exam: Exam) -> None:
        _merge(
            self._session,
            ExamRow(
                id=exam.id,
                subject_code=exam.subject_code,
                label=exam.label,
                pdf_key=exam.pdf_key,
                solution_pdf_key=exam.solution_pdf_key,
                status=exam.status.value,
                error=exam.error,
                page_count=exam.page_count,
                solution_page_count=exam.solution_page_count,
                uploaded_at=exam.uploaded_at,
            ),
        )

    def get(self, exam_id: UUID) -> Exam | None:
        row = self._session.get(ExamRow, exam_id)
        return None if row is None else _exam(row)

    def list_all(self, subject_code: str | None = None) -> list[Exam]:
        query = select(ExamRow).order_by(ExamRow.uploaded_at.desc(), ExamRow.label)
        if subject_code is not None:
            query = query.where(ExamRow.subject_code == subject_code)
        return [_exam(row) for row in self._session.scalars(query)]

    def find_by_label(self, subject_code: str, label: str) -> Exam | None:
        row = self._session.scalars(
            select(ExamRow).where(ExamRow.subject_code == subject_code, ExamRow.label == label)
        ).first()
        return None if row is None else _exam(row)

    def list_by_status(self, status: ExamStatus) -> list[Exam]:
        rows = self._session.scalars(
            select(ExamRow).where(ExamRow.status == status.value).order_by(ExamRow.uploaded_at)
        )
        return [_exam(row) for row in rows]


class SqlTaskRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, task: Task) -> None:
        _merge(
            self._session,
            TaskRow(
                id=task.id,
                exam_id=task.exam_id,
                parent_id=task.parent_id,
                number=task.number,
                title=task.title,
                position=task.position,
                text=task.text,
                points=task.points,
                solution_text=task.solution_text,
                regions=_regions_out(task.regions),
                image_keys=list(task.image_keys),
                solution_regions=_regions_out(task.solution_regions),
                solution_image_keys=list(task.solution_image_keys),
                topic_links=[
                    TaskTopicRow(task_id=task.id, topic_id=topic_id)
                    for topic_id in sorted(task.topic_ids, key=str)
                ],
            ),
        )

    def get(self, task_id: UUID) -> Task | None:
        row = self._session.get(TaskRow, task_id)
        return None if row is None else _task(row)

    def list_by_exam(self, exam_id: UUID) -> list[Task]:
        rows = self._session.scalars(
            select(TaskRow)
            .where(TaskRow.exam_id == exam_id)
            .order_by(TaskRow.position, TaskRow.number)
        )
        return [_task(row) for row in rows]

    def list_by_topic(self, topic_id: UUID) -> list[Task]:
        rows = self._session.scalars(
            select(TaskRow)
            .join(TaskTopicRow, TaskTopicRow.task_id == TaskRow.id)
            .where(TaskTopicRow.topic_id == topic_id)
            .order_by(TaskRow.exam_id, TaskRow.position)
        )
        return [_task(row) for row in rows]

    def list_by_exam_status(self, status: ExamStatus) -> list[Task]:
        rows = self._session.scalars(
            select(TaskRow)
            .join(ExamRow, ExamRow.id == TaskRow.exam_id)
            .where(ExamRow.status == status.value)
            .order_by(ExamRow.uploaded_at, ExamRow.id, TaskRow.position)
        )
        return [_task(row) for row in rows]

    def delete(self, task_id: UUID) -> None:
        row = self._session.get(TaskRow, task_id)
        if row is not None:
            self._session.delete(row)
            self._session.flush()

    def delete_by_exam(self, exam_id: UUID) -> None:
        for row in self._session.scalars(select(TaskRow).where(TaskRow.exam_id == exam_id)):
            self._session.delete(row)
        self._session.flush()


class SqlAttemptRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, attempt: Attempt) -> None:
        self._session.add(
            AttemptRow(
                id=attempt.id,
                task_id=attempt.task_id,
                attempted_at=attempt.attempted_at,
                grade=attempt.grade.value,
                time_spent_seconds=(
                    None if attempt.time_spent is None else attempt.time_spent.total_seconds()
                ),
                answer=attempt.answer,
                note=attempt.note,
            )
        )
        # Flush now so re-adding an existing attempt fails here, not at commit.
        self._session.flush()

    def list_by_task(self, task_id: UUID) -> list[Attempt]:
        rows = self._session.scalars(
            select(AttemptRow)
            .where(AttemptRow.task_id == task_id)
            .order_by(AttemptRow.attempted_at)
        )
        return [_attempt(row) for row in rows]

    def list_all(self) -> list[Attempt]:
        rows = self._session.scalars(select(AttemptRow).order_by(AttemptRow.attempted_at))
        return [_attempt(row) for row in rows]


class SqlReviewStateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, state: ReviewState) -> None:
        _merge(
            self._session,
            ReviewStateRow(
                task_id=state.task_id,
                due=state.due,
                phase=state.phase.value,
                step=state.step,
                stability=state.stability,
                difficulty=state.difficulty,
                last_review=state.last_review,
            ),
        )

    def get(self, task_id: UUID) -> ReviewState | None:
        row = self._session.get(ReviewStateRow, task_id)
        return None if row is None else _review_state(row)

    def list_all(self) -> list[ReviewState]:
        return [_review_state(row) for row in self._session.scalars(select(ReviewStateRow))]


class SqlSettingsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, key: str) -> dict | None:
        row = self._session.get(SettingRow, key)
        return None if row is None else dict(row.value)

    def set(self, key: str, value: dict) -> None:
        _merge(self._session, SettingRow(key=key, value=value))


def _merge(session: Session, row: object) -> None:
    """Insert or update a row, and send it to the database straight away.

    Flushing at once means writes reach the database in the order the
    repositories are called. Left to itself the session may insert a row before
    the row it refers to, when the two tables are not linked by a relationship.
    """
    session.merge(row)
    session.flush()


def _subject(row: SubjectRow) -> Subject:
    return Subject(code=row.code, name=row.name, exam_date=row.exam_date)


def _topic(row: TopicRow) -> Topic:
    return Topic(id=row.id, subject_code=row.subject_code, name=row.name)


def _exam(row: ExamRow) -> Exam:
    return Exam(
        id=row.id,
        subject_code=row.subject_code,
        label=row.label,
        pdf_key=row.pdf_key,
        solution_pdf_key=row.solution_pdf_key,
        status=ExamStatus(row.status),
        error=row.error,
        page_count=row.page_count,
        solution_page_count=row.solution_page_count,
        uploaded_at=row.uploaded_at,
    )


def _task(row: TaskRow) -> Task:
    return Task(
        id=row.id,
        exam_id=row.exam_id,
        parent_id=row.parent_id,
        number=row.number,
        title=row.title,
        position=row.position,
        text=row.text,
        points=row.points,
        solution_text=row.solution_text,
        regions=_regions_in(row.regions),
        image_keys=tuple(row.image_keys),
        solution_regions=_regions_in(row.solution_regions),
        solution_image_keys=tuple(row.solution_image_keys),
        topic_ids=frozenset(link.topic_id for link in row.topic_links),
    )


def _regions_out(regions: tuple[Region, ...]) -> list[list[float]]:
    return [[r.page, r.top, r.bottom, r.left, r.right] for r in regions]


def _regions_in(stored: list[list[float]]) -> tuple[Region, ...]:
    return tuple(
        Region(page=int(page), top=top, bottom=bottom, left=left, right=right)
        for page, top, bottom, left, right in stored
    )


def _attempt(row: AttemptRow) -> Attempt:
    return Attempt(
        id=row.id,
        task_id=row.task_id,
        attempted_at=row.attempted_at,
        grade=Grade(row.grade),
        time_spent=(
            None if row.time_spent_seconds is None else timedelta(seconds=row.time_spent_seconds)
        ),
        answer=row.answer,
        note=row.note,
    )


def _review_state(row: ReviewStateRow) -> ReviewState:
    return ReviewState(
        task_id=row.task_id,
        due=row.due,
        phase=ReviewPhase(row.phase),
        step=row.step,
        stability=row.stability,
        difficulty=row.difficulty,
        last_review=row.last_review,
    )
