import dataclasses
from datetime import UTC, date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from levet.domain import (
    Attempt,
    Exam,
    ExamStatus,
    Grade,
    InvalidTransition,
    Region,
    ReviewPhase,
    ReviewState,
    Subject,
    Task,
    Topic,
)

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


# --- Subject -----------------------------------------------------------------


def test_subject_code_is_normalised_so_it_works_as_a_natural_key():
    assert Subject(" idatt2202 ", "Operativsystemer").code == "IDATT2202"
    assert Subject("idatt2202", "Operativsystemer") == Subject("IDATT2202", "Operativsystemer")


@pytest.mark.parametrize(("code", "name"), [("", "Operativsystemer"), ("IDATT2202", "  ")])
def test_subject_requires_code_and_name(code, name):
    with pytest.raises(ValueError):
        Subject(code, name)


def test_days_until_exam():
    subject = Subject("IDATT2202", "Operativsystemer", exam_date=date(2026, 12, 1))
    assert subject.days_until_exam(date(2026, 11, 11)) == 20
    assert subject.days_until_exam(date(2026, 12, 3)) == -2
    assert Subject("IDATT2202", "Operativsystemer").days_until_exam(date(2026, 11, 11)) is None


# --- Topic -------------------------------------------------------------------


def test_topic_belongs_to_a_normalised_subject_and_gets_its_own_id():
    a = Topic(subject_code="idatt2202", name=" Scheduling ")
    b = Topic(subject_code="IDATT2202", name="Scheduling")
    assert a.subject_code == "IDATT2202"
    assert a.name == "Scheduling"
    assert a.id != b.id


def test_topic_requires_a_name():
    with pytest.raises(ValueError):
        Topic(subject_code="IDATT2202", name="")


# --- Exam --------------------------------------------------------------------


def new_exam(**overrides):
    fields = {
        "subject_code": "IDATT2202",
        "label": "Høst 2023",
        "pdf_key": "exams/h23.pdf",
        "uploaded_at": NOW,
    }
    return Exam(**(fields | overrides))


def test_new_exam_starts_processing_without_a_solution():
    exam = new_exam()
    assert exam.status is ExamStatus.PROCESSING
    assert exam.solution_pdf_key is None
    assert exam.error is None


def test_exam_happy_path_is_processing_then_needs_review_then_ready():
    exam = new_exam()
    reviewed = exam.mark_needs_review()
    ready = reviewed.approve()
    assert (reviewed.status, ready.status) == (ExamStatus.NEEDS_REVIEW, ExamStatus.READY)
    assert ready.id == exam.id
    assert exam.status is ExamStatus.PROCESSING  # transitions return new objects


def test_failed_exam_keeps_its_error_until_retried():
    failed = new_exam().fail("page 4: extraction returned invalid JSON")
    assert failed.status is ExamStatus.FAILED
    assert failed.error == "page 4: extraction returned invalid JSON"

    retried = failed.retry()
    assert retried.status is ExamStatus.PROCESSING
    assert retried.error is None


def test_failing_requires_an_error_message():
    with pytest.raises(ValueError):
        new_exam().fail("   ")


@pytest.mark.parametrize(
    "transition",
    [
        lambda e: e.approve(),  # processing → ready skips review
        lambda e: e.retry(),  # nothing to retry
        lambda e: e.mark_needs_review().mark_needs_review(),
        lambda e: e.mark_needs_review().fail("too late"),
        lambda e: e.mark_needs_review().approve().approve(),
        lambda e: e.mark_needs_review().approve().fail("too late"),
        lambda e: e.fail("boom").approve(),
        lambda e: e.fail("boom").mark_needs_review(),
    ],
)
def test_invalid_exam_transitions_are_rejected(transition):
    with pytest.raises(InvalidTransition):
        transition(new_exam())


def test_error_and_failed_status_must_go_together():
    with pytest.raises(ValueError):
        new_exam(status=ExamStatus.FAILED)
    with pytest.raises(ValueError):
        new_exam(error="boom")


def test_exam_requires_label_pdf_and_an_aware_upload_time():
    with pytest.raises(ValueError):
        new_exam(label=" ")
    with pytest.raises(ValueError):
        new_exam(pdf_key="")
    with pytest.raises(ValueError):
        new_exam(uploaded_at=datetime(2026, 11, 11))


