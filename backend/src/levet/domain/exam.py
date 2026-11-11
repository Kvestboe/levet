from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from levet.domain.subject import normalize_subject_code


class ExamStatus(StrEnum):
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    READY = "ready"
    FAILED = "failed"


class InvalidTransition(Exception):
    """An exam was asked to move to a status it cannot reach from its current one."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Exam:
    """One uploaded exam paper.

    Lifecycle::

        processing ──► needs_review ──► ready
            │  ▲
            ▼  │ retry
           failed

    Only tasks of a ``ready`` exam take part in practice. ``pdf_key`` and
    ``solution_pdf_key`` are file-store keys, not paths. The page counts are
    None until the pages have been rendered.
    """

    subject_code: str
    label: str
    pdf_key: str
    uploaded_at: datetime
    solution_pdf_key: str | None = None
    status: ExamStatus = ExamStatus.PROCESSING
    error: str | None = None
    page_count: int | None = None
    solution_page_count: int | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        label = self.label.strip()
        if not label:
            raise ValueError("exam label must not be empty")
        if not self.pdf_key:
            raise ValueError("exam must reference its original PDF")
        if self.uploaded_at.tzinfo is None:
            raise ValueError("uploaded_at must be timezone-aware")
        status = ExamStatus(self.status)
        if (status is ExamStatus.FAILED) != (self.error is not None):
            raise ValueError("an exam carries an error exactly when its status is 'failed'")
        if self.page_count is not None and self.page_count < 1:
            raise ValueError("a rendered exam has at least one page")
        if self.solution_page_count is not None:
            if self.solution_pdf_key is None:
                raise ValueError("an exam without a solution PDF cannot have solution pages")
            if self.solution_page_count < 1:
                raise ValueError("a rendered solution has at least one page")
        object.__setattr__(self, "subject_code", normalize_subject_code(self.subject_code))
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "uploaded_at", self.uploaded_at.astimezone(UTC))

    def with_pages(self, page_count: int, solution_page_count: int | None = None) -> Self:
        """Record how many page images were rendered from the exam and its solution."""
        return replace(self, page_count=page_count, solution_page_count=solution_page_count)

    def mark_needs_review(self) -> Self:
        """Processing finished; the exam is waiting for manual review."""
        self._require(ExamStatus.PROCESSING, target=ExamStatus.NEEDS_REVIEW)
        return replace(self, status=ExamStatus.NEEDS_REVIEW)

    def approve(self) -> Self:
        """Review finished; the exam's tasks enter practice."""
        self._require(ExamStatus.NEEDS_REVIEW, target=ExamStatus.READY)
        return replace(self, status=ExamStatus.READY)

    def fail(self, error: str) -> Self:
        """Processing gave up; ``error`` is what the UI shows next to the retry button."""
        self._require(ExamStatus.PROCESSING, target=ExamStatus.FAILED)
        if not error.strip():
            raise ValueError("a failed exam needs an error message")
        return replace(self, status=ExamStatus.FAILED, error=error.strip())

    def retry(self) -> Self:
        """Send a failed exam back through processing from the start."""
        self._require(ExamStatus.FAILED, target=ExamStatus.PROCESSING)
        return replace(
            self,
            status=ExamStatus.PROCESSING,
            error=None,
            page_count=None,
            solution_page_count=None,
        )

    def _require(self, expected: ExamStatus, *, target: ExamStatus) -> None:
        if self.status is not expected:
            raise InvalidTransition(
                f"exam {self.label!r} is {self.status.value}; "
                f"only a {expected.value} exam can become {target.value}"
            )
