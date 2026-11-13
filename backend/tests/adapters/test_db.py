from datetime import UTC, date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from levet.adapters.db.migrate import run_migrations
from levet.adapters.db.models import Base
from levet.domain import (
    Attempt,
    Exam,
    ExamStatus,
    Grade,
    Region,
    ReviewPhase,
    ReviewState,
    Subject,
    Task,
    Topic,
)

# --- schema ------------------------------------------------------------------


def test_migrations_create_exactly_the_schema_the_models_describe(engine):
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def test_migrations_can_be_run_again_on_an_up_to_date_database(engine):
    run_migrations(engine)
    assert "subjects" in inspect(engine).get_table_names()


def test_foreign_keys_are_enforced(engine):
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1


# --- helpers -----------------------------------------------------------------


def save_subject(uow_factory, code="IDATT2202"):
    subject = Subject(code, "Operativsystemer", exam_date=date(2026, 12, 1))
    with uow_factory() as uow:
        uow.subjects.save(subject)
        uow.commit()
    return subject


def save_exam(uow_factory, now, **overrides):
    fields = {
        "subject_code": "IDATT2202",
        "label": "Høst 2023",
        "pdf_key": "exams/x/exam.pdf",
        "uploaded_at": now,
    }
    exam = Exam(**(fields | overrides))
    with uow_factory() as uow:
        uow.exams.save(exam)
        uow.commit()
    return exam


@pytest.fixture
def exam(uow_factory, now):
    save_subject(uow_factory)
    return save_exam(uow_factory, now)


# --- unit of work ------------------------------------------------------------


def test_nothing_is_persisted_without_commit(uow_factory):
    with uow_factory() as uow:
        uow.subjects.save(Subject("IDATT2202", "Operativsystemer"))
    with uow_factory() as uow:
        assert uow.subjects.get("IDATT2202") is None


def test_an_exception_inside_the_block_rolls_back(uow_factory):
    with pytest.raises(RuntimeError), uow_factory() as uow:
        uow.subjects.save(Subject("IDATT2202", "Operativsystemer"))
        raise RuntimeError("boom")
    with uow_factory() as uow:
        assert uow.subjects.list_all() == []


# --- subjects ----------------------------------------------------------------


def test_subject_round_trip_and_update(uow_factory):
    subject = save_subject(uow_factory)
    with uow_factory() as uow:
        assert uow.subjects.get("IDATT2202") == subject
        uow.subjects.save(Subject("IDATT2202", "Operating systems", exam_date=None))
        uow.commit()
    with uow_factory() as uow:
        assert uow.subjects.list_all() == [Subject("IDATT2202", "Operating systems")]


def test_subject_with_exams_cannot_be_deleted_at_database_level(uow_factory, exam):
    with pytest.raises(IntegrityError), uow_factory() as uow:
        uow.subjects.delete("IDATT2202")
        uow.commit()


def test_deleting_a_subject_removes_its_topics(uow_factory):
    save_subject(uow_factory)
    topic = Topic(subject_code="IDATT2202", name="Scheduling")
    with uow_factory() as uow:
        uow.topics.save(topic)
        uow.commit()
    with uow_factory() as uow:
        uow.subjects.delete("IDATT2202")
        uow.commit()
    with uow_factory() as uow:
        assert uow.topics.get(topic.id) is None


# --- topics ------------------------------------------------------------------


def test_topic_round_trip_listed_by_subject_in_name_order(uow_factory):
    save_subject(uow_factory)
    save_subject(uow_factory, "TDT4100")
    paging = Topic(subject_code="IDATT2202", name="Paging")
    deadlock = Topic(subject_code="IDATT2202", name="Deadlock")
    other = Topic(subject_code="TDT4100", name="Arv")
    with uow_factory() as uow:
        for topic in (paging, deadlock, other):
            uow.topics.save(topic)
        uow.commit()
    with uow_factory() as uow:
        assert uow.topics.get(paging.id) == paging
        assert uow.topics.list_by_subject("IDATT2202") == [deadlock, paging]


def test_topic_names_are_unique_within_a_subject(uow_factory):
    save_subject(uow_factory)
    with pytest.raises(IntegrityError), uow_factory() as uow:
        uow.topics.save(Topic(subject_code="IDATT2202", name="Paging"))
        uow.topics.save(Topic(subject_code="IDATT2202", name="Paging"))
        uow.commit()


# --- exams -------------------------------------------------------------------