def test_page_counts_are_unknown_until_pages_are_rendered():
    exam = new_exam(solution_pdf_key="exams/h23-lf.pdf")
    assert (exam.page_count, exam.solution_page_count) == (None, None)

    rendered = exam.with_pages(10, 4)
    assert (rendered.page_count, rendered.solution_page_count) == (10, 4)


def test_retrying_forgets_the_page_counts_because_rendering_starts_over():
    failed = new_exam().with_pages(10).fail("boom")
    assert failed.retry().page_count is None


def test_impossible_page_counts_are_rejected():
    with pytest.raises(ValueError):
        new_exam().with_pages(0)
    with pytest.raises(ValueError):
        new_exam().with_pages(10, 4)  # no solution PDF
    with pytest.raises(ValueError):
        new_exam(solution_pdf_key="exams/h23-lf.pdf").with_pages(10, 0)


# --- Region ------------------------------------------------------------------


def test_region_covers_the_full_page_width_by_default():
    region = Region(page=2, top=0.25, bottom=0.75)
    assert (region.left, region.right) == (0.0, 1.0)
    assert region.height == pytest.approx(0.5)


@pytest.mark.parametrize(
    "fields",
    [
        {"page": 0, "top": 0.1, "bottom": 0.2},
        {"page": 1, "top": 0.5, "bottom": 0.5},
        {"page": 1, "top": 0.6, "bottom": 0.4},
        {"page": 1, "top": -0.1, "bottom": 0.4},
        {"page": 1, "top": 0.1, "bottom": 1.1},
        {"page": 1, "top": 0.1, "bottom": 0.2, "left": 0.9, "right": 0.1},
    ],
)
def test_impossible_regions_are_rejected(fields):
    with pytest.raises(ValueError):
        Region(**fields)


def test_region_is_split_at_a_fraction_of_its_height():
    upper, lower = Region(page=3, top=0.2, bottom=0.6, left=0.1, right=0.9).split_at(0.25)
    assert (upper.top, upper.bottom) == (0.2, pytest.approx(0.3))
    assert (lower.top, lower.bottom) == (pytest.approx(0.3), 0.6)
    assert upper.bottom == lower.top
    for part in (upper, lower):
        assert (part.page, part.left, part.right) == (3, 0.1, 0.9)


@pytest.mark.parametrize("fraction", [0.0, 1.0, -0.2, 1.5])
def test_region_cannot_be_split_at_or_beyond_its_edges(fraction):
    with pytest.raises(ValueError):
        Region(page=1, top=0.2, bottom=0.6).split_at(fraction)


# --- Task --------------------------------------------------------------------


def new_task(**overrides):
    fields = {"exam_id": uuid4(), "number": "3b"}
    return Task(**(fields | overrides))


def test_task_defaults_describe_a_bare_top_level_task():
    task = new_task()
    assert task.parent_id is None
    assert task.title is None
    assert task.text == ""
    assert task.position == 0
    assert task.points is None
    assert task.topic_ids == frozenset()
    assert task.regions == ()
    assert task.image_keys == ()
    assert task.source_pages == ()
    assert not task.has_solution


def test_sub_task_points_at_its_parent():
    parent = new_task(number="3", title="Normalfordeling")
    child = new_task(exam_id=parent.exam_id, number="3a", parent_id=parent.id)
    assert child.parent_id == parent.id


def test_task_cannot_be_its_own_parent():
    task_id = uuid4()
    with pytest.raises(ValueError):
        new_task(id=task_id, parent_id=task_id)


def test_task_accepts_up_to_three_topics_and_no_more():
    three = {uuid4(), uuid4(), uuid4()}
    assert new_task(topic_ids=three).topic_ids == frozenset(three)
    with pytest.raises(ValueError):
        new_task(topic_ids=three | {uuid4()})


def test_task_collections_are_stored_immutably():
    topic = uuid4()
    regions = [Region(page=4, top=0.8, bottom=0.95), Region(page=5, top=0.05, bottom=0.3)]
    task = new_task(topic_ids=[topic, topic], regions=regions, image_keys=["a.png", "b.png"])
    assert task.topic_ids == frozenset({topic})
    assert task.regions == tuple(regions)
    assert task.image_keys == ("a.png", "b.png")


