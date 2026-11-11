from uuid import uuid4

import pytest

from levet.adapters.jobs.worker import InMemoryProgress
from levet.application import storage_keys
from levet.application.errors import InvalidPdf
from levet.application.ports import Progress
from levet.application.processing import INTERRUPTED_MESSAGE, ExamProcessor
from levet.application.storage_keys import PageKind
from levet.domain import Exam, ExamStatus, Subject

EXAM_PDF = b"%PDF exam"
SOLUTION_PDF = b"%PDF solution"


class FakeRenderer:
    """Renders ``pages[pdf]`` pages for each known document.

    ``failures`` holds exceptions to raise, one per call to ``render_pages``,
    before rendering starts working. ``drop_last_page`` simulates a renderer
    that silently produces fewer pages than it counted.
    """

    def __init__(self, pages, failures=(), drop_last_page=False):
        self.pages = pages
        self.failures = list(failures)
        self.drop_last_page = drop_last_page
        self.render_calls = 0

    def count_pages(self, pdf):
        if pdf not in self.pages:
            raise InvalidPdf("the file could not be read as a PDF")
        return self.pages[pdf]

    def render_pages(self, pdf):
        self.render_calls += 1
        if self.failures:
            raise self.failures.pop(0)
        count = self.pages[pdf] - (1 if self.drop_last_page else 0)
        for number in range(1, count + 1):
            yield pdf + b" page %d" % number


class RecordingProgress(InMemoryProgress):
    def __init__(self):
        super().__init__()
        self.reports = []

    def report(self, exam_id, progress):
        self.reports.append(progress)
        super().report(exam_id, progress)


@pytest.fixture
def progress():
    return RecordingProgress()


@pytest.fixture
def new_exam(uow_factory, files, now):
    def create(solution=False, label="Høst 2023", **overrides):
        exam_id = uuid4()
        exam = Exam(
            id=exam_id,
            subject_code="IDATT2202",
            label=label,
            pdf_key=storage_keys.exam_pdf(exam_id),
            solution_pdf_key=storage_keys.solution_pdf(exam_id) if solution else None,
            uploaded_at=now,
            **overrides,
        )
        files.write(exam.pdf_key, EXAM_PDF)
        if solution:
            files.write(exam.solution_pdf_key, SOLUTION_PDF)
        with uow_factory() as uow:
            uow.subjects.save(Subject("IDATT2202", "Operativsystemer"))
            uow.exams.save(exam)
            uow.commit()
        return exam

    return create


def processor(uow_factory, files, progress, renderer):
    return ExamProcessor(uow_factory, files, renderer, progress)


def load(uow_factory, exam):
    with uow_factory() as uow:
        return uow.exams.get(exam.id)


# --- the happy path ----------------------------------------------------------


def test_every_page_is_rendered_and_the_exam_moves_to_needs_review(
    uow_factory, files, progress, new_exam
):
    exam = new_exam()
    renderer = FakeRenderer({EXAM_PDF: 3})

    processor(uow_factory, files, progress, renderer).process(exam.id)

    processed = load(uow_factory, exam)
    assert processed.status is ExamStatus.NEEDS_REVIEW
    assert processed.page_count == 3
    assert processed.solution_page_count is None
    for number in (1, 2, 3):
        key = storage_keys.page_image(exam.id, PageKind.EXAM, number)
        assert files.read(key) == EXAM_PDF + b" page %d" % number
    assert not files.exists(storage_keys.page_image(exam.id, PageKind.EXAM, 4))


def test_solution_pages_are_rendered_alongside_the_exam(uow_factory, files, progress, new_exam):
    exam = new_exam(solution=True)
    renderer = FakeRenderer({EXAM_PDF: 2, SOLUTION_PDF: 3})

    processor(uow_factory, files, progress, renderer).process(exam.id)

    processed = load(uow_factory, exam)
    assert (processed.page_count, processed.solution_page_count) == (2, 3)
    assert files.read(storage_keys.page_image(exam.id, PageKind.SOLUTION, 3)) == (
        SOLUTION_PDF + b" page 3"
    )


def test_progress_counts_pages_across_both_documents_and_is_cleared_when_done(
    uow_factory, files, progress, new_exam
):
    exam = new_exam(solution=True)
    renderer = FakeRenderer({EXAM_PDF: 2, SOLUTION_PDF: 1})

    processor(uow_factory, files, progress, renderer).process(exam.id)

    assert progress.reports == [Progress("rendering", done, 3) for done in (0, 1, 2, 3)]
    assert progress.get(exam.id) is None


# --- failures ----------------------------------------------------------------


