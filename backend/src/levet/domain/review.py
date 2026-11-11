from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class ReviewPhase(StrEnum):
    LEARNING = "learning"
    REVIEW = "review"
    RELEARNING = "relearning"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReviewState:
    """Spaced-repetition state of one task.

    Mirrors the fields of an FSRS card so it can be converted to and from one
    without loss. ``stability`` and ``difficulty`` are None until the first review.
    """

    task_id: UUID
    due: datetime
    phase: ReviewPhase = ReviewPhase.LEARNING
    step: int | None = 0
    stability: float | None = None
    difficulty: float | None = None
    last_review: datetime | None = None

    def __post_init__(self) -> None:
        if self.due.tzinfo is None:
            raise ValueError("due must be timezone-aware")
        if self.last_review is not None and self.last_review.tzinfo is None:
            raise ValueError("last_review must be timezone-aware")
        object.__setattr__(self, "due", self.due.astimezone(UTC))
        if self.last_review is not None:
            object.__setattr__(self, "last_review", self.last_review.astimezone(UTC))
        object.__setattr__(self, "phase", ReviewPhase(self.phase))

    def is_due(self, now: datetime) -> bool:
        return self.due <= now
