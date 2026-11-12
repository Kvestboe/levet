from datetime import UTC, datetime

import pymupdf
import pytest

from levet.adapters.db.engine import create_session_factory, create_sqlite_engine
from levet.adapters.db.migrate import run_migrations
from levet.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from levet.adapters.files.local import LocalFileStore

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


@pytest.fixture
def now():
    return NOW


@pytest.fixture
def engine(tmp_path):
    engine = create_sqlite_engine(tmp_path / "db" / "levet.db")
    run_migrations(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def uow_factory(engine):
    session_factory = create_session_factory(engine)
    return lambda: SqlAlchemyUnitOfWork(session_factory)


@pytest.fixture
def files(tmp_path):
    return LocalFileStore(tmp_path / "files")


@pytest.fixture
def make_pdf():
    """Builds a real PDF with one page per given text."""

    def build(*page_texts: str) -> bytes:
        document = pymupdf.open()
        for text in page_texts or ("Oppgave 1",):
            page = document.new_page()  # A4
            page.insert_text((72, 100), text, fontsize=14)
        try:
            return document.tobytes()
        finally:
            document.close()

    return build


@pytest.fixture
def build_pdf():
    """Builds a PDF from pages of lines, laid out top to bottom like an exam.

    A line is either a string or ``(text, options)`` with the options ``bold``,
    ``x`` (left edge in points), ``size`` and ``gap`` (extra space above it).
    Every page gets a running header and a page-number footer.
    """

    def build(*pages, header="EXAM-H24"):
        document = pymupdf.open()
        for number, lines in enumerate(pages, start=1):
            page = document.new_page()  # A4: 595 x 842 points
            page.insert_text((500, 25), header, fontsize=10)
            page.insert_text((555, 824), f"{number}/{len(pages)}", fontsize=10)
            y = 60.0
            for line in lines:
                text, options = (line, {}) if isinstance(line, str) else line
                size = options.get("size", 11)
                y += options.get("gap", 0)
                page.insert_text(
                    (options.get("x", 56), y),
                    text,
                    fontsize=size,
                    fontname="hebo" if options.get("bold") else "helv",
                )
                y += size * 1.5
        try:
            return document.tobytes()
        finally:
            document.close()

    return build


def heading(text):
    return (text, {"bold": True, "gap": 6})


def option(text):
    return (text, {"x": 80, "gap": 8})


@pytest.fixture
def exam_pdf(build_pdf):
    """A two-task exam over three pages; task 1 has parts a and b, b runs over a page break."""
    return build_pdf(
        ["Eksamen i statistikk", "Tillatte hjelpemidler: kalkulator."],
        [
            heading("Oppgave 1: Normalfordeling"),
            "La X være normalfordelt med forventning 3.",
            ("a) Hva er sannsynligheten for at X er mindre enn 1?", {"gap": 14}),
            option("0.16"),
            option("0.84"),
            ("b) Hva er variansen til 2X?", {"gap": 480}),
        ],
        [
            option("4"),
            option("8"),
            ("Maks poeng: 2", {"x": 456, "gap": 10}),
            heading("Oppgave 2: Hypotesetest"),
            "Regn ut p-verdien for testen.",
            ("Maks poeng: 3", {"x": 456, "gap": 10}),
        ],
    )


@pytest.fixture
def solution_pdf(build_pdf):
    return build_pdf(
        [
            heading("Oppgave 1: Normalfordeling"),
            ("a)", {"gap": 8}),
            "Standardiserer og slår opp i tabellen: 0.16.",
            ("b)", {"gap": 8}),
            "Var(2X) = 4 Var(X) = 8.",
            heading("Oppgave 2: Hypotesetest"),
            "p-verdien er 0.03.",
        ],
        header="LF-H24",
    )
