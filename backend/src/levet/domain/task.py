import math
from dataclasses import dataclass, field
from uuid import UUID, uuid4

MAX_TOPICS_PER_TASK = 3


@dataclass(frozen=True, slots=True, kw_only=True)
class Task:
    """One task (or sub-task) extracted from an exam.

    A sub-task such as "3b" points at its parent "3" through ``parent_id`` so the
    shared context from the parent can be shown with it. ``text`` and
    ``solution_text`` are Markdown with LaTeX. ``figure_keys`` are file-store keys
    of the cropped figure images, in display order. ``source_pages`` are 1-based
    page numbers in the original PDF.

    A task may have no topics while its exam is still being processed; the upper
    bound of three always holds.
    """

    exam_id: UUID
    number: str
    text: str
    parent_id: UUID | None = None
    points: float | None = None
    topic_ids: frozenset[UUID] = frozenset()
    figure_keys: tuple[str, ...] = ()
    solution_text: str | None = None
    source_pages: tuple[int, ...] = ()
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        number = self.number.strip()
        if not number:
            raise ValueError("task number must not be empty")
        if self.parent_id == self.id:
            raise ValueError("a task cannot be its own parent")
        if self.points is not None and not (math.isfinite(self.points) and self.points >= 0):
            raise ValueError("points must be a non-negative number")

        topic_ids = frozenset(self.topic_ids)
        if len(topic_ids) > MAX_TOPICS_PER_TASK:
            raise ValueError(f"a task can have at most {MAX_TOPICS_PER_TASK} topics")

        source_pages = tuple(sorted(set(self.source_pages)))
        if any(page < 1 for page in source_pages):
            raise ValueError("source pages are 1-based")

        object.__setattr__(self, "number", number)
        object.__setattr__(self, "topic_ids", topic_ids)
        object.__setattr__(self, "figure_keys", tuple(self.figure_keys))
        object.__setattr__(self, "source_pages", source_pages)