def test_source_pages_follow_from_the_regions():
    task = new_task(
        regions=[
            Region(page=5, top=0.05, bottom=0.3),
            Region(page=4, top=0.8, bottom=0.95),
            Region(page=4, top=0.1, bottom=0.2),
        ]
    )
    assert task.source_pages == (4, 5)


def test_task_has_a_solution_when_it_has_solution_regions_or_text():
    assert new_task(solution_regions=[Region(page=1, top=0.1, bottom=0.2)]).has_solution
    assert new_task(solution_text="x = 2").has_solution


def test_blank_title_means_no_title():
    assert new_task(title="   ").title is None
    assert new_task(title=" Normalfordeling ").title == "Normalfordeling"


@pytest.mark.parametrize(
    "overrides",
    [{"number": " "}, {"points": -1}, {"points": float("nan")}, {"position": -1}],
)
def test_invalid_tasks_are_rejected(overrides):
    with pytest.raises(ValueError):
        new_task(**overrides)


def test_retagging_a_task_keeps_its_identity():
    task = new_task()
    topic = uuid4()
    retagged = dataclasses.replace(task, topic_ids={topic})
    assert retagged.id == task.id
    assert retagged.topic_ids == frozenset({topic})


# --- Attempt -----------------------------------------------------------------


def test_attempt_score_follows_its_grade():
    attempt = Attempt(task_id=uuid4(), attempted_at=NOW, grade=Grade.HARD)
    assert attempt.score == Grade.HARD.score


def test_attempt_is_immutable():
    attempt = Attempt(task_id=uuid4(), attempted_at=NOW, grade=Grade.GOOD)
    with pytest.raises(dataclasses.FrozenInstanceError):
        attempt.grade = Grade.EASY


def test_attempt_optional_fields_default_to_absent():
    attempt = Attempt(task_id=uuid4(), attempted_at=NOW, grade=Grade.GOOD)
    assert (attempt.time_spent, attempt.answer, attempt.note) == (None, None, None)


def test_attempt_timestamp_is_stored_in_utc():
    oslo = timezone(timedelta(hours=1))
    attempt = Attempt(
        task_id=uuid4(), attempted_at=datetime(2026, 11, 11, 13, 0, tzinfo=oslo), grade=Grade.GOOD
    )
    assert attempt.attempted_at == NOW
    assert attempt.attempted_at.tzinfo is UTC


def test_attempt_rejects_naive_timestamp_negative_time_and_unknown_grade():
    with pytest.raises(ValueError):
        Attempt(task_id=uuid4(), attempted_at=datetime(2026, 11, 11), grade=Grade.GOOD)
    with pytest.raises(ValueError):
        Attempt(
            task_id=uuid4(), attempted_at=NOW, grade=Grade.GOOD, time_spent=timedelta(seconds=-1)
        )
    with pytest.raises(ValueError):
        Attempt(task_id=uuid4(), attempted_at=NOW, grade="perfect")


def test_attempt_accepts_a_grade_by_its_stored_value():
    assert Attempt(task_id=uuid4(), attempted_at=NOW, grade="again").grade is Grade.AGAIN


# --- ReviewState -------------------------------------------------------------


def test_new_review_state_is_a_fresh_learning_card():
    state = ReviewState(task_id=uuid4(), due=NOW)
    assert state.phase is ReviewPhase.LEARNING
    assert state.step == 0
    assert (state.stability, state.difficulty, state.last_review) == (None, None, None)


def test_review_state_is_due_from_its_due_time_onwards():
    state = ReviewState(task_id=uuid4(), due=NOW)
    assert not state.is_due(NOW - timedelta(seconds=1))
    assert state.is_due(NOW)
    assert state.is_due(NOW + timedelta(days=1))


def test_review_state_rejects_naive_datetimes():
    with pytest.raises(ValueError):
        ReviewState(task_id=uuid4(), due=datetime(2026, 11, 11))
    with pytest.raises(ValueError):
        ReviewState(task_id=uuid4(), due=NOW, last_review=datetime(2026, 11, 10))