def test_exam_round_trip_keeps_every_field(uow_factory, now):
    save_subject(uow_factory)
    exam = save_exam(uow_factory, now, solution_pdf_key="exams/x/solution.pdf")
    failed = exam.fail("page 4: boom")
    with uow_factory() as uow:
        assert uow.exams.get(exam.id) == exam
        uow.exams.save(failed)
        uow.commit()
    with uow_factory() as uow:
        assert uow.exams.get(exam.id) == failed

    rendered = failed.retry().with_pages(10, 4).mark_needs_review()
    with uow_factory() as uow:
        uow.exams.save(rendered)
        uow.commit()
    with uow_factory() as uow:
        assert uow.exams.get(exam.id) == rendered


def test_exam_timestamps_come_back_timezone_aware_in_utc(uow_factory):
    save_subject(uow_factory)
    oslo = timezone(timedelta(hours=1))
    exam = save_exam(uow_factory, datetime(2026, 11, 11, 13, 0, tzinfo=oslo))
    with uow_factory() as uow:
        loaded = uow.exams.get(exam.id)
    assert loaded.uploaded_at == datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
    assert loaded.uploaded_at.utcoffset() == timedelta(0)


def test_exams_are_listed_newest_first_and_can_be_filtered(uow_factory, now):
    save_subject(uow_factory)
    save_subject(uow_factory, "TDT4100")
    old = save_exam(uow_factory, now - timedelta(days=2), label="Høst 2022")
    new = save_exam(uow_factory, now, label="Høst 2023")
    other = save_exam(
        uow_factory, now - timedelta(days=1), subject_code="TDT4100", label="Vår 2024"
    )
    with uow_factory() as uow:
        assert uow.exams.list_all() == [new, other, old]
        assert uow.exams.list_all("IDATT2202") == [new, old]
        assert uow.exams.find_by_label("IDATT2202", "Høst 2022") == old
        assert uow.exams.find_by_label("TDT4100", "Høst 2022") is None


def test_exams_can_be_listed_by_status(uow_factory, now):
    save_subject(uow_factory)
    processing = save_exam(uow_factory, now, label="A")
    save_exam(uow_factory, now, label="B", status=ExamStatus.NEEDS_REVIEW)
    with uow_factory() as uow:
        assert uow.exams.list_by_status(ExamStatus.PROCESSING) == [processing]


def test_exam_labels_are_unique_within_a_subject(uow_factory, now, exam):
    with pytest.raises(IntegrityError):
        save_exam(uow_factory, now)


# --- tasks -------------------------------------------------------------------


def test_task_round_trip_keeps_every_field(uow_factory, exam):
    topics = [Topic(subject_code="IDATT2202", name=name) for name in ("Paging", "Deadlock")]
    parent = Task(exam_id=exam.id, number="3", title="Minnehåndtering", position=4)
    child = Task(
        exam_id=exam.id,
        number="3b",
        position=6,
        text="Vis at x^2 >= 0.",
        parent_id=parent.id,
        points=7.5,
        topic_ids={t.id for t in topics},
        regions=(
            Region(page=3, top=0.8, bottom=0.95, left=0.05, right=0.9),
            Region(page=4, top=0.04, bottom=0.31, left=0.05, right=0.9),
        ),
        image_keys=("exams/x/task-images/a.png", "exams/x/task-images/b.png"),
        solution_text="Fordi …",
        solution_regions=(Region(page=2, top=0.1, bottom=0.2),),
        solution_image_keys=("exams/x/task-images/c.png",),
    )
    with uow_factory() as uow:
        for topic in topics:
            uow.topics.save(topic)
        # Child first: the order within a transaction must not matter.
        uow.tasks.save(child)
        uow.tasks.save(parent)
        uow.commit()
    with uow_factory() as uow:
        assert uow.tasks.get(child.id) == child
        assert uow.tasks.get(parent.id) == parent
        assert uow.tasks.list_by_exam(exam.id) == [parent, child]


def test_tasks_are_listed_in_document_order_not_by_label(uow_factory, exam):
    tenth = Task(exam_id=exam.id, number="10", position=1)
    second = Task(exam_id=exam.id, number="2", position=0)
    with uow_factory() as uow:
        uow.tasks.save(tenth)
        uow.tasks.save(second)
        uow.commit()
    with uow_factory() as uow:
        assert [task.number for task in uow.tasks.list_by_exam(exam.id)] == ["2", "10"]


