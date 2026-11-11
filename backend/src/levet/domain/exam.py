from dataclasses import dataclass, field, replace
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
    ``solution_pdf_key`` are file-store keys, not paths.
    """

    subject_code: str
    label: str
    pdf_key: str
    solution_pdf_key: str | None = None
    status: ExamStatus = ExamStatus.PROCESSING
    error: str | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        label = self.label.strip()
        if not label:
            raise ValueError("exam label must not be empty")
        if not self.pdf_key:
            raise ValueError("exam must reference its original PDF")
        if (self.status is ExamStatus.FAILED) != (self.error is not None):
            raise ValueError("an exam carries an error exactly when its status is 'failed'")
        object.__setattr__(self, "subject_code", normalize_subject_code(self.subject_code))
        object.__setattr__(self, "label", label)

    def mark_needs_review(self) -> Self:
        """Extraction finished; the tasks are waiting for manual review."""
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
        """Send a failed exam back through processing."""
        self._require(ExamStatus.FAILED, target=ExamStatus.PROCESSING)
        return replace(self, status=ExamStatus.PROCESSING, error=None)

    def _require(self, expected: ExamStatus, *, target: ExamStatus) -> None:
        if self.status is not expected:
            raise InvalidTransition(
                f"exam {self.label!r} is {self.status.value}; "
                f"only a {expected.value} exam can become {target.value}"
            )
