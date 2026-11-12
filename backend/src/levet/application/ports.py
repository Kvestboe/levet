"""Ports: what the use cases need from the outside world."""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from levet.domain import Attempt, Exam, ExamStatus, Region, ReviewState, Subject, Task, Topic

Clock = Callable[[], datetime]
"""Returns the current time, timezone-aware."""


# --- persistence -------------------------------------------------------------


class SubjectRepository(Protocol):
    def save(self, subject: Subject) -> None: ...
    def get(self, code: str) -> Subject | None: ...
    def list_all(self) -> list[Subject]: ...
    def delete(self, code: str) -> None: ...


class TopicRepository(Protocol):
    def save(self, topic: Topic) -> None: ...
    def get(self, topic_id: UUID) -> Topic | None: ...
    def list_by_subject(self, subject_code: str) -> list[Topic]: ...
    def delete(self, topic_id: UUID) -> None: ...
    def delete_unused(self, subject_code: str) -> None:
        """Remove the subject's topics that no task is tagged with."""
        ...


class ExamRepository(Protocol):
    def save(self, exam: Exam) -> None: ...
    def get(self, exam_id: UUID) -> Exam | None: ...
    def list_all(self, subject_code: str | None = None) -> list[Exam]:
        """All exams, or one subject's, newest upload first."""
        ...

    def find_by_label(self, subject_code: str, label: str) -> Exam | None: ...
    def list_by_status(self, status: ExamStatus) -> list[Exam]: ...


class TaskRepository(Protocol):
    def save(self, task: Task) -> None: ...
    def get(self, task_id: UUID) -> Task | None: ...
    def list_by_exam(self, exam_id: UUID) -> list[Task]:
        """In document order."""
        ...

    def list_by_topic(self, topic_id: UUID) -> list[Task]: ...
    def delete(self, task_id: UUID) -> None: ...
    def delete_by_exam(self, exam_id: UUID) -> None: ...


class AttemptRepository(Protocol):
    def add(self, attempt: Attempt) -> None:
        """Attempts are immutable: they can be added but never changed."""
        ...

    def list_by_task(self, task_id: UUID) -> list[Attempt]:
        """Oldest first."""
        ...


class ReviewStateRepository(Protocol):
    def save(self, state: ReviewState) -> None: ...
    def get(self, task_id: UUID) -> ReviewState | None: ...


class UnitOfWork(Protocol):
    """One database transaction. Nothing is persisted unless ``commit`` is called."""

    subjects: SubjectRepository
    topics: TopicRepository
    exams: ExamRepository
    tasks: TaskRepository
    attempts: AttemptRepository
    review_states: ReviewStateRepository

    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...
    def commit(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]


# --- files -------------------------------------------------------------------


class FileStore(Protocol):
    """Blob storage addressed by slash-separated keys such as ``exams/<id>/exam.pdf``."""

    def write(self, key: str, data: bytes) -> None: ...
    def read(self, key: str) -> bytes:
        """Raises FileNotFoundError if nothing is stored under ``key``."""
        ...

    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None:
        """Remove one file. Removing a file that does not exist is not an error."""
        ...

    def delete_tree(self, prefix: str) -> None:
        """Remove every file whose key starts with ``prefix`` followed by a slash."""
        ...


# --- PDF rendering -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RenderedRegion:
    """A region as an image. ``region`` is what the image shows: the requested
    region with empty space above and below its content trimmed away."""

    region: Region
    png: bytes


class PageRenderer(Protocol):
    """Turns a PDF into images. Raises ``InvalidPdf`` for unreadable input."""

    def count_pages(self, pdf: bytes) -> int: ...
    def render_pages(self, pdf: bytes) -> Iterator[bytes]:
        """PNG bytes for every page, in page order."""
        ...

    def render_regions(self, pdf: bytes, regions: Sequence[Region]) -> list[RenderedRegion | None]:
        """One image per region, in the same order; None for a region with nothing on it."""
        ...


# --- task extraction ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExtractedSection:
    """One task or sub-task found in a document, before it becomes a Task.

    ``number`` is the full label ("3" or "3b"); ``parent_number`` is set for
    sub-tasks. ``text`` is the plain text inside ``regions``.
    """

    number: str
    regions: tuple[Region, ...]
    text: str = ""
    parent_number: str | None = None
    title: str | None = None
    points: float | None = None


class ExtractionService(Protocol):
    """Finds the tasks in an exam or solution PDF.

    Returns every section in document order, including repeated language
    versions; choosing between those is the caller's job. A document in which
    no tasks can be told apart comes back as one section per page, so that no
    page is ever dropped. Raises ``InvalidPdf`` for unreadable input.
    """

    def extract(self, pdf: bytes) -> list[ExtractedSection]: ...


# --- background processing ---------------------------------------------------


class JobQueue(Protocol):
    def enqueue(self, exam_id: UUID) -> None:
        """Schedule the exam for processing and return immediately."""
        ...


@dataclass(frozen=True, slots=True)
class Progress:
    stage: str
    done: int
    total: int


class ProgressTracker(Protocol):
    """Live progress of exams being processed. Not persisted."""

    def report(self, exam_id: UUID, progress: Progress) -> None: ...
    def get(self, exam_id: UUID) -> Progress | None: ...
    def clear(self, exam_id: UUID) -> None: ...