def test_all_tasks_of_an_exam_can_be_deleted_at_once(uow_factory, exam, now):
    other = save_exam(uow_factory, now, label="Vår 2024")
    parent = Task(exam_id=exam.id, number="1")
    with uow_factory() as uow:
        uow.tasks.save(parent)
        uow.tasks.save(Task(exam_id=exam.id, number="1a", parent_id=parent.id, position=1))
        uow.tasks.save(Task(exam_id=other.id, number="1"))
        uow.commit()
    with uow_factory() as uow:
        uow.tasks.delete_by_exam(exam.id)
        uow.commit()
    with uow_factory() as uow:
        assert uow.tasks.list_by_exam(exam.id) == []
        assert len(uow.tasks.list_by_exam(other.id)) == 1


def test_topics_that_no_task_uses_can_be_cleared_out(uow_factory, exam):
    used = Topic(subject_code="IDATT2202", name="Paging")
    unused = Topic(subject_code="IDATT2202", name="Deadlock")
    with uow_factory() as uow:
        uow.topics.save(used)
        uow.topics.save(unused)
        uow.tasks.save(Task(exam_id=exam.id, number="1", topic_ids={used.id}))
        uow.topics.delete_unused("IDATT2202")
        uow.commit()
    with uow_factory() as uow:
        assert uow.topics.list_by_subject("IDATT2202") == [used]


def test_saving_a_task_again_replaces_its_topics(uow_factory, exam):
    old, new = (Topic(subject_code="IDATT2202", name=name) for name in ("Paging", "Deadlock"))
    task = Task(exam_id=exam.id, number="1", topic_ids={old.id})
    retagged = Task(id=task.id, exam_id=exam.id, number="1", topic_ids={new.id})
    with uow_factory() as uow:
        uow.topics.save(old)
        uow.topics.save(new)
        uow.tasks.save(task)
        uow.commit()
    with uow_factory() as uow:
        uow.tasks.save(retagged)
        uow.commit()
    with uow_factory() as uow:
        assert uow.tasks.get(task.id).topic_ids == frozenset({new.id})


def test_task_cannot_reference_a_missing_topic_or_parent(uow_factory, exam):
    with pytest.raises(IntegrityError), uow_factory() as uow:
        uow.tasks.save(Task(exam_id=exam.id, number="1", text="…", topic_ids={uuid4()}))
        uow.commit()
    with pytest.raises(IntegrityError), uow_factory() as uow:
        uow.tasks.save(Task(exam_id=exam.id, number="1a", text="…", parent_id=uuid4()))
        uow.commit()


def test_deleting_a_task_removes_its_topic_links_attempts_and_review_state(uow_factory, exam, now):
    topic = Topic(subject_code="IDATT2202", name="Paging")
    task = Task(exam_id=exam.id, number="1", text="…", topic_ids={topic.id})
    with uow_factory() as uow:
        uow.topics.save(topic)
        uow.tasks.save(task)
        uow.commit()
    with uow_factory() as uow:
        uow.attempts.add(Attempt(task_id=task.id, attempted_at=now, grade=Grade.GOOD))
        uow.review_states.save(ReviewState(task_id=task.id, due=now))
        uow.commit()
    with uow_factory() as uow:
        uow.tasks.delete(task.id)
        uow.commit()
    with uow_factory() as uow:
        assert uow.tasks.get(task.id) is None
        assert uow.attempts.list_by_task(task.id) == []
        assert uow.review_states.get(task.id) is None
        assert uow.topics.get(topic.id) == topic


def test_tasks_can_be_listed_for_every_exam_with_a_status(uow_factory, exam, now):
    ready = save_exam(uow_factory, now + timedelta(hours=1), label="Klar", status=ExamStatus.READY)
    older = save_exam(uow_factory, now - timedelta(hours=1), label="Eldre", status=ExamStatus.READY)
    with uow_factory() as uow:
        uow.tasks.save(Task(exam_id=exam.id, number="under behandling"))
        uow.tasks.save(Task(exam_id=ready.id, number="2", position=1))
        uow.tasks.save(Task(exam_id=ready.id, number="1", position=0))
        uow.tasks.save(Task(exam_id=older.id, number="1"))
        uow.commit()
    with uow_factory() as uow:
        listed = uow.tasks.list_by_exam_status(ExamStatus.READY)
    # Oldest exam first, each exam's tasks in document order.
    assert [(t.exam_id, t.number) for t in listed] == [
        (older.id, "1"),
        (ready.id, "1"),
        (ready.id, "2"),
    ]


