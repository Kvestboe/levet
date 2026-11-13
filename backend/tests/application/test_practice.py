from datetime import timedelta
from uuid import uuid4

import pytest

from levet.application.errors import Conflict, NotFound
from levet.application.practice import PracticeService
from levet.domain import Exam, ExamStatus, Grade, Region, ReviewPhase, Subject, Task, Topic
from levet.domain.practice import Reason


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


@pytest.fixture
def clock(now):
    return Clock(now)


@pytest.fixture
def practice(uow_factory, clock):
    return PracticeService(uow_factory, clock)


class Library:
    """Puts subjects, exams, topics and tasks in the database."""

    def __init__(self, uow_factory, now):
        self.uow_factory = uow_factory
        self.now = now
        self.exams = 0

    def subject(self, code="STAT", exam_date=None):
        with self.uow_factory() as uow:
            uow.subjects.save(Subject(code, f"Subject {code}", exam_date))
            uow.commit()
        return code

    def topic(self, name, subject="STAT"):
        topic = Topic(subject_code=subject, name=name)
        with self.uow_factory() as uow:
            uow.topics.save(topic)
            uow.commit()
        return topic

    def exam(self, label="Høst 2024", subject="STAT", status=ExamStatus.READY):
        self.exams += 1
        exam = Exam(
            subject_code=subject,
            label=label,
            pdf_key="exams/x/exam.pdf",
            uploaded_at=self.now + timedelta(minutes=self.exams),
            status=status,
            page_count=3,
        )
        with self.uow_factory() as uow:
            uow.exams.save(exam)
            uow.commit()
        return exam

    def task(self, exam, number, *topics, position=None, **fields):
        with self.uow_factory() as uow:
            task = Task(
                exam_id=exam.id,
                number=number,
                position=len(uow.tasks.list_by_exam(exam.id)) if position is None else position,
                topic_ids={topic.id for topic in topics},
                **fields,
            )
            uow.tasks.save(task)
            uow.commit()
        return task


@pytest.fixture
def library(uow_factory, now):
    library = Library(uow_factory, now)
    library.subject()
    return library


def numbers(queue):
    return [entry.practice.task.number for entry in queue.entries]


# --- what can be practised ---------------------------------------------------


def test_only_tasks_of_approved_exams_are_queued(practice, library):
    topic = library.topic("Normalfordeling")
    library.task(library.exam("Klar"), "1", topic)
    library.task(library.exam("Til gjennomgang", status=ExamStatus.NEEDS_REVIEW), "2", topic)

    queue = practice.queue()

    assert numbers(queue) == ["1"]
    assert (queue.total, queue.due_count) == (1, 0)


def test_a_task_with_parts_is_not_practised_itself_but_gives_its_parts_context(practice, library):
    topic = library.topic("Normalfordeling")
    exam = library.exam()
    parent = library.task(
        exam,
        "3",
        topic,
        title="Kulediametere",
        image_keys=("exams/x/task-images/intro.png",),
        solution_text="Løsning til hele oppgaven",
    )
    part_a = library.task(exam, "3a", topic, parent_id=parent.id, solution_text="Svar a")
    part_b = library.task(exam, "3b", topic, parent_id=parent.id)
    library.task(exam, "4", topic)

    queue = practice.queue()

    assert numbers(queue) == ["3a", "3b", "4"]
    first, second, alone = (entry.practice for entry in queue.entries)
    assert first.parent == parent
    assert [task.number for task in first.group] == ["3", "3a", "3b"]
    assert first.solution == part_a  # its own solution
    assert second.solution == parent  # falls back to the task's
    assert second.task == part_b
    assert alone.parent is None
    assert [task.number for task in alone.group] == ["4"]
    assert alone.solution is None


def test_queue_entries_say_why_and_carry_the_topic_and_history(practice, library, clock):
    weak = library.topic("Hypotesetest")
    exam = library.exam()
    failed = library.task(exam, "1", weak)
    library.task(exam, "2", weak)
    practice.record_attempt(failed.id, Grade.AGAIN)
    clock.advance(minutes=5)

    queue = practice.queue()

    assert numbers(queue) == ["1", "2"]
    due, new = queue.entries
    assert (due.reason, new.reason) == (Reason.DUE, Reason.NEW)
    assert due.topic == weak
    assert due.practice.topics == (weak,)
    assert (due.practice.attempt_count, due.practice.last_grade) == (1, Grade.AGAIN)
    assert due.practice.due < clock()
    assert (new.practice.attempt_count, new.practice.last_grade, new.practice.due) == (
        0,
        None,
        None,
    )
    assert (queue.total, queue.due_count) == (2, 1)


