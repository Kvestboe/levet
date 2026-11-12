"""Finds tasks in a document from its layout alone. Pure: no PDF library, no I/O.

The input is every line of text with its position, size and weight. The
output is a list of sections, each a task or sub-task with the bands of the
pages it occupies. A section runs from its own heading or label to the next
one, so everything between the first task heading and the end of the last
task belongs to some section.

What is recognised:

* task headings: "Oppgave 3", "Oppgåve 3", "Oppg. 3 [15%]", "Problem 3",
  "Ekstraoppgave 8: Title" and the like, set in bold, in a larger size or
  alone on their line; and the bare question numbers that Inspera prints in
  the left margin next to a bold title;
* sub-task labels "a)", "b)" ... at the left edge of the text, in order;
* in tasks without such labels, one part per "Velg ett alternativ" prompt;
* "Maks poeng: 5" lines, which end a task and give its points;
* running headers and footers, which are left out.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from levet.application.ports import ExtractedSection
from levet.domain import Region


@dataclass(frozen=True, slots=True)
class PageSize:
    width: float
    height: float


@dataclass(frozen=True, slots=True)
class Line:
    """One run of text on a page. Coordinates are in points from the top-left corner."""

    page: int  # 1-based
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    bold: bool = False  # whether the line starts in bold
    size: float = 11.0


@dataclass(frozen=True, slots=True)
class _Row:
    """The lines that sit side by side on one visual row, left to right."""

    lines: tuple[Line, ...]

    @property
    def page(self) -> int:
        return self.lines[0].page

    @property
    def x0(self) -> float:
        return self.lines[0].x0

    @property
    def y0(self) -> float:
        return min(line.y0 for line in self.lines)

    @property
    def y1(self) -> float:
        return max(line.y1 for line in self.lines)

    @property
    def text(self) -> str:
        return " ".join(line.text for line in self.lines)

    @property
    def bold(self) -> bool:
        return self.lines[0].bold

    @property
    def size(self) -> float:
        return max(line.size for line in self.lines)

    @property
    def key(self) -> tuple[int, float]:
        return (self.page, self.y0)


_HEADING = re.compile(
    r"^(?:(?P<index>\d{1,3})\s+)?"
    r"(?:ekstra)?(?:oppg(?:ave|åve|\.)?|exercise|problem|task|question|spørsmål)"
    r"\s*(?P<number>\d{1,3})\b\s*[:.)–-]?\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_MARGIN_INDEX = re.compile(r"^\d{1,3}$")
_INDEXED_TITLE = re.compile(r"^(?P<index>\d{1,3})\s+(?P<rest>\D.*)$")
_SUBTASK = re.compile(r"^\(?(?P<letter>[a-z])\)(?:\s|$)")
_POINTS_LINE = re.compile(
    r"^(?:maks(?:imal)?\.?\s*poeng|max(?:imum)?\.?\s*(?:points|marks|score))"
    r"\s*:?\s*(?P<points>\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
_POINTS_IN_TITLE = re.compile(
    r"[\[(]\s*(?P<points>\d+(?:[.,]\d+)?)\s*(?:%|poeng|points|pts|p)\s*[\])]", re.IGNORECASE
)
_PROMPT = re.compile(
    r"^(?:velg|vel)\s+(?:ett|eitt|et|en|ein)\b.*alternativ|^select\s+(?:one|an)\b.*alternative",
    re.IGNORECASE,
)

# Fractions of the page height in which running headers and footers are looked for.
_HEADER_ZONE = 0.06
_FOOTER_ZONE = 0.08
_PAD = 4.0  # points of air kept above a heading or label when cutting
_MIN_BAND = 3.0  # points; thinner bands are dropped


def segment(pages: list[PageSize], lines: list[Line]) -> list[ExtractedSection]:
    """Split a document into task sections. See the module docstring."""
    if not pages:
        return []
    layout = _Layout.of(pages, lines)
    tasks = _find_tasks(layout)
    if not tasks:
        return _one_section_per_page(layout)

    sections: list[ExtractedSection] = []
    for task in tasks:
        sections.extend(_sections_of(task, layout))
    return sections


# --- layout: rows, margins and what counts as body text ----------------------


@dataclass(frozen=True, slots=True)
class _Layout:
    pages: tuple[PageSize, ...]
    rows: tuple[_Row, ...]  # body rows in reading order; headers and footers removed
    top: float  # content area, as fractions of the page height
    bottom: float
    left: float  # horizontal extent of the content, as fractions of the page width
    right: float
    body_left: float  # x where ordinary text lines start, in points
    body_size: float

    @classmethod
    def of(cls, pages: list[PageSize], lines: list[Line]) -> "_Layout":
        lines = [line for line in lines if line.text.strip() and 1 <= line.page <= len(pages)]
        furniture = _furniture(pages, lines)
        body = [line for line in lines if line not in furniture]

        top = max(
            (
                line.y1 / pages[line.page - 1].height
                for line in furniture
                if _in_header(line, pages)
            ),
            default=0.0,
        )
        bottom = min(
            (
                line.y0 / pages[line.page - 1].height
                for line in furniture
                if not _in_header(line, pages)
            ),
            default=1.0,
        )
        left = min((line.x0 / pages[line.page - 1].width for line in body), default=0.0)
        right = max((line.x1 / pages[line.page - 1].width for line in body), default=1.0)
        margin = 0.012
        return cls(
            pages=tuple(pages),
            rows=tuple(_rows(body)),
            top=min(top + 0.002, 0.2),
            bottom=max(bottom - 0.002, 0.8),
            left=max(0.0, left - margin),
            right=min(1.0, right + margin),
            body_left=_body_left(body),
            body_size=_most_common([round(line.size, 1) for line in body], default=11.0),
        )

    def height(self, page: int) -> float:
        return self.pages[page - 1].height

    def content_top(self, page: int) -> float:
        return self.top * self.height(page)

    def content_bottom(self, page: int) -> float:
        return self.bottom * self.height(page)

    def at_body_left(self, row: _Row) -> bool:
        return row.x0 <= self.body_left + 0.02 * self.pages[row.page - 1].width


def _in_header(line: Line, pages: list[PageSize]) -> bool:
    return line.y1 <= _HEADER_ZONE * pages[line.page - 1].height


def _furniture(pages: list[PageSize], lines: list[Line]) -> set[Line]:
    """Lines that repeat at the same spot near the top or bottom of most pages."""
    if len(pages) < 3:
        return set()
    seen: dict[tuple[str, str, float], list[Line]] = defaultdict(list)
    for line in lines:
        height = pages[line.page - 1].height
        if line.y1 <= _HEADER_ZONE * height:
            zone = "header"
        elif line.y0 >= (1 - _FOOTER_ZONE) * height:
            zone = "footer"
        else:
            continue
        # Page numbers change from page to page; everything else must match.
        text = re.sub(r"\d+", "#", line.text.strip())
        seen[(zone, text, round(line.y0 / height, 2))].append(line)

    needed = max(3, 0.6 * len(pages))
    furniture: set[Line] = set()
    for group in seen.values():
        if len({line.page for line in group}) >= needed:
            furniture.update(group)
    return furniture


def _rows(lines: list[Line]) -> list[_Row]:
    """Group lines that overlap vertically into rows, in reading order."""
    rows: list[list[Line]] = []
    for line in sorted(lines, key=lambda line: (line.page, line.y0, line.x0)):
        current = rows[-1] if rows else None
        if current and current[0].page == line.page and _same_row(current[0], line):
            current.append(line)
        else:
            rows.append([line])
    return [_Row(tuple(sorted(row, key=lambda line: line.x0))) for row in rows]


def _same_row(a: Line, b: Line) -> bool:
    overlap = min(a.y1, b.y1) - max(a.y0, b.y0)
    return overlap > 0.5 * min(a.y1 - a.y0, b.y1 - b.y0)


def _body_left(lines: list[Line]) -> float:
    """The left edge of ordinary text: the leftmost x at which a fair share of lines start.

    Not simply the most common x: indented answer options can outnumber the
    lines of running text.
    """
    if not lines:
        return 0.0
    counts = Counter(round(line.x0 / 2) * 2 for line in lines)
    for x in sorted(counts):
        if counts[x] >= 0.1 * len(lines):
            return float(x)
    return float(min(counts))


def _most_common(values: list[float], default: float) -> float:
    return Counter(values).most_common(1)[0][0] if values else default


# --- tasks -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Cut:
    """A position in the document: a page and a height on it, in points."""

    page: int
    y: float

    @property
    def key(self) -> tuple[int, float]:
        return (self.page, self.y)


@dataclass(frozen=True, slots=True)
class _TaskSpan:
    number: int
    title: str | None
    points: float | None
    start: _Cut
    end: _Cut
    rows: tuple[_Row, ...]  # body rows inside the span, heading row first


def _find_tasks(layout: _Layout) -> list[_TaskSpan]:
    headings: list[tuple[int, _Row, int, str | None, float | None]] = []
    for index, row in enumerate(layout.rows):
        heading = _as_heading(row, layout)
        if heading is None:
            continue
        number, title, points = heading
        previous = headings[-1] if headings else None
        if (
            previous
            and previous[2] == number
            and index - previous[0] == 1
            and previous[1].page == row.page
        ):
            # The same heading printed twice ("3 Title" above "Oppgave 3: Title").
            headings[-1] = (*previous[:3], previous[3] or title, previous[4] or points)
            continue
        headings.append((index, row, number, title, points))
    if not headings:
        return []

    last_page = len(layout.pages)
    tasks: list[_TaskSpan] = []
    for position, (index, row, number, title, points) in enumerate(headings):
        following = headings[position + 1] if position + 1 < len(headings) else None
        stop_index = following[0] if following else len(layout.rows)
        rows = layout.rows[index:stop_index]
        start = _cut_above(row, layout, index)
        end = (
            _cut_above(following[1], layout, following[0])
            if following
            else _Cut(last_page, layout.content_bottom(last_page))
        )
        # A "Maks poeng" line closes the task: what follows it (blank space,
        # appendices) is not part of it.
        for candidate in rows[1:]:
            match = _POINTS_LINE.match(candidate.text)
            if match:
                points = _number(match.group("points"))
                end = _Cut(
                    candidate.page, min(candidate.y1 + _PAD, layout.content_bottom(candidate.page))
                )
                rows = tuple(r for r in rows if r.key <= candidate.key)
                break
        tasks.append(_TaskSpan(number, title, points, start, end, tuple(rows)))
    return tasks


def _as_heading(row: _Row, layout: _Layout) -> tuple[int, str | None, float | None] | None:
    """(number, title, points) if the row is a task heading."""
    prominent = row.bold or row.size >= layout.body_size * 1.15
    match = _HEADING.match(row.text)
    if match and (prominent or not match.group("rest").strip()):
        title, points = _title_and_points(match.group("rest"))
        return int(match.group("number")), title, points

    # Inspera: the question number in the left margin, followed by a bold title
    # that need not contain the word "Oppgave".
    first = row.lines[0]
    if not first.bold or first.x0 >= layout.body_left - 5:
        return None
    if len(row.lines) > 1 and row.lines[1].bold and _MARGIN_INDEX.match(first.text.strip()):
        title, points = _title_and_points(" ".join(line.text for line in row.lines[1:]))
        return int(first.text), title, points
    match = _INDEXED_TITLE.match(row.text)
    if match and row.size >= layout.body_size * 1.15:
        title, points = _title_and_points(match.group("rest"))
        return int(match.group("index")), title, points
    return None


def _title_and_points(rest: str) -> tuple[str | None, float | None]:
    points = None
    match = _POINTS_IN_TITLE.search(rest)
    if match:
        points = _number(match.group("points"))
        rest = rest[: match.start()] + rest[match.end() :]
    title = " ".join(rest.split()).strip(" :.-–")
    return (title or None), points


def _number(text: str) -> float:
    return float(text.replace(",", "."))


def _cut_above(row: _Row, layout: _Layout, index: int) -> _Cut:
    """Where to cut so that ``row`` starts a new band: a little above it, but
    never into the row before."""
    limit = layout.content_top(row.page)
    if index > 0:
        previous = layout.rows[index - 1]
        if previous.page == row.page and previous.y1 <= row.y0:
            limit = max(limit, (previous.y1 + row.y0) / 2)
    return _Cut(row.page, max(limit, row.y0 - _PAD))


# --- sections within a task --------------------------------------------------


def _sections_of(task: _TaskSpan, layout: _Layout) -> list[ExtractedSection]:
    starts = _lettered_parts(task, layout) or _prompted_parts(task, layout)
    number = str(task.number)
    if not starts:
        return [_section(number, None, task, task.start, task.end, layout)]

    share = None if task.points is None else task.points / len(starts)
    sections = [_section(number, None, task, task.start, starts[0][1], layout)]
    for position, (letter, start) in enumerate(starts):
        end = starts[position + 1][1] if position + 1 < len(starts) else task.end
        sections.append(
            _section(f"{number}{letter}", number, task, start, end, layout, points=share)
        )
    return sections


def _lettered_parts(task: _TaskSpan, layout: _Layout) -> list[tuple[str, _Cut]]:
    """Starts of the parts labelled "a)", "b)" ... in alphabetical order."""
    parts: list[tuple[str, _Cut]] = []
    for row in task.rows[1:]:
        match = _SUBTASK.match(row.lines[0].text)
        if not match or not layout.at_body_left(row):
            continue
        letter = match.group("letter")
        expected_first = not parts and letter in "ab"
        follows = bool(parts) and parts[-1][0] < letter <= chr(ord(parts[-1][0]) + 2)
        if expected_first or follows:
            parts.append((letter, _cut_above(row, layout, layout.rows.index(row))))
    return parts


def _prompted_parts(task: _TaskSpan, layout: _Layout) -> list[tuple[str, _Cut]]:
    """Starts of unlabelled parts, one per answer prompt, lettered in order.

    Each part after the first begins at the first line of running text below
    the previous prompt (its answer options are indented, so they are skipped).
    The first part begins at the paragraph directly above its prompt; what
    comes before is the introduction shared by all parts.
    """
    rows = task.rows[1:]
    prompts = [index for index, row in enumerate(rows) if _PROMPT.match(row.text)]
    if len(prompts) < 2:
        return []

    starts: list[_Row] = []
    first = prompts[0]
    while (
        first > 0
        and layout.at_body_left(rows[first - 1])
        and rows[first - 1].page == rows[first].page
        and rows[first].y0 - rows[first - 1].y1 <= 0.6 * (rows[first].y1 - rows[first].y0)
    ):
        first -= 1
    starts.append(rows[first])

    for previous, current in zip(prompts, prompts[1:], strict=False):
        opening = next(
            (
                row
                for row in rows[previous + 1 : current + 1]
                if layout.at_body_left(row) and row is not rows[previous]
            ),
            None,
        )
        if opening is not None and opening is not rows[current]:
            starts.append(opening)
        elif opening is rows[current]:
            starts.append(rows[current])

    return [
        (chr(ord("a") + position), _cut_above(row, layout, layout.rows.index(row)))
        for position, row in enumerate(starts)
    ]


def _section(
    number: str,
    parent: str | None,
    task: _TaskSpan,
    start: _Cut,
    end: _Cut,
    layout: _Layout,
    points: float | None = None,
) -> ExtractedSection:
    regions = _bands(start, end, layout)
    rows = [
        row for row in task.rows if start.key <= (row.page, row.y0 + 0.01) and row.key < end.key
    ]
    return ExtractedSection(
        number=number,
        parent_number=parent,
        title=task.title if parent is None else None,
        points=task.points if parent is None else points,
        regions=regions,
        text="\n".join(row.text for row in rows),
    )


def _bands(start: _Cut, end: _Cut, layout: _Layout) -> tuple[Region, ...]:
    """The page bands between two cuts: the rest of the first page, whole pages
    in between, and the top of the last."""
    regions: list[Region] = []
    for page in range(start.page, end.page + 1):
        top = start.y if page == start.page else layout.content_top(page)
        bottom = end.y if page == end.page else layout.content_bottom(page)
        if bottom - top < _MIN_BAND:
            continue
        height = layout.height(page)
        regions.append(
            Region(
                page=page,
                top=max(0.0, top / height),
                bottom=min(1.0, bottom / height),
                left=layout.left,
                right=layout.right,
            )
        )
    return tuple(regions)


def _one_section_per_page(layout: _Layout) -> list[ExtractedSection]:
    """Fallback when no task can be told apart: every page becomes one section."""
    rows_by_page: dict[int, list[_Row]] = defaultdict(list)
    for row in layout.rows:
        rows_by_page[row.page].append(row)
    return [
        ExtractedSection(
            number=str(page),
            title=f"Page {page}",
            regions=(Region(page=page, top=0.0, bottom=1.0),),
            text="\n".join(row.text for row in rows_by_page[page]),
        )
        for page in range(1, len(layout.pages) + 1)
    ]
