from datetime import date, datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from levet.application.exams import ExamView
from levet.application.practice import (
    AttemptResult,
    PracticeQueue,
    PracticeTask,
    QueueEntry,
    TopicProgress,
)
from levet.application.progress import Dashboard, LoggedAttempt, TopicDetail
from levet.application.review import ExamTasks
from levet.application.settings import AppSettings
from levet.domain import ExamStatus, Grade, Language, Region, Subject, Task, Topic
from levet.domain.practice import Reason


class LoginIn(BaseModel):
    password: str


class SessionOut(BaseModel):
    authenticated: bool


class SubjectIn(BaseModel):
    code: str
    name: str
    exam_date: date | None = None


class SubjectUpdate(BaseModel):
    name: str
    exam_date: date | None = None


class SubjectOut(BaseModel):
    code: str
    name: str
    exam_date: date | None

    @classmethod
    def of(cls, subject: Subject) -> Self:
        return cls(code=subject.code, name=subject.name, exam_date=subject.exam_date)


class ProgressOut(BaseModel):
    stage: str
    done: int
    total: int


class ExamOut(BaseModel):
    id: UUID
    subject_code: str
    label: str
    status: ExamStatus
    error: str | None
    has_solution: bool
    page_count: int | None
    solution_page_count: int | None
    uploaded_at: datetime
    progress: ProgressOut | None

    @classmethod
    def of(cls, view: ExamView) -> Self:
        exam, progress = view.exam, view.progress
        return cls(
            id=exam.id,
            subject_code=exam.subject_code,
            label=exam.label,
            status=exam.status,
            error=exam.error,
            has_solution=exam.solution_pdf_key is not None,
            page_count=exam.page_count,
            solution_page_count=exam.solution_page_count,
            uploaded_at=exam.uploaded_at,
            progress=(
                None
                if progress is None
                else ProgressOut(stage=progress.stage, done=progress.done, total=progress.total)
            ),
        )


class TopicOut(BaseModel):
    id: UUID
    name: str

    @classmethod
    def of(cls, topic: Topic) -> Self:
        return cls(id=topic.id, name=topic.name)


class RegionOut(BaseModel):
    page: int
    top: float
    bottom: float
    left: float
    right: float

    @classmethod
    def of(cls, region: Region) -> Self:
        return cls(
            page=region.page,
            top=region.top,
            bottom=region.bottom,
            left=region.left,
            right=region.right,
        )


class TaskOut(BaseModel):
    id: UUID
    exam_id: UUID
    parent_id: UUID | None
    number: str
    title: str | None
    position: int
    points: float | None
    topics: list[TopicOut]
    regions: list[RegionOut]
    images: list[str]
    solution_images: list[str]
    solution_text: str | None

    @classmethod
    def of(cls, task: Task, topics: dict[UUID, Topic]) -> Self:
        return cls(
            id=task.id,
            exam_id=task.exam_id,
            parent_id=task.parent_id,
            number=task.number,
            title=task.title,
            position=task.position,
            points=task.points,
            topics=sorted(
                (TopicOut.of(topics[i]) for i in task.topic_ids if i in topics),
                key=lambda topic: topic.name.casefold(),
            ),
            regions=[RegionOut.of(region) for region in task.regions],
            images=[_image_url(task.exam_id, key) for key in task.image_keys],
            solution_images=[_image_url(task.exam_id, key) for key in task.solution_image_keys],
            solution_text=task.solution_text,
        )


class ExamTasksOut(BaseModel):
    tasks: list[TaskOut]
    topics: list[TopicOut]

    @classmethod
    def of(cls, view: ExamTasks) -> Self:
        topics = {topic.id: topic for topic in view.topics}
        return cls(
            tasks=[TaskOut.of(task, topics) for task in view.tasks],
            topics=[TopicOut.of(topic) for topic in view.topics],
        )


class TaskUpdate(BaseModel):
    """Fields left out are not changed. ``title`` and ``points`` may be set to null."""

    number: str | None = None
    title: str | None = None
    points: float | None = Field(default=None, ge=0)
    topics: list[str] | None = None


class TopicRename(BaseModel):
    name: str