def test_tasks_can_be_listed_by_topic(uow_factory, exam):
    wanted = Topic(subject_code="IDATT2202", name="Paging")
    other = Topic(subject_code="IDATT2202", name="Deadlock")
    with uow_factory() as uow:
        uow.topics.save(wanted)
        uow.topics.save(other)
        uow.tasks.save(Task(exam_id=exam.id, number="1", topic_ids={wanted.id}))
        uow.tasks.save(Task(exam_id=exam.id, number="2", position=1, topic_ids={other.id}))
        uow.tasks.save(
            Task(exam_id=exam.id, number="3", position=2, topic_ids={wanted.id, other.id})
        )
        uow.commit()
    with uow_factory() as uow:
        assert [t.number for t in uow.tasks.list_by_topic(wanted.id)] == ["1", "3"]
        uow.topics.delete(other.id)
        uow.commit()
    with uow_factory() as uow:
        assert [t.name for t in uow.topics.list_by_subject("IDATT2202")] == ["Paging"]
        assert uow.tasks.get(uow.tasks.list_by_exam(exam.id)[2].id).topic_ids == {wanted.id}


# --- attempts ----------------------------------------------------------------


@pytest.fixture
def task(uow_factory, exam):
    task = Task(exam_id=exam.id, number="1", text="…")
    with uow_factory() as uow:
        uow.tasks.save(task)
        uow.commit()
    return task


def test_attempt_round_trip_listed_oldest_first(uow_factory, task, now):
    first = Attempt(
        task_id=task.id,
        attempted_at=now - timedelta(days=1),
        grade=Grade.AGAIN,
        time_spent=timedelta(minutes=12, seconds=30),
        answer="x = 2",
        note="glemte fortegnet",
    )
    second = Attempt(task_id=task.id, attempted_at=now, grade=Grade.EASY)
    with uow_factory() as uow:
        uow.attempts.add(second)
        uow.attempts.add(first)
        uow.commit()
    with uow_factory() as uow:
        assert uow.attempts.list_by_task(task.id) == [first, second]


def test_all_attempts_and_review_states_can_be_listed(uow_factory, exam, task, now):
    other = Task(exam_id=exam.id, number="2", position=1)
    later = Attempt(task_id=other.id, attempted_at=now, grade=Grade.GOOD)
    earlier = Attempt(task_id=task.id, attempted_at=now - timedelta(hours=1), grade=Grade.AGAIN)
    with uow_factory() as uow:
        uow.tasks.save(other)
        uow.attempts.add(later)
        uow.attempts.add(earlier)
        uow.review_states.save(ReviewState(task_id=task.id, due=now))
        uow.review_states.save(ReviewState(task_id=other.id, due=now + timedelta(days=1)))
        uow.commit()
    with uow_factory() as uow:
        assert uow.attempts.list_all() == [earlier, later]
        assert {state.task_id for state in uow.review_states.list_all()} == {task.id, other.id}


def test_an_attempt_cannot_be_added_twice(uow_factory, task, now):
    attempt = Attempt(task_id=task.id, attempted_at=now, grade=Grade.GOOD)
    with uow_factory() as uow:
        uow.attempts.add(attempt)
        uow.commit()
    with pytest.raises(IntegrityError), uow_factory() as uow:
        uow.attempts.add(attempt)


# --- review states -----------------------------------------------------------


def test_review_state_round_trip_and_update(uow_factory, task, now):
    fresh = ReviewState(task_id=task.id, due=now)
    reviewed = ReviewState(
        task_id=task.id,
        due=now + timedelta(days=3),
        phase=ReviewPhase.REVIEW,
        step=None,
        stability=3.17,
        difficulty=5.28,
        last_review=now,
    )
    with uow_factory() as uow:
        assert uow.review_states.get(task.id) is None
        uow.review_states.save(fresh)
        uow.commit()
    with uow_factory() as uow:
        assert uow.review_states.get(task.id) == fresh
        uow.review_states.save(reviewed)
        uow.commit()
    with uow_factory() as uow:
        assert uow.review_states.get(task.id) == reviewed


# --- settings ----------------------------------------------------------------


def test_settings_are_stored_as_documents_by_key(uow_factory):
    with uow_factory() as uow:
        assert uow.settings.get("app") is None
        uow.settings.set("app", {"mastery_weight": 0.5, "preferred_language": "nn"})
        uow.commit()
    with uow_factory() as uow:
        assert uow.settings.get("app") == {"mastery_weight": 0.5, "preferred_language": "nn"}
        uow.settings.set("app", {"mastery_weight": 0.7})
        uow.commit()
    with uow_factory() as uow:
        assert uow.settings.get("app") == {"mastery_weight": 0.7}
        assert uow.settings.get("other") is None
