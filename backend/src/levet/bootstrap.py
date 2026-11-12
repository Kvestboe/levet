"""Composition root: wires the adapters to the use cases."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine

from levet.adapters.db.engine import create_session_factory, create_sqlite_engine
from levet.adapters.db.migrate import run_migrations
from levet.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from levet.adapters.extraction.layout_extractor import LayoutExtractor
from levet.adapters.files.local import LocalFileStore
from levet.adapters.http.auth import LoginThrottle, SessionManager, load_or_create_secret_key
from levet.adapters.jobs.worker import InMemoryProgress, ThreadedJobQueue
from levet.adapters.pdf.pymupdf_renderer import PyMuPdfRenderer
from levet.application.exams import ExamService
from levet.application.ports import Clock
from levet.application.processing import ExamProcessor
from levet.application.review import ReviewService
from levet.application.subjects import SubjectService
from levet.config import Settings

log = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Container:
    settings: Settings
    engine: Engine
    subjects: SubjectService
    exams: ExamService
    review: ReviewService
    processor: ExamProcessor
    jobs: ThreadedJobQueue
    sessions: SessionManager
    throttle: LoginThrottle

    def start(self) -> None:
        recovered = self.processor.recover_interrupted()
        if recovered:
            log.warning("marked %d interrupted exam(s) as failed; they can be retried", recovered)
        self.jobs.start()

    def stop(self) -> None:
        self.jobs.stop()
        self.engine.dispose()


def build_container(settings: Settings, clock: Clock = utc_now) -> Container:
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    engine = create_sqlite_engine(settings.db_path)
    run_migrations(engine)
    session_factory = create_session_factory(engine)

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    files = LocalFileStore(settings.files_dir)
    progress = InMemoryProgress()
    renderer = PyMuPdfRenderer(settings.render_dpi)
    processor = ExamProcessor(
        uow_factory,
        files,
        renderer,
        LayoutExtractor(),
        progress,
        preferred_language=settings.preferred_language,
    )
    jobs = ThreadedJobQueue(processor.process)

    secret_key = settings.secret_key or load_or_create_secret_key(settings.secret_key_path)

    return Container(
        settings=settings,
        engine=engine,
        subjects=SubjectService(uow_factory),
        exams=ExamService(uow_factory, files, jobs, progress, clock),
        review=ReviewService(uow_factory, files, renderer),
        processor=processor,
        jobs=jobs,
        sessions=SessionManager(
            settings.password, secret_key, max_age_seconds=settings.session_days * 86_400
        ),
        throttle=LoginThrottle(),
    )
