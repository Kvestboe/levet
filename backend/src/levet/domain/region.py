from dataclasses import dataclass, replace
from typing import Self


@dataclass(frozen=True, slots=True)
class Region:
    """A rectangle on one page of a PDF.

    ``page`` is 1-based. The edges are fractions of the page's width and
    height (0 = left/top, 1 = right/bottom), so a region means the same thing
    at any rendering resolution.
    """

    page: int
    top: float
    bottom: float
    left: float = 0.0
    right: float = 1.0

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("pages are 1-based")
        if not 0.0 <= self.top < self.bottom <= 1.0:
            raise ValueError("a region needs 0 <= top < bottom <= 1")
        if not 0.0 <= self.left < self.right <= 1.0:
            raise ValueError("a region needs 0 <= left < right <= 1")

    @property
    def height(self) -> float:
        return self.bottom - self.top

    def split_at(self, fraction: float) -> tuple[Self, Self]:
        """Cut the region horizontally; ``fraction`` is how far down it (0-1) the cut goes."""
        if not 0.0 < fraction < 1.0:
            raise ValueError("a region can only be split strictly inside it")
        cut = self.top + fraction * self.height
        return replace(self, bottom=cut), replace(self, top=cut)


def source_pages(regions: tuple[Region, ...]) -> tuple[int, ...]:
    """The pages a sequence of regions touches, in ascending order."""
    return tuple(sorted({region.page for region in regions}))
