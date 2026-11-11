from dataclasses import dataclass
from datetime import date


def normalize_subject_code(code: str) -> str:
    """Canonical form of a course code, so ``idatt2202 `` and ``IDATT2202`` are one subject."""
    normalized = code.strip().upper()
    if not normalized:
        raise ValueError("subject code must not be empty")
    return normalized


@dataclass(frozen=True, slots=True)
class Subject:
    """A course. The course code is the natural key."""

    code: str
    name: str
    exam_date: date | None = None

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name:
            raise ValueError("subject name must not be empty")
        object.__setattr__(self, "code", normalize_subject_code(self.code))
        object.__setattr__(self, "name", name)

    def days_until_exam(self, today: date) -> int | None:
        """Whole days until the exam; negative once it has passed, None if no date is set."""
        if self.exam_date is None:
            return None
        return (self.exam_date - today).days
