from datetime import timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from levet.application.errors import InvalidInput, NotFound
from levet.application.practice import PracticeService
from levet.application.progress import ProgressService
from levet.application.settings import AppSettings, SettingsService
from levet.domain import Exam, ExamStatus, Grade, Language, Subject, Task, Topic

OSLO = ZoneInfo("Europe/Oslo")


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
def preferences(uow_factory):
    return SettingsService(uow_factory)


@pytest.fixture
def scoring(preferences):
    return lambda: preferences.get().scoring


@pytest.fixture
def practice(uow_factory, clock, scoring):
    return PracticeService(uow_factory, clock, scoring)


@pytest.fixture
def progress(uow_factory, clock, scoring):
    return ProgressService(uow_factory, clock, scoring)


@pytest.fixture
def library(uow_factory, now):
    """Adds subjects, topics and approved exams with tasks."""

    class Library:
        def subject(self, code="STAT", exam_date=None):
            with uow_factory() as uow:
                uow.subjects.save(Subject(code, f"Subject {code}", exam_date))
                uow.commit()

        def topic(self, name, subject="STAT"):
            topic = Topic(subject_code=subject, name=name)
            with uow_factory() as uow:
                uow.topics.save(topic)
                uow.commit()
            return topic

        def exam(self, label="Høst 2024", subject="STAT", status=ExamStatus.READY):
            exam = Exam(
                subject_code=subject,
                label=label,
                pdf_key="exams/x/exam.pdf",
                uploaded_at=now,
                status=status,
                page_count=3,
            )
            with uow_factory() as uow:
                uow.exams.save(exam)
                uow.commit()
            return exam

        def task(self, exam, number, *topics):
            with uow_factory() as uow:
                task = Task(
                    exam_id=exam.id,
                    number=number,
                    position=len(uow.tasks.list_by_exam(exam.id)),
                    topic_ids={topic.id for topic in topics},
                )
                uow.tasks.save(task)
                uow.commit()
            return task

    library = Library()
    library.subject()
    return library


# --- settings ----------------------------------------------------------------


def test_settings_start_from_the_defaults(preferences):
    settings = preferences.get()
    assert settings == AppSettings()
    assert settings.scoring.mastery_weight == 0.60
    assert settings.preferred_language is Language.BOKMAL


def test_the_environment_can_supply_other_defaults(uow_factory):
    defaults = AppSettings(preferred_language=Language.ENGLISH)
    assert SettingsService(uow_factory, defaults).get().preferred_language is Language.ENGLISH


def test_changed_settings_are_kept_and_the_rest_left_alone(preferences, uow_factory):
    updated = preferences.update(mastery_weight=0.2, preferred_language="nn")

    assert updated.scoring.mastery_weight == 0.2
    assert updated.scoring.staleness_weight == 0.25  # untouched
    assert updated.preferred_language is Language.NYNORSK
    # A new service on the same database sees them: they are stored, not remembered.
    assert SettingsService(uow_factory).get() == updated

    again = preferences.update(coverage_weight=0.5)
    assert (again.scoring.mastery_weight, again.scoring.coverage_weight) == (0.2, 0.5)
    assert again.preferred_language is Language.NYNORSK


def test_a_stored_setting_wins_over_a_default_from_the_environment(uow_factory):
    SettingsService(uow_factory).update(preferred_language="nn")
    from_env = SettingsService(uow_factory, AppSettings(preferred_language=Language.ENGLISH))
    assert from_env.get().preferred_language is Language.NYNORSK


@pytest.mark.parametrize(
    "changes",
    [
        {"mastery_weight": -1},
        {"mastery_weight": 0, "staleness_weight": 0, "coverage_weight": 0},
        {"preferred_language": "german"},
    ],
)
def test_invalid_settings_are_refused_and_nothing_is_saved(preferences, changes):
    preferences.update(mastery_weight=0.3)
    with pytest.raises(InvalidInput):
        preferences.update(**changes)
    assert preferences.get().scoring.mastery_weight == 0.3
    assert preferences.get().preferred_language is Language.BOKMAL


def test_unusable_stored_settings_fall_back_to_the_defaults(preferences, uow_factory):
    with uow_factory() as uow:
        uow.settings.set("app", {"mastery_weight": "a lot", "preferred_language": "xx"})
        uow.commit()
    assert preferences.get() == AppSettings()


def test_changing_the_weights_changes_how_topics_are_ranked(practice, preferences, library, clock):
    half_covered, stale = library.topic("Halvt dekket"), library.topic("Gammelt")
    exam = library.exam()
    done = library.task(exam, "1", half_covered)
    library.task(exam, "2", half_covered)
    old = library.task(exam, "3", stale)
    practice.record_attempt(old.id, Grade.EASY)
    clock.advance(days=30)
    practice.record_attempt(done.id, Grade.EASY)

    def ranking():
        return [p.topic.name for p in practice.topics()]

    preferences.update(mastery_weight=0, staleness_weight=1, coverage_weight=0)
    assert ranking() == ["Gammelt", "Halvt dekket"]
    preferences.update(mastery_weight=0, staleness_weight=0, coverage_weight=1)
    assert ranking() == ["Halvt dekket", "Gammelt"]


# --- dashboard ---------------------------------------------------------------


def test_an_empty_app_has_an_empty_dashboard(progress):
    dashboard = progress.dashboard(OSLO)
    assert dashboard.weakest_topics == ()
    assert (dashboard.due_count, dashboard.task_count, dashboard.attempted_count) == (0, 0, 0)
    assert (dashboard.streak_days, dashboard.attempts_today) == (0, 0)
    assert dashboard.subjects == ()


