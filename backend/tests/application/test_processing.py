from uuid import uuid4

import pytest

from levet.adapters.jobs.worker import InMemoryProgress
from levet.application import storage_keys
from levet.application.errors import InvalidPdf
from levet.application.ports import ExtractedSection, Progress, RenderedRegion
from levet.application.processing import INTERRUPTED_MESSAGE, ExamProcessor
from levet.application.storage_keys import PageKind
from levet.domain import Exam, ExamStatus, Language, Region, Subject, Task, Topic

EXAM_PDF = b"%PDF exam"
SOLUTION_PDF = b"%PDF solution"

BLANK = Region(page=1, top=0.9, bottom=0.95)

NB = "Hva er sannsynligheten for at kula ikke er defekt? Regn ut og velg ett alternativ."
EN = "What is the probability that the ball is not defective? Compute the value and answer."


def band(page, top, bottom):
    return Region(page=page, top=top, bottom=bottom)


def section(number, *regions, parent=None, title=None, points=None, text=""):
    return ExtractedSection(
        number=number,
        regions=regions or (band(1, 0.1, 0.2),),
        text=text,
        parent_number=parent,
        title=title,
        points=points,
    )


class FakeRenderer:
    """Renders ``pages[pdf]`` pages for each known document.

    ``failures`` holds exceptions to raise, one per call to ``render_pages``,
    before rendering starts working. ``drop_last_page`` simulates a renderer
    that silently produces fewer pages than it counted. A region is rendered
    as a recognisable byte string, trimmed a little; ``BLANK`` renders as nothing.
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

    def render_regions(self, pdf, regions):
        return [None if region == BLANK else self._region(pdf, region) for region in regions]

    @staticmethod
    def _region(pdf, region):
        trimmed = Region(
            page=region.page, top=round(region.top + 0.01, 4), bottom=round(region.bottom - 0.01, 4)
        )
        png = pdf + b" p%d %.2f-%.2f" % (region.page, region.top, region.bottom)
        return RenderedRegion(region=trimmed, png=png)


class FakeExtractor:
    def __init__(self, sections=None):
        self.sections = sections or {}

    def extract(self, pdf):
        return list(self.sections.get(pdf, [section("1")]))


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


@pytest.fixture
def process(uow_factory, files, progress):
    """Runs the processor on an exam with the given fakes; returns the processor."""

    def run(exam, renderer=None, sections=None, language=Language.BOKMAL):
        renderer = renderer or FakeRenderer({EXAM_PDF: 2, SOLUTION_PDF: 1})
        processor = ExamProcessor(
            uow_factory, files, renderer, FakeExtractor(sections), progress, language
        )
        processor.process(exam.id)
        return processor

    return run


def load(uow_factory, exam):
    with uow_factory() as uow:
        return uow.exams.get(exam.id)


def tasks_of(uow_factory, exam):
    with uow_factory() as uow:
        return uow.tasks.list_by_exam(exam.id)


def topics_of(uow_factory):
    with uow_factory() as uow:
        return uow.topics.list_by_subject("IDATT2202")


# --- pages -------------------------------------------------------------------


def test_every_page_is_rendered_and_the_exam_moves_to_needs_review(
    uow_factory, files, new_exam, process
):
    exam = new_exam()

    process(exam, FakeRenderer({EXAM_PDF: 3}))

    processed = load(uow_factory, exam)
    assert processed.status is ExamStatus.NEEDS_REVIEW
    assert processed.page_count == 3
    assert processed.solution_page_count is None
    for number in (1, 2, 3):
        key = storage_keys.page_image(exam.id, PageKind.EXAM, number)
        assert files.read(key) == EXAM_PDF + b" page %d" % number
    assert not files.exists(storage_keys.page_image(exam.id, PageKind.EXAM, 4))


def test_solution_pages_are_rendered_alongside_the_exam(uow_factory, files, new_exam, process):
    exam = new_exam(solution=True)

    process(exam, FakeRenderer({EXAM_PDF: 2, SOLUTION_PDF: 3}))

    processed = load(uow_factory, exam)
    assert (processed.page_count, processed.solution_page_count) == (2, 3)
    assert files.read(storage_keys.page_image(exam.id, PageKind.SOLUTION, 3)) == (
        SOLUTION_PDF + b" page 3"
    )


def test_progress_covers_rendering_then_extraction_and_is_cleared_when_done(
    progress, new_exam, process
):
    exam = new_exam(solution=True)
    sections = {EXAM_PDF: [section("1"), section("2")]}

    process(exam, FakeRenderer({EXAM_PDF: 2, SOLUTION_PDF: 1}), sections)

    assert progress.reports == [
        *(Progress("rendering", done, 3) for done in (0, 1, 2, 3)),
        Progress("extracting", 0, 1),
        Progress("extracting", 1, 2),
        Progress("extracting", 2, 2),
    ]
    assert progress.get(exam.id) is None


# --- tasks -------------------------------------------------------------------


def test_extracted_sections_become_tasks_in_document_order(uow_factory, new_exam, process):
    exam = new_exam()
    sections = {
        EXAM_PDF: [
            section("1", band(1, 0.1, 0.3), title="Normalfordeling", points=4, text="Innledning"),
            section("1a", band(1, 0.3, 0.6), parent="1", points=2, text="a) Finn …"),
            section("1b", band(1, 0.6, 0.9), band(2, 0.1, 0.4), parent="1", points=2),
            section("2", band(2, 0.4, 0.8), title="Hypotesetest"),
        ]
    }

    process(exam, sections=sections)

    tasks = tasks_of(uow_factory, exam)
    assert [(t.number, t.position, t.title, t.points) for t in tasks] == [
        ("1", 0, "Normalfordeling", 4),
        ("1a", 1, None, 2),
        ("1b", 2, None, 2),
        ("2", 3, "Hypotesetest", None),
    ]
    assert tasks[0].text == "Innledning"
    assert [t.parent_id for t in tasks] == [None, tasks[0].id, tasks[0].id, None]
    assert all(t.exam_id == exam.id for t in tasks)
    assert tasks[2].source_pages == (1, 2)


def test_each_task_region_is_stored_as_an_image_of_what_was_rendered(
    uow_factory, files, new_exam, process
):
    exam = new_exam()
    sections = {EXAM_PDF: [section("1", band(1, 0.60, 0.90), band(2, 0.10, 0.40))]}

    process(exam, sections=sections)

    (task,) = tasks_of(uow_factory, exam)
    # The regions kept are the trimmed ones the images show, one image each.
    assert task.regions == (band(1, 0.61, 0.89), band(2, 0.11, 0.39))
    assert [files.read(key) for key in task.image_keys] == [
        EXAM_PDF + b" p1 0.60-0.90",
        EXAM_PDF + b" p2 0.10-0.40",
    ]
    prefix = storage_keys.task_images(exam.id) + "/"
    assert all(key.startswith(prefix) and key.endswith(".png") for key in task.image_keys)


def test_blank_regions_are_left_out(uow_factory, new_exam, process):
    exam = new_exam()
    sections = {EXAM_PDF: [section("1", band(1, 0.2, 0.5), BLANK)]}

    process(exam, sections=sections)

    (task,) = tasks_of(uow_factory, exam)
    assert len(task.regions) == len(task.image_keys) == 1


def test_only_the_preferred_language_version_becomes_tasks(uow_factory, new_exam, process):
    sections = {
        EXAM_PDF: [
            section("1", band(1, 0.1, 0.5), text=NB),
            section("2", band(1, 0.5, 0.9), text=NB),
            section("1", band(2, 0.1, 0.5), text=EN),
            section("2", band(2, 0.5, 0.9), text=EN),
        ]
    }

    norwegian = new_exam(label="A")
    process(norwegian, sections=sections)
    english = new_exam(label="B")
    process(english, sections=sections, language=Language.ENGLISH)

    assert [(t.number, t.text) for t in tasks_of(uow_factory, norwegian)] == [("1", NB), ("2", NB)]
    assert [(t.number, t.text) for t in tasks_of(uow_factory, english)] == [("1", EN), ("2", EN)]


# --- solutions ---------------------------------------------------------------


def test_solutions_are_matched_by_number_and_stored_as_images(
    uow_factory, files, new_exam, process
):
    exam = new_exam(solution=True)
    sections = {
        EXAM_PDF: [section("1"), section("1a", parent="1"), section("2")],
        SOLUTION_PDF: [
            section("1", band(1, 0.1, 0.2), text="Løsning 1"),
            section("1a", band(1, 0.2, 0.5), parent="1", text="Svar a"),
            section("3", band(1, 0.5, 0.9), text="Hører ikke til noen oppgave"),
        ],
    }

    process(exam, sections=sections)

    intro, part, unsolved = tasks_of(uow_factory, exam)
    assert part.solution_text == "Svar a"
    assert part.solution_regions == (band(1, 0.21, 0.49),)
    assert [files.read(key) for key in part.solution_image_keys] == [
        SOLUTION_PDF + b" p1 0.20-0.50"
    ]
    assert intro.solution_text == "Løsning 1"
    assert not unsolved.has_solution


def test_an_exam_without_a_solution_pdf_has_no_solutions(uow_factory, new_exam, process):
    exam = new_exam()
    process(exam, sections={EXAM_PDF: [section("1")]})
    assert not tasks_of(uow_factory, exam)[0].has_solution


# --- topics ------------------------------------------------------------------


def test_task_titles_become_topics_on_the_tasks_not_on_their_parts(uow_factory, new_exam, process):
    exam = new_exam()
    sections = {
        EXAM_PDF: [
            section("1", title="Normalfordeling"),
            section("1a", parent="1"),
            section("2", title="Hypotesetest"),
            section("3"),
        ]
    }

    process(exam, sections=sections)

    topics = {topic.id: topic.name for topic in topics_of(uow_factory)}
    assert sorted(topics.values()) == ["Hypotesetest", "Normalfordeling"]
    first, part, second, untitled = tasks_of(uow_factory, exam)
    assert [topics[i] for i in first.topic_ids] == ["Normalfordeling"]
    assert [topics[i] for i in second.topic_ids] == ["Hypotesetest"]
    assert part.topic_ids == frozenset()  # takes its parent's
    assert untitled.topic_ids == frozenset()


def test_a_second_exam_reuses_the_topics_of_the_first(uow_factory, new_exam, process):
    first = new_exam(label="Høst 2023")
    process(
        first,
        sections={
            EXAM_PDF: [
                section("1", title="Normalfordeling"),
                section("2", title="Enkel lineær regresjon"),
            ]
        },
    )
    second = new_exam(label="Høst 2024")
    process(
        second,
        sections={
            EXAM_PDF: [
                section("1", title="Regresjon"),
                section("2", title="Normalfordelingen"),
                section("3", title="Kaffekopper"),
            ]
        },
    )

    topics = {topic.id: topic.name for topic in topics_of(uow_factory)}
    assert sorted(topics.values()) == ["Enkel lineær regresjon", "Kaffekopper", "Normalfordeling"]
    tagged = [[topics[i] for i in task.topic_ids] for task in tasks_of(uow_factory, second)]
    assert tagged == [["Enkel lineær regresjon"], ["Normalfordeling"], ["Kaffekopper"]]


def test_two_tasks_with_the_same_title_in_one_exam_share_one_topic(uow_factory, new_exam, process):
    exam = new_exam()
    process(
        exam,
        sections={
            EXAM_PDF: [section("1", title="Hypotesetest"), section("2", title="Hypotesetesting")]
        },
    )
    assert [topic.name for topic in topics_of(uow_factory)] == ["Hypotesetest"]


# --- failures ----------------------------------------------------------------


def test_a_failed_run_is_retried_once_and_can_then_succeed(uow_factory, new_exam, process):
    exam = new_exam()
    renderer = FakeRenderer({EXAM_PDF: 2}, failures=[OSError("disk hiccup")])

    process(exam, renderer)

    assert renderer.render_calls == 2
    processed = load(uow_factory, exam)
    assert processed.status is ExamStatus.NEEDS_REVIEW
    assert processed.page_count == 2
    assert len(tasks_of(uow_factory, exam)) == 1


def test_after_a_second_failure_the_exam_is_failed_with_the_error_visible(
    uow_factory, progress, new_exam, process
):
    exam = new_exam()
    renderer = FakeRenderer({EXAM_PDF: 2}, failures=[OSError("disk hiccup"), OSError("disk full")])

    process(exam, renderer)

    assert renderer.render_calls == 2
    failed = load(uow_factory, exam)
    assert failed.status is ExamStatus.FAILED
    assert failed.error == "OSError: disk full"
    assert failed.page_count is None
    assert tasks_of(uow_factory, exam) == []
    assert progress.get(exam.id) is None


def test_an_unreadable_pdf_fails_at_once_because_retrying_cannot_help(
    uow_factory, new_exam, process
):
    exam = new_exam()
    renderer = FakeRenderer({})  # knows no documents: every PDF is invalid

    process(exam, renderer)

    assert renderer.render_calls == 0
    failed = load(uow_factory, exam)
    assert failed.status is ExamStatus.FAILED
    assert failed.error == "Exam PDF: the file could not be read as a PDF"


def test_an_unreadable_solution_fails_the_exam_and_says_which_file(uow_factory, new_exam, process):
    exam = new_exam(solution=True)

    process(exam, FakeRenderer({EXAM_PDF: 2}))

    failed = load(uow_factory, exam)
    assert failed.status is ExamStatus.FAILED
    assert failed.error.startswith("Solution PDF:")


def test_pages_are_never_silently_dropped(uow_factory, new_exam, process):
    exam = new_exam()

    process(exam, FakeRenderer({EXAM_PDF: 5}, drop_last_page=True))

    failed = load(uow_factory, exam)
    assert failed.status is ExamStatus.FAILED
    assert "rendered 4 of 5 pages" in failed.error


def test_a_missing_stored_pdf_fails_the_exam(uow_factory, now, process):
    exam = Exam(
        subject_code="IDATT2202", label="Høst 2023", pdf_key="exams/gone/exam.pdf", uploaded_at=now
    )
    with uow_factory() as uow:
        uow.subjects.save(Subject("IDATT2202", "Operativsystemer"))
        uow.exams.save(exam)
        uow.commit()

    process(exam, FakeRenderer({}))

    failed = load(uow_factory, exam)
    assert failed.status is ExamStatus.FAILED
    assert failed.error.startswith("FileNotFoundError")


def test_very_long_errors_are_shortened(uow_factory, new_exam, process):
    exam = new_exam()

    process(exam, FakeRenderer({EXAM_PDF: 1}, failures=[OSError("x" * 5000)] * 2))

    assert len(load(uow_factory, exam).error) == 500


def test_processing_again_replaces_the_tasks_images_and_unused_topics(
    uow_factory, files, new_exam, process
):
    exam = new_exam()
    process(exam, sections={EXAM_PDF: [section("1", title="Gammelt tema"), section("2")]})
    old_tasks = tasks_of(uow_factory, exam)
    old_image = old_tasks[0].image_keys[0]

    with uow_factory() as uow:  # as the retry button does after a failure
        uow.exams.save(replace_status(load(uow_factory, exam), ExamStatus.PROCESSING))
        uow.commit()
    process(exam, sections={EXAM_PDF: [section("1", title="Nytt tema")]})

    new_tasks = tasks_of(uow_factory, exam)
    assert [t.number for t in new_tasks] == ["1"]
    assert {t.id for t in new_tasks}.isdisjoint({t.id for t in old_tasks})
    assert not files.exists(old_image)
    assert [topic.name for topic in topics_of(uow_factory)] == ["Nytt tema"]


def replace_status(exam, status):
    return Exam(
        id=exam.id,
        subject_code=exam.subject_code,
        label=exam.label,
        pdf_key=exam.pdf_key,
        solution_pdf_key=exam.solution_pdf_key,
        uploaded_at=exam.uploaded_at,
        status=status,
    )


# --- things that must be left alone ------------------------------------------


def test_an_exam_that_is_not_processing_is_left_untouched(uow_factory, new_exam, process):
    exam = new_exam(status=ExamStatus.NEEDS_REVIEW, page_count=7)
    renderer = FakeRenderer({EXAM_PDF: 2})

    process(exam, renderer)

    assert load(uow_factory, exam) == exam
    assert renderer.render_calls == 0
    assert tasks_of(uow_factory, exam) == []


def test_processing_an_unknown_exam_does_nothing(uow_factory, files, progress):
    processor = ExamProcessor(uow_factory, files, FakeRenderer({}), FakeExtractor(), progress)
    processor.process(uuid4())


def test_tasks_and_topics_of_other_exams_survive(uow_factory, new_exam, process):
    other = new_exam(label="Annen eksamen")
    topic = Topic(subject_code="IDATT2202", name="Deadlock")
    with uow_factory() as uow:
        uow.topics.save(topic)
        uow.tasks.save(Task(exam_id=other.id, number="1", topic_ids={topic.id}))
        uow.commit()

    process(new_exam(), sections={EXAM_PDF: [section("1", title="Paging")]})

    assert [t.number for t in tasks_of(uow_factory, other)] == ["1"]
    assert sorted(t.name for t in topics_of(uow_factory)) == ["Deadlock", "Paging"]


# --- recovery after a restart ------------------------------------------------


def test_exams_left_processing_by_a_previous_run_are_failed_so_they_can_be_retried(
    uow_factory, files, progress, new_exam
):
    stuck = new_exam(label="A")
    done = new_exam(label="B", status=ExamStatus.NEEDS_REVIEW, page_count=3)
    processor = ExamProcessor(uow_factory, files, FakeRenderer({}), FakeExtractor(), progress)

    assert processor.recover_interrupted() == 1

    recovered = load(uow_factory, stuck)
    assert recovered.status is ExamStatus.FAILED
    assert recovered.error == INTERRUPTED_MESSAGE
    assert load(uow_factory, done) == done
    assert processor.recover_interrupted() == 0
