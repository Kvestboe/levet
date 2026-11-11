"""Background processing of an uploaded exam.

So far the pipeline renders every page of the exam (and of its solution, if
one was uploaded) to a PNG. Task extraction slots in after rendering.
"""

import logging
from uuid import UUID

from levet.application import storage_keys
from levet.application.errors import InvalidPdf
from levet.application.ports import (
    FileStore,
    PageRenderer,
    Progress,
    ProgressTracker,
    UnitOfWorkFactory,
)
from levet.application.storage_keys import PageKind
from levet.domain import Exam, ExamStatus

log = logging.getLogger(__name__)

STAGE_RENDERING = "rendering"
INTERRUPTED_MESSAGE = "Processing was interrupted by a server restart."

_MAX_ATTEMPTS = 2
_MAX_ERROR_LENGTH = 500
_DOCUMENT_NAMES = {PageKind.EXAM: "Exam PDF", PageKind.SOLUTION: "Solution PDF"}


class ExamProcessor:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        files: FileStore,
        renderer: PageRenderer,
        progress: ProgressTracker,
    ) -> None:
        self._uow_factory = uow_factory
        self._files = files
        self._renderer = renderer
        self._progress = progress

    def process(self, exam_id: UUID) -> None:
        """Run the pipeline for one exam. Never raises for a pipeline failure.

        A failed run is retried once. If it fails again, or the failure is one
        a retry cannot fix, the exam is marked ``failed`` with the error.
        """
        error: Exception | None = None
        try:
            for attempt in range(1, _MAX_ATTEMPTS + 1):
                try:
                    self._run(exam_id)
                    return
                except InvalidPdf as exc:
                    error = exc
                    break
                except Exception as exc:
                    log.warning(
                        "processing exam %s failed (attempt %d of %d)",
                        exam_id,
                        attempt,
                        _MAX_ATTEMPTS,
                        exc_info=True,
                    )
                    error = exc
        finally:
            self._progress.clear(exam_id)
        self._mark_failed(exam_id, _describe(error))

    def recover_interrupted(self) -> int:
        """Fail exams left in ``processing`` by a previous run of the server.

        The job queue lives in memory, so such exams would otherwise stay in
        ``processing`` for ever. Returns how many exams were marked failed.
        """
        with self._uow_factory() as uow:
            stuck = uow.exams.list_by_status(ExamStatus.PROCESSING)
            for exam in stuck:
                uow.exams.save(exam.fail(INTERRUPTED_MESSAGE))
            uow.commit()
        return len(stuck)

    def _run(self, exam_id: UUID) -> None:
        exam = self._load_processing(exam_id)
        if exam is None:
            return

        documents = [(PageKind.EXAM, self._files.read(exam.pdf_key))]
        if exam.solution_pdf_key is not None:
            documents.append((PageKind.SOLUTION, self._files.read(exam.solution_pdf_key)))

        page_counts = {kind: self._count_pages(kind, pdf) for kind, pdf in documents}
        total = sum(page_counts.values())
        done = 0
        self._progress.report(exam_id, Progress(STAGE_RENDERING, done, total))

        for kind, pdf in documents:
            rendered = 0
            for number, png in enumerate(self._renderer.render_pages(pdf), start=1):
                self._files.write(storage_keys.page_image(exam_id, kind, number), png)
                rendered += 1
                done += 1
                self._progress.report(exam_id, Progress(STAGE_RENDERING, done, total))
            if rendered != page_counts[kind]:
                # Never carry on with pages missing.
                raise RuntimeError(
                    f"{_DOCUMENT_NAMES[kind]}: rendered {rendered} of {page_counts[kind]} pages"
                )

        with self._uow_factory() as uow:
            exam = uow.exams.get(exam_id)
            if exam is None or exam.status is not ExamStatus.PROCESSING:
                return
            exam = exam.with_pages(
                page_counts[PageKind.EXAM], page_counts.get(PageKind.SOLUTION)
            ).mark_needs_review()
            uow.exams.save(exam)
            uow.commit()

    def _count_pages(self, kind: PageKind, pdf: bytes) -> int:
        try:
            return self._renderer.count_pages(pdf)
        except InvalidPdf as exc:
            raise InvalidPdf(f"{_DOCUMENT_NAMES[kind]}: {exc}") from exc

    def _load_processing(self, exam_id: UUID) -> Exam | None:
        with self._uow_factory() as uow:
            exam = uow.exams.get(exam_id)
        if exam is None or exam.status is not ExamStatus.PROCESSING:
            log.info("skipping exam %s: nothing to process", exam_id)
            return None
        return exam

    def _mark_failed(self, exam_id: UUID, error: str) -> None:
        with self._uow_factory() as uow:
            exam = uow.exams.get(exam_id)
            if exam is None or exam.status is not ExamStatus.PROCESSING:
                return
            uow.exams.save(exam.fail(error))
            uow.commit()


def _describe(error: Exception | None) -> str:
    if error is None:
        return "Processing failed."
    message = str(error).strip()
    if not isinstance(error, InvalidPdf):
        message = f"{type(error).__name__}: {message}" if message else type(error).__name__
    if len(message) > _MAX_ERROR_LENGTH:
        message = message[: _MAX_ERROR_LENGTH - 1] + "…"
    return message