class TaskSplit(BaseModel):
    image_index: int = Field(ge=0)
    fraction: float = Field(gt=0, lt=1)


def _image_url(exam_id: UUID, key: str) -> str:
    return f"/api/exams/{exam_id}/task-images/{key.rsplit('/', 1)[-1]}"


# --- practice ------------------------------------------------------------------


class ExamRef(BaseModel):
    id: UUID
    label: str
    subject_code: str


class TaskPart(BaseModel):
    """One piece of a task as printed: a label and its images."""

    id: UUID
    number: str
    images: list[str]


class SolutionOut(BaseModel):
    images: list[str]
    text: str | None


class PracticeTaskOut(BaseModel):
    id: UUID
    number: str
    title: str | None
    points: float | None
    exam: ExamRef
    images: list[str]
    # The introduction shared by the parts of the task this one belongs to.
    context: TaskPart | None
    # The whole task in order: the introduction and every part.
    group: list[TaskPart]
    solution: SolutionOut | None
    topics: list[TopicOut]
    attempt_count: int
    last_grade: Grade | None
    due: datetime | None

    @classmethod
    def of(cls, practice: PracticeTask) -> Self:
        task, parent, solution = practice.task, practice.parent, practice.solution
        return cls(
            id=task.id,
            number=task.number,
            title=task.title or (parent.title if parent else None),
            points=task.points,
            exam=ExamRef(
                id=practice.exam.id,
                label=practice.exam.label,
                subject_code=practice.exam.subject_code,
            ),
            images=_image_urls(task.exam_id, task.image_keys),
            context=None if parent is None else _part(parent),
            group=[_part(member) for member in practice.group],
            solution=(
                None
                if solution is None
                else SolutionOut(
                    images=_image_urls(solution.exam_id, solution.solution_image_keys),
                    text=solution.solution_text,
                )
            ),
            topics=[TopicOut.of(topic) for topic in practice.topics],
            attempt_count=practice.attempt_count,
            last_grade=practice.last_grade,
            due=practice.due,
        )


class QueueEntryOut(BaseModel):
    task: PracticeTaskOut
    reason: Reason
    topic: TopicOut | None

    @classmethod
    def of(cls, entry: QueueEntry) -> Self:
        return cls(
            task=PracticeTaskOut.of(entry.practice),
            reason=entry.reason,
            topic=None if entry.topic is None else TopicOut.of(entry.topic),
        )


class PracticeQueueOut(BaseModel):
    entries: list[QueueEntryOut]
    total: int
    due_count: int

    @classmethod
    def of(cls, queue: PracticeQueue) -> Self:
        return cls(
            entries=[QueueEntryOut.of(entry) for entry in queue.entries],
            total=queue.total,
            due_count=queue.due_count,
        )


class TopicProgressOut(BaseModel):
    id: UUID
    name: str
    subject_code: str
    weakness: float
    mastery: float | None
    staleness: float
    coverage_gap: float
    urgency: float
    priority: float
    task_count: int
    attempted_count: int

    @classmethod
    def of(cls, progress: TopicProgress) -> Self:
        score = progress.score
        return cls(
            id=progress.topic.id,
            name=progress.topic.name,
            subject_code=score.subject_code,
            weakness=score.weakness.weakness,
            mastery=score.weakness.mastery,
            staleness=score.weakness.staleness,
            coverage_gap=score.weakness.coverage_gap,
            urgency=score.urgency,
            priority=score.priority,
            task_count=score.task_count,
            attempted_count=score.attempted_count,
        )


class AttemptIn(BaseModel):
    task_id: UUID
    grade: Grade
    time_spent_seconds: float | None = Field(default=None, ge=0, le=86_400)
    answer: str | None = Field(default=None, max_length=20_000)
    note: str | None = Field(default=None, max_length=5_000)


class AttemptOut(BaseModel):
    id: UUID
    task_id: UUID
    grade: Grade
    score: float
    attempted_at: datetime
    # When the task is due again according to the spaced-repetition schedule.
    due: datetime

    @classmethod
    def of(cls, result: AttemptResult) -> Self:
        attempt = result.attempt
        return cls(
            id=attempt.id,
            task_id=attempt.task_id,
            grade=attempt.grade,
            score=attempt.score,
            attempted_at=attempt.attempted_at,
            due=result.state.due,
        )