def test_the_queue_is_cut_to_the_limit_but_reports_its_full_size(practice, library):
    topic = library.topic("Normalfordeling")
    exam = library.exam()
    for number in range(1, 8):
        library.task(exam, str(number), topic)

    queue = practice.queue(limit=3)

    assert numbers(queue) == ["1", "2", "3"]
    assert queue.total == 7


def test_tasks_come_exam_by_exam_in_document_order_when_nothing_else_decides(practice, library):
    topic = library.topic("Normalfordeling")
    first, second = library.exam("Høst 2023"), library.exam("Høst 2024")
    library.task(second, "1", topic)
    library.task(first, "2", topic, position=1)
    library.task(first, "1", topic, position=0)

    assert [(e.practice.exam.label, e.practice.task.number) for e in practice.queue().entries] == [
        ("Høst 2023", "1"),
        ("Høst 2023", "2"),
        ("Høst 2024", "1"),
    ]


def test_the_queue_can_be_limited_to_one_topic(practice, library):
    wanted, other = library.topic("Regresjon"), library.topic("Varians")
    exam = library.exam()
    library.task(exam, "1", other)
    library.task(exam, "2", wanted)
    library.task(exam, "3", wanted, other)

    assert numbers(practice.queue(topic_id=wanted.id)) == ["2", "3"]
    with pytest.raises(NotFound):
        practice.queue(topic_id=uuid4())


def test_an_empty_library_gives_an_empty_queue(practice):
    queue = practice.queue()
    assert (queue.entries, queue.total, queue.due_count) == ((), 0, 0)
    assert practice.topics() == []


# --- logging attempts --------------------------------------------------------


def test_an_attempt_is_stored_and_the_task_is_scheduled(practice, library, uow_factory, clock):
    exam = library.exam()
    task = library.task(exam, "1", library.topic("Normalfordeling"))

    result = practice.record_attempt(
        task.id, Grade.GOOD, time_spent=timedelta(minutes=7), answer=" x = 2 ", note="  "
    )

    assert result.attempt.task_id == task.id
    assert result.attempt.attempted_at == clock()
    assert result.attempt.time_spent == timedelta(minutes=7)
    assert (result.attempt.answer, result.attempt.note) == ("x = 2", None)
    assert result.state.due > clock()
    with uow_factory() as uow:
        assert uow.attempts.list_by_task(task.id) == [result.attempt]
        assert uow.review_states.get(task.id) == result.state


def test_each_attempt_is_kept_and_moves_the_schedule_on(practice, library, uow_factory, clock):
    task = library.task(library.exam(), "1", library.topic("Normalfordeling"))

    failed = practice.record_attempt(task.id, Grade.AGAIN)
    clock.advance(minutes=2)
    retried = practice.record_attempt(task.id, Grade.GOOD)
    clock.advance(minutes=15)
    passed = practice.record_attempt(task.id, Grade.GOOD)

    with uow_factory() as uow:
        assert [a.grade for a in uow.attempts.list_by_task(task.id)] == [
            Grade.AGAIN,
            Grade.GOOD,
            Grade.GOOD,
        ]
    assert failed.state.due - failed.attempt.attempted_at < timedelta(minutes=5)
    assert retried.state.phase is ReviewPhase.LEARNING
    assert passed.state.phase is ReviewPhase.REVIEW
    assert passed.state.due - clock() >= timedelta(days=1)


def test_a_failed_task_leaves_the_front_of_the_queue_and_returns_when_due(practice, library, clock):
    topic = library.topic("Normalfordeling")
    exam = library.exam()
    first = library.task(exam, "1", topic)
    library.task(exam, "2", topic)

    practice.record_attempt(first.id, Grade.AGAIN)
    assert numbers(practice.queue()) == ["2", "1"]

    clock.advance(minutes=2)
    queue = practice.queue()
    assert numbers(queue) == ["1", "2"]
    assert queue.entries[0].reason is Reason.DUE


