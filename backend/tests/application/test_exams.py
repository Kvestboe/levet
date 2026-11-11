from uuid import uuid4

import pytest

from levet.adapters.jobs.worker import InMemoryProgress
from levet.application import storage_keys
from levet.application.errors import Conflict, InvalidInput, NotFound
from levet.application.exams import ExamService
from levet.application.ports import Progress
from levet.application.storage_keys import PageKind
from levet.application.subjects import SubjectService
from levet.domain import ExamStatus

PDF = b"%PDF-1.7\n(exam)"
SOLUTION = b"%PDF-1.7\n(solution)"


class RecordingJobs:
    def __init__(self):
        self.enqueued = []

    def enqueue(self, exam_id):
        self.enqueued.append(exam_id)


@pytest.fixture
def jobs():
    return RecordingJobs()


@pytest.fixture
def progress():
    return InMemoryProgress()


@pytest.fixture
def exams(uow_factory, files, jobs, progress, now):
    SubjectService(uow_factory).create("IDATT2202", "Operativsystemer")
    return ExamService(uow_factory, files, jobs, progress, clock=lambda: now)


def set_exam(uow_factory, exam):
    with uow_factory() as uow:
        uow.exams.save(exam)
        uow.commit()


# --- upload ------------------------------------------------------------------


def test_upload_stores_the_pdf_and_queues_the_exam_for_processing(exams, files, jobs, now):
    exam = exams.upload("idatt2202", " Høst 2023 ", PDF)

    assert exam.subject_code == "IDATT2202"
    assert exam.label == "Høst 2023"
    assert exam.status is ExamStatus.PROCESSING
    assert exam.uploaded_at == now
    assert exam.solution_pdf_key is None
    assert files.read(exam.pdf_key) == PDF
    assert jobs.enqueued == [exam.id]
    assert exams.get(exam.id).exam == exam


def test_upload_with_solution_stores_both_documents(exams, files):
    exam = exams.upload("IDATT2202", "Høst 2023", PDF, SOLUTION)
    assert files.read(exam.pdf_key) == PDF
    assert files.read(exam.solution_pdf_key) == SOLUTION


def test_each_upload_gets_its_own_files(exams, files):
    first = exams.upload("IDATT2202", "Høst 2022", PDF)
    second = exams.upload("IDATT2202", "Høst 2023", b"%PDF-1.7\n(other)")
    assert first.pdf_key != second.pdf_key
    assert files.read(first.pdf_key) == PDF


def test_upload_to_an_unknown_subject_is_rejected_and_nothing_is_kept(exams, jobs):
    with pytest.raises(NotFound):
        exams.upload("TDT4100", "Høst 2023", PDF)
    assert exams.list_all() == []
    assert jobs.enqueued == []


def test_a_second_exam_with_the_same_label_is_a_conflict(exams, jobs):
    first = exams.upload("IDATT2202", "Høst 2023", PDF)
    with pytest.raises(Conflict):
        exams.upload("IDATT2202", "Høst 2023", PDF)
    assert jobs.enqueued == [first.id]


@pytest.mark.parametrize(
    ("pdf", "solution"),
    [(b"", None), (b"PK\x03\x04 a docx", None), (PDF, b"<html>not a pdf</html>")],
)
def test_files_that_are_not_pdfs_are_rejected(exams, jobs, pdf, solution):
    with pytest.raises(InvalidInput):
        exams.upload("IDATT2202", "Høst 2023", pdf, solution)
    assert exams.list_all() == []
    assert jobs.enqueued == []


def test_blank_label_is_invalid_input(exams):
    with pytest.raises(InvalidInput):
        exams.upload("IDATT2202", "  ", PDF)


# --- reading -----------------------------------------------------------------


def test_exams_are_listed_per_subject(exams, uow_factory):
    SubjectService(uow_factory).create("TDT4100", "Objektorientert programmering")
    os_exam = exams.upload("IDATT2202", "Høst 2023", PDF)
    oop_exam = exams.upload("TDT4100", "Vår 2024", PDF)
    assert {view.exam.id for view in exams.list_all()} == {os_exam.id, oop_exam.id}
    assert [view.exam.id for view in exams.list_all("tdt4100")] == [oop_exam.id]


def test_getting_an_unknown_exam_is_not_found(exams):
    with pytest.raises(NotFound):
        exams.get(uuid4())


def test_progress_is_shown_only_while_the_exam_is_processing(exams, progress, uow_factory):
    exam = exams.upload("IDATT2202", "Høst 2023", PDF)
    assert exams.get(exam.id).progress is None

    progress.report(exam.id, Progress("rendering", 3, 10))
    assert exams.get(exam.id).progress == Progress("rendering", 3, 10)
    assert exams.list_all()[0].progress == Progress("rendering", 3, 10)

    set_exam(uow_factory, exam.with_pages(10).mark_needs_review())
    assert exams.get(exam.id).progress is None


# --- retry -------------------------------------------------------------------


def test_retrying_a_failed_exam_requeues_it_with_the_error_cleared(exams, jobs, uow_factory):
    exam = exams.upload("IDATT2202", "Høst 2023", PDF)
    set_exam(uow_factory, exam.fail("boom"))

    retried = exams.retry(exam.id)

    assert retried.status is ExamStatus.PROCESSING
    assert retried.error is None
    assert exams.get(exam.id).exam == retried
    assert jobs.enqueued == [exam.id, exam.id]


def test_only_a_failed_exam_can_be_retried(exams, jobs):
    exam = exams.upload("IDATT2202", "Høst 2023", PDF)
    with pytest.raises(Conflict):
        exams.retry(exam.id)
    assert jobs.enqueued == [exam.id]


def test_retrying_an_unknown_exam_is_not_found(exams):
    with pytest.raises(NotFound):
        exams.retry(uuid4())


# --- page images -------------------------------------------------------------


def test_page_images_are_served_for_rendered_pages_only(exams, files, uow_factory):
    exam = exams.upload("IDATT2202", "Høst 2023", PDF, SOLUTION)
    files.write(storage_keys.page_image(exam.id, PageKind.EXAM, 1), b"exam page 1")
    files.write(storage_keys.page_image(exam.id, PageKind.EXAM, 2), b"exam page 2")
    files.write(storage_keys.page_image(exam.id, PageKind.SOLUTION, 1), b"solution page 1")

    # Rendered files exist, but the exam does not yet say how many pages it has.
    with pytest.raises(NotFound):
        exams.page_image(exam.id, PageKind.EXAM, 1)

    set_exam(uow_factory, exam.with_pages(2, 1).mark_needs_review())
    assert exams.page_image(exam.id, PageKind.EXAM, 2) == b"exam page 2"
    assert exams.page_image(exam.id, PageKind.SOLUTION, 1) == b"solution page 1"
    for kind, number in [(PageKind.EXAM, 0), (PageKind.EXAM, 3), (PageKind.SOLUTION, 2)]:
        with pytest.raises(NotFound):
            exams.page_image(exam.id, kind, number)


def test_solution_pages_of_an_exam_without_solution_are_not_found(exams, uow_factory):
    exam = exams.upload("IDATT2202", "Høst 2023", PDF)
    set_exam(uow_factory, exam.with_pages(2).mark_needs_review())
    with pytest.raises(NotFound):
        exams.page_image(exam.id, PageKind.SOLUTION, 1)
