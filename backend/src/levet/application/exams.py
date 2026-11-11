from dataclasses import dataclass
from uuid import UUID, uuid4

from levet.application import storage_keys
from levet.application.errors import Conflict, InvalidInput, NotFound
from levet.application.ports import (
    Clock,
    FileStore,
    JobQueue,
    Progress,
    ProgressTracker,
    UnitOfWorkFactory,
)
from levet.application.storage_keys import PageKind
from levet.domain import Exam, ExamStatus, InvalidTransition
from levet.domain.subject import normalize_subject_code

_PDF_MAGIC = b"%PDF-"


@dataclass(frozen=True, slots=True)
class ExamView:
    """An exam together with its live processing progress, if it is being processed."""

    exam: Exam
    progress: Progress | None = None


class ExamService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        files: FileStore,
        jobs: JobQueue,
        progress: ProgressTracker,
        clock: Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._files = files
        self._jobs = jobs
        self._progress = progress
        self._clock = clock

    def upload(
        self,
        subject_code: str,
        label: str,
        pdf: bytes,
        solution_pdf: bytes | None = None,
    ) -> Exam:
        """Store the uploaded documents and queue the exam for background processing."""
        _require_pdf(pdf, "exam")
        if solution_pdf is not None:
            _require_pdf(solution_pdf, "solution")

        exam_id = uuid4()
        try:
            exam = Exam(
                id=exam_id,
                subject_code=subject_code,
                label=label,
                pdf_key=storage_keys.exam_pdf(exam_id),
                solution_pdf_key=(
                    storage_keys.solution_pdf(exam_id) if solution_pdf is not None else None
                ),
                uploaded_at=self._clock(),
            )
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc

        with self._uow_factory() as uow:
            if uow.subjects.get(exam.subject_code) is None:
                raise NotFound(f"no subject {exam.subject_code}")
            if uow.exams.find_by_label(exam.subject_code, exam.label) is not None:
                raise Conflict(f"{exam.subject_code} already has an exam labelled {exam.label!r}")

            self._files.write(exam.pdf_key, pdf)
            if exam.solution_pdf_key is not None and solution_pdf is not None:
                self._files.write(exam.solution_pdf_key, solution_pdf)
            uow.exams.save(exam)
            uow.commit()

        self._jobs.enqueue(exam.id)
        return exam

    def list_all(self, subject_code: str | None = None) -> list[ExamView]:
        if subject_code is not None:
            try:
                subject_code = normalize_subject_code(subject_code)
            except ValueError as exc:
                raise InvalidInput(str(exc)) from exc
        with self._uow_factory() as uow:
            exams = uow.exams.list_all(subject_code)
        return [self._view(exam) for exam in exams]

    def get(self, exam_id: UUID) -> ExamView:
        with self._uow_factory() as uow:
            exam = uow.exams.get(exam_id)
        if exam is None:
            raise NotFound("no such exam")
        return self._view(exam)

    def retry(self, exam_id: UUID) -> Exam:
        """Send a failed exam through processing again, using the stored documents."""
        with self._uow_factory() as uow:
            exam = uow.exams.get(exam_id)
            if exam is None:
                raise NotFound("no such exam")
            try:
                exam = exam.retry()
            except InvalidTransition as exc:
                raise Conflict(str(exc)) from exc
            uow.exams.save(exam)
            uow.commit()
        self._jobs.enqueue(exam.id)
        return exam

    def page_image(self, exam_id: UUID, kind: PageKind, number: int) -> bytes:
        """PNG of one rendered page; ``number`` is 1-based."""
        exam = self.get(exam_id).exam
        page_count = exam.page_count if kind is PageKind.EXAM else exam.solution_page_count
        if page_count is None or not 1 <= number <= page_count:
            raise NotFound("no such page")
        try:
            return self._files.read(storage_keys.page_image(exam_id, kind, number))
        except FileNotFoundError as exc:
            raise NotFound("no such page") from exc

    def _view(self, exam: Exam) -> ExamView:
        if exam.status is not ExamStatus.PROCESSING:
            return ExamView(exam)
        return ExamView(exam, self._progress.get(exam.id))


def _require_pdf(data: bytes, what: str) -> None:
    # The header may be preceded by a little junk, but must appear early.
    if _PDF_MAGIC not in data[:1024]:
        raise InvalidInput(f"the {what} file is not a PDF")
