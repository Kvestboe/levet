from datetime import date, datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from levet.application.exams import ExamView
from levet.application.review import ExamTasks
from levet.domain import ExamStatus, Region, Subject, Task, Topic


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
