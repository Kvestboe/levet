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