def _part(task: Task) -> TaskPart:
    return TaskPart(
        id=task.id, number=task.number, images=_image_urls(task.exam_id, task.image_keys)
    )


def _image_urls(exam_id: UUID, keys: tuple[str, ...]) -> list[str]:
    return [_image_url(exam_id, key) for key in keys]


# --- progress ------------------------------------------------------------------


class DashboardOut(BaseModel):
    subjects: list[SubjectOut]
    weakest_topics: list[TopicProgressOut]
    due_count: int
    task_count: int
    attempted_count: int
    streak_days: int
    attempts_today: int

    @classmethod
    def of(cls, dashboard: Dashboard) -> Self:
        return cls(
            subjects=[SubjectOut.of(subject) for subject in dashboard.subjects],
            weakest_topics=[TopicProgressOut.of(p) for p in dashboard.weakest_topics],
            due_count=dashboard.due_count,
            task_count=dashboard.task_count,
            attempted_count=dashboard.attempted_count,
            streak_days=dashboard.streak_days,
            attempts_today=dashboard.attempts_today,
        )


class MasteryPoint(BaseModel):
    day: date
    mastery: float


class TopicTaskOut(BaseModel):
    id: UUID
    number: str
    exam: ExamRef
    attempt_count: int
    last_grade: Grade | None
    due: datetime | None

    @classmethod
    def of(cls, practice: PracticeTask) -> Self:
        return cls(
            id=practice.task.id,
            number=practice.task.number,
            exam=ExamRef(
                id=practice.exam.id,
                label=practice.exam.label,
                subject_code=practice.exam.subject_code,
            ),
            attempt_count=practice.attempt_count,
            last_grade=practice.last_grade,
            due=practice.due,
        )


class LoggedAttemptOut(BaseModel):
    id: UUID
    attempted_at: datetime
    grade: Grade
    score: float
    time_spent_seconds: float | None
    answer: str | None
    note: str | None
    task_number: str
    exam_label: str

    @classmethod
    def of(cls, logged: LoggedAttempt) -> Self:
        attempt = logged.attempt
        return cls(
            id=attempt.id,
            attempted_at=attempt.attempted_at,
            grade=attempt.grade,
            score=attempt.score,
            time_spent_seconds=(
                None if attempt.time_spent is None else attempt.time_spent.total_seconds()
            ),
            answer=attempt.answer,
            note=attempt.note,
            task_number=logged.task.number,
            exam_label=logged.exam.label,
        )


class TopicDetailOut(BaseModel):
    topic: TopicProgressOut
    history: list[MasteryPoint]
    tasks: list[TopicTaskOut]
    attempts: list[LoggedAttemptOut]

    @classmethod
    def of(cls, detail: TopicDetail) -> Self:
        return cls(
            topic=TopicProgressOut.of(detail.progress),
            history=[MasteryPoint(day=day, mastery=value) for day, value in detail.history],
            tasks=[TopicTaskOut.of(task) for task in detail.tasks],
            attempts=[LoggedAttemptOut.of(logged) for logged in detail.attempts],
        )


# --- settings ------------------------------------------------------------------


class SettingsOut(BaseModel):
    mastery_weight: float
    staleness_weight: float
    coverage_weight: float
    preferred_language: Language

    @classmethod
    def of(cls, settings: AppSettings) -> Self:
        return cls(
            mastery_weight=settings.scoring.mastery_weight,
            staleness_weight=settings.scoring.staleness_weight,
            coverage_weight=settings.scoring.coverage_weight,
            preferred_language=settings.preferred_language,
        )


class SettingsIn(BaseModel):
    """Fields left out are not changed."""

    mastery_weight: float | None = Field(default=None, ge=0, le=1000)
    staleness_weight: float | None = Field(default=None, ge=0, le=1000)
    coverage_weight: float | None = Field(default=None, ge=0, le=1000)
    preferred_language: Language | None = None