def test_a_failed_run_is_retried_once_and_can_then_succeed(uow_factory, files, progress, new_exam):
    exam = new_exam()
    renderer = FakeRenderer({EXAM_PDF: 2}, failures=[OSError("disk hiccup")])

    processor(uow_factory, files, progress, renderer).process(exam.id)

    assert renderer.render_calls == 2
    processed = load(uow_factory, exam)
    assert processed.status is ExamStatus.NEEDS_REVIEW
    assert processed.page_count == 2


def test_after_a_second_failure_the_exam_is_failed_with_the_error_visible(
    uow_factory, files, progress, new_exam
):
    exam = new_exam()
    renderer = FakeRenderer({EXAM_PDF: 2}, failures=[OSError("disk hiccup"), OSError("disk full")])

    processor(uow_factory, files, progress, renderer).process(exam.id)

    assert renderer.render_calls == 2
    failed = load(uow_factory, exam)
    assert failed.status is ExamStatus.FAILED
    assert failed.error == "OSError: disk full"
    assert failed.page_count is None
    assert progress.get(exam.id) is None


def test_an_unreadable_pdf_fails_at_once_because_retrying_cannot_help(
    uow_factory, files, progress, new_exam
):
    exam = new_exam()
    renderer = FakeRenderer({})  # knows no documents: every PDF is invalid

    processor(uow_factory, files, progress, renderer).process(exam.id)

    assert renderer.render_calls == 0
    failed = load(uow_factory, exam)
    assert failed.status is ExamStatus.FAILED
    assert failed.error == "Exam PDF: the file could not be read as a PDF"


def test_an_unreadable_solution_fails_the_exam_and_says_which_file(
    uow_factory, files, progress, new_exam
):
    exam = new_exam(solution=True)
    renderer = FakeRenderer({EXAM_PDF: 2})

    processor(uow_factory, files, progress, renderer).process(exam.id)

    failed = load(uow_factory, exam)
    assert failed.status is ExamStatus.FAILED
    assert failed.error.startswith("Solution PDF:")


def test_pages_are_never_silently_dropped(uow_factory, files, progress, new_exam):
    exam = new_exam()
    renderer = FakeRenderer({EXAM_PDF: 5}, drop_last_page=True)

    processor(uow_factory, files, progress, renderer).process(exam.id)

    failed = load(uow_factory, exam)
    assert failed.status is ExamStatus.FAILED
    assert "rendered 4 of 5 pages" in failed.error


def test_a_missing_stored_pdf_fails_the_exam(uow_factory, files, progress, now):
    exam = Exam(
        subject_code="IDATT2202", label="Høst 2023", pdf_key="exams/gone/exam.pdf", uploaded_at=now
    )
    with uow_factory() as uow:
        uow.subjects.save(Subject("IDATT2202", "Operativsystemer"))
        uow.exams.save(exam)
        uow.commit()

    processor(uow_factory, files, progress, FakeRenderer({})).process(exam.id)

    failed = load(uow_factory, exam)
    assert failed.status is ExamStatus.FAILED
    assert failed.error.startswith("FileNotFoundError")


def test_very_long_errors_are_shortened(uow_factory, files, progress, new_exam):
    exam = new_exam()
    renderer = FakeRenderer({EXAM_PDF: 1}, failures=[OSError("x" * 5000)] * 2)

    processor(uow_factory, files, progress, renderer).process(exam.id)

    assert len(load(uow_factory, exam).error) == 500


# --- things that must be left alone ------------------------------------------


def test_an_exam_that_is_not_processing_is_left_untouched(uow_factory, files, progress, new_exam):
    exam = new_exam(status=ExamStatus.NEEDS_REVIEW, page_count=7)
    renderer = FakeRenderer({EXAM_PDF: 2})

    processor(uow_factory, files, progress, renderer).process(exam.id)

    assert load(uow_factory, exam) == exam
    assert renderer.render_calls == 0


def test_processing_an_unknown_exam_does_nothing(uow_factory, files, progress):
    processor(uow_factory, files, progress, FakeRenderer({})).process(uuid4())


# --- recovery after a restart ------------------------------------------------


def test_exams_left_processing_by_a_previous_run_are_failed_so_they_can_be_retried(
    uow_factory, files, progress, new_exam
):
    stuck = new_exam(label="A")
    done = new_exam(label="B", status=ExamStatus.NEEDS_REVIEW, page_count=3)
    subject = processor(uow_factory, files, progress, FakeRenderer({}))

    assert subject.recover_interrupted() == 1

    recovered = load(uow_factory, stuck)
    assert recovered.status is ExamStatus.FAILED
    assert recovered.error == INTERRUPTED_MESSAGE
    assert load(uow_factory, done) == done
    assert subject.recover_interrupted() == 0