def test_dashboard_lists_subjects_nearest_exam_first(progress, library, now):
    library.subject("LATER", now.date() + timedelta(days=30))
    library.subject("SOON", now.date() + timedelta(days=3))
    assert [s.code for s in progress.dashboard(OSLO).subjects] == ["SOON", "LATER", "STAT"]


def test_dashboard_counts_tasks_attempts_and_due_tasks(progress, practice, library, clock):
    topic = library.topic("Normalfordeling")
    exam = library.exam()
    first = library.task(exam, "1", topic)
    second = library.task(exam, "2", topic)
    library.task(exam, "3", topic)
    library.task(library.exam("Ny", status=ExamStatus.NEEDS_REVIEW), "1", topic)

    practice.record_attempt(first.id, Grade.AGAIN)
    practice.record_attempt(second.id, Grade.GOOD)
    practice.record_attempt(second.id, Grade.GOOD)
    assert progress.dashboard(OSLO).due_count == 0  # the failed task is not due yet

    clock.advance(minutes=5)
    dashboard = progress.dashboard(OSLO)

    assert dashboard.due_count == 1
    assert (dashboard.task_count, dashboard.attempted_count) == (3, 2)
    assert dashboard.attempts_today == 3


def test_dashboard_shows_the_five_weakest_topics_weakest_first(progress, practice, library):
    exam = library.exam()
    strong = library.topic("Sterkt")
    done = library.task(exam, "0", strong)
    for name in ("A", "B", "C", "D", "E"):
        library.task(exam, name, library.topic(f"Urørt {name}"))
    practice.record_attempt(done.id, Grade.EASY)

    weakest = progress.dashboard(OSLO).weakest_topics

    assert [p.topic.name for p in weakest] == [f"Urørt {name}" for name in "ABCDE"]
    assert all(p.score.weakness.weakness == 1.0 for p in weakest)


def test_the_streak_counts_days_in_the_users_time_zone(progress, practice, library, clock):
    task = library.task(library.exam(), "1", library.topic("Normalfordeling"))
    # The fixed clock starts at 12:00 UTC; practise on three consecutive days.
    for _ in range(3):
        practice.record_attempt(task.id, Grade.GOOD)
        clock.advance(days=1)
    clock.advance(days=-1)  # back to the day of the last attempt

    assert progress.dashboard(OSLO).streak_days == 3
    assert progress.dashboard(OSLO).attempts_today == 1

    clock.advance(days=1)  # nothing practised yet today: the streak is still alive
    assert (progress.dashboard(OSLO).streak_days, progress.dashboard(OSLO).attempts_today) == (3, 0)

    clock.advance(days=1)  # a whole day missed
    assert progress.dashboard(OSLO).streak_days == 0


# --- topic detail ------------------------------------------------------------


def test_topic_detail_shows_score_history_tasks_and_attempts(progress, practice, library, clock):
    topic, other = library.topic("Normalfordeling"), library.topic("Varians")
    exam = library.exam()
    first = library.task(exam, "1a", topic)
    second = library.task(exam, "1b", topic)
    elsewhere = library.task(exam, "2", other)

    practice.record_attempt(first.id, Grade.AGAIN, note="feil tabell")
    clock.advance(days=1)
    practice.record_attempt(first.id, Grade.GOOD, time_spent=timedelta(minutes=4))
    practice.record_attempt(elsewhere.id, Grade.EASY)

    detail = progress.topic(topic.id, OSLO)

    assert detail.progress.topic == topic
    assert (detail.progress.score.task_count, detail.progress.score.attempted_count) == (2, 1)
    assert [t.task.number for t in detail.tasks] == ["1a", "1b"]
    assert [(t.attempt_count, t.last_grade) for t in detail.tasks] == [(2, Grade.GOOD), (0, None)]
    assert second.id == detail.tasks[1].task.id

    # Newest first, and only attempts at this topic's tasks.
    assert [(a.attempt.grade, a.task.number, a.exam.label) for a in detail.attempts] == [
        (Grade.GOOD, "1a", "Høst 2024"),
        (Grade.AGAIN, "1a", "Høst 2024"),
    ]
    assert detail.attempts[1].attempt.note == "feil tabell"
    assert detail.attempts[0].attempt.time_spent == timedelta(minutes=4)

    # Failed on the first day, better on the second.
    assert len(detail.history) == 2
    (day_one, before), (day_two, after) = detail.history
    assert day_two - day_one == timedelta(days=1)
    assert before == pytest.approx(0.0)
    assert after > before


def test_topic_detail_of_an_untouched_topic_has_no_history(progress, library):
    topic = library.topic("Normalfordeling")
    library.task(library.exam(), "1", topic)
    detail = progress.topic(topic.id, OSLO)
    assert detail.history == ()
    assert detail.attempts == ()
    assert detail.progress.score.weakness.weakness == 1.0


def test_topic_detail_needs_a_topic_with_tasks_to_practise(progress, library):
    unused = library.topic("Ubrukt")
    with pytest.raises(NotFound):
        progress.topic(unused.id, OSLO)
    with pytest.raises(NotFound):
        progress.topic(uuid4(), OSLO)


def test_topic_detail_follows_the_configured_weights(progress, practice, preferences, library):
    topic = library.topic("Normalfordeling")
    exam = library.exam()
    done = library.task(exam, "1", topic)
    library.task(exam, "2", topic)
    practice.record_attempt(done.id, Grade.EASY)

    preferences.update(mastery_weight=0, staleness_weight=0, coverage_weight=1)

    assert progress.topic(topic.id, OSLO).progress.score.weakness.weakness == pytest.approx(0.5)
