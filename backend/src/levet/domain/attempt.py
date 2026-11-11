from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4


class Grade(StrEnum):
    """Self-assessed outcome of one attempt, on the Anki scale."""

    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"

    @property
    def score(self) -> float:
        """The grade as a mastery score in [0, 1]."""
        return _GRADE_SCORES[self]


_GRADE_SCORES = {
    Grade.AGAIN: 0.0,
    Grade.HARD: 0.4,
    Grade.GOOD: 0.8,
    Grade.EASY: 1.0,
}


@dataclass(frozen=True, slots=True, kw_only=True)
class Attempt:
    """One logged attempt at a task. Immutable: attempts are appended, never edited."""

    task_id: UUID
    attempted_at: datetime
    grade: Grade
    time_spent: timedelta | None = None
    answer: str | None = None
    note: str | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if self.attempted_at.tzinfo is None:
            raise ValueError("attempted_at must be timezone-aware")
        if self.time_spent is not None and self.time_spent < timedelta(0):
            raise ValueError("time_spent must not be negative")
        object.__setattr__(self, "attempted_at", self.attempted_at.astimezone(UTC))
        object.__setattr__(self, "grade", Grade(self.grade))

    @property
    def score(self) -> float:
        return self.grade.score