def test_attempts_are_refused_for_what_cannot_be_practised(practice, library):
    topic = library.topic("Normalfordeling")
    exam = library.exam()
    parent = library.task(exam, "1", topic)
    library.task(exam, "1a", topic, parent_id=parent.id)
    pending = library.task(library.exam("Ny", status=ExamStatus.NEEDS_REVIEW), "1", topic)

    with pytest.raises(Conflict):
        practice.record_attempt(parent.id, Grade.GOOD)  # has sub-tasks
    with pytest.raises(Conflict):
        practice.record_attempt(pending.id, Grade.GOOD)  # exam not approved
    with pytest.raises(NotFound):
        practice.record_attempt(uuid4(), Grade.GOOD)


# --- progress per topic ------------------------------------------------------


def test_topics_are_listed_weakest_first_with_their_scores(practice, library, clock):
    strong, weak, untouched = (
        library.topic("Regresjon"),
        library.topic("Hypotesetest"),
        library.topic("Varians"),
    )
    exam = library.exam()
    good = library.task(exam, "1", strong)
    bad = library.task(exam, "2", weak)
    library.task(exam, "3", weak)
    library.task(exam, "4", untouched)
    practice.record_attempt(good.id, Grade.EASY)
    practice.record_attempt(bad.id, Grade.AGAIN)

    progress = practice.topics()

    assert [p.topic.name for p in progress] == ["Varians", "Hypotesetest", "Regresjon"]
    by_name = {p.topic.name: p.score for p in progress}
    assert by_name["Varians"].weakness.weakness == 1.0
    assert by_name["Regresjon"].weakness.weakness == pytest.approx(0.0)
    assert (by_name["Hypotesetest"].task_count, by_name["Hypotesetest"].attempted_count) == (2, 1)
    assert by_name["Hypotesetest"].weakness.mastery == pytest.approx(0.0)


def test_topics_without_practisable_tasks_are_not_listed(practice, library):
    used = library.topic("Regresjon")
    library.topic("Ubrukt")
    pending_only = library.topic("Bare i ikke-godkjent eksamen")
    library.task(library.exam(), "1", used)
    library.task(library.exam("Ny", status=ExamStatus.NEEDS_REVIEW), "1", pending_only)

    assert [p.topic.name for p in practice.topics()] == ["Regresjon"]


def test_the_subject_with_the_closer_exam_outranks_the_other(practice, library, now):
    library.subject("STAT", exam_date=now.date() + timedelta(days=40))
    library.subject("OS", exam_date=now.date() + timedelta(days=4))
    stats = library.topic("Regresjon", "STAT")
    systems = library.topic("Paging", "OS")
    library.task(library.exam("Statistikk", subject="STAT"), "1", stats)
    library.task(library.exam("Operativsystemer", subject="OS"), "1", systems)

    progress = practice.topics()

    assert [p.topic.name for p in progress] == ["Paging", "Regresjon"]
    assert progress[0].score.urgency > progress[1].score.urgency
    assert [e.practice.exam.subject_code for e in practice.queue().entries] == ["OS", "STAT"]


def test_a_subject_without_an_exam_date_still_gets_practised(practice, library):
    library.subject("STAT", exam_date=None)
    library.task(library.exam(), "1", library.topic("Regresjon"))
    assert numbers(practice.queue()) == ["1"]
    assert practice.topics()[0].score.urgency == pytest.approx(0.2)


# --- mock exam ---------------------------------------------------------------


def test_a_mock_exam_is_the_exams_practisable_tasks_in_document_order(practice, library):
    topic = library.topic("Regresjon")
    exam, other = library.exam("Høst 2024"), library.exam("Vår 2024")
    parent = library.task(exam, "1", topic, regions=(Region(page=1, top=0.1, bottom=0.2),))
    library.task(exam, "1a", topic, parent_id=parent.id, points=2)
    library.task(exam, "1b", topic, parent_id=parent.id, points=3)
    library.task(exam, "2", topic)
    library.task(other, "1", topic)

    tasks = practice.exam_tasks(exam.id)

    assert [t.task.number for t in tasks] == ["1a", "1b", "2"]
    assert [t.task.points for t in tasks] == [2, 3, None]
    assert tasks[0].parent == parent
    assert all(t.exam.id == exam.id for t in tasks)


def test_a_mock_exam_needs_an_approved_exam(practice, library):
    pending = library.exam("Ny", status=ExamStatus.NEEDS_REVIEW)
    with pytest.raises(Conflict):
        practice.exam_tasks(pending.id)
    with pytest.raises(NotFound):
        practice.exam_tasks(uuid4())
