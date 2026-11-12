import math
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from levet.domain.region import Region, source_pages

MAX_TOPICS_PER_TASK = 3


@dataclass(frozen=True, slots=True, kw_only=True)
class Task:
    """One task (or sub-task) of an exam.

    A task is shown as it was printed: ``regions`` say where on the exam's
    pages it is, and ``image_keys`` are the file-store keys of those regions
    rendered as images, one per region and in the same order. The same goes for
    the solution, when the exam has one. ``text`` and ``solution_text`` are the
    plain text found in those regions; formulas drawn as graphics are missing
    from it, so it serves search and topic matching, not display.

    A sub-task such as "3b" points at its parent "3" through ``parent_id``; the
    parent holds the context shared by its sub-tasks. ``position`` orders the
    tasks of an exam as they appear in the document.

    A task may have no topics of its own; a sub-task without topics takes its
    parent's. The upper bound of three always holds.
    """

    exam_id: UUID
    number: str
    text: str = ""
    title: str | None = None
    position: int = 0
    parent_id: UUID | None = None
    points: float | None = None
    topic_ids: frozenset[UUID] = frozenset()
    regions: tuple[Region, ...] = ()
    image_keys: tuple[str, ...] = ()
    solution_text: str | None = None
    solution_regions: tuple[Region, ...] = ()
    solution_image_keys: tuple[str, ...] = ()
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        number = self.number.strip()
        if not number:
            raise ValueError("task number must not be empty")
        if self.parent_id == self.id:
            raise ValueError("a task cannot be its own parent")
        if self.position < 0:
            raise ValueError("position must not be negative")
        if self.points is not None and not (math.isfinite(self.points) and self.points >= 0):
            raise ValueError("points must be a non-negative number")

        topic_ids = frozenset(self.topic_ids)
        if len(topic_ids) > MAX_TOPICS_PER_TASK:
            raise ValueError(f"a task can have at most {MAX_TOPICS_PER_TASK} topics")

        title = self.title.strip() if self.title else None

        object.__setattr__(self, "number", number)
        object.__setattr__(self, "title", title or None)
        object.__setattr__(self, "topic_ids", topic_ids)
        object.__setattr__(self, "regions", tuple(self.regions))
        object.__setattr__(self, "image_keys", tuple(self.image_keys))
        object.__setattr__(self, "solution_regions", tuple(self.solution_regions))
        object.__setattr__(self, "solution_image_keys", tuple(self.solution_image_keys))

    @property
    def source_pages(self) -> tuple[int, ...]:
        """1-based page numbers of the exam PDF this task appears on."""
        return source_pages(self.regions)

    @property
    def has_solution(self) -> bool:
        return bool(self.solution_regions or self.solution_text)
