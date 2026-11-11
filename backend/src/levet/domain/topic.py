from dataclasses import dataclass, field
from uuid import UUID, uuid4

from levet.domain.subject import normalize_subject_code


@dataclass(frozen=True, slots=True, kw_only=True)
class Topic:
    """A topic within one subject. Tasks are tagged with one to three of these."""

    subject_code: str
    name: str
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name:
            raise ValueError("topic name must not be empty")
        object.__setattr__(self, "subject_code", normalize_subject_code(self.subject_code))
        object.__setattr__(self, "name", name)
