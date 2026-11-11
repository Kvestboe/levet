from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from levet.domain.attempt import Attempt, Grade
from levet.domain.scoring import (
    ScoringConfig,
    coverage_gap,
    mastery,
    staleness,
    subject_urgency,
    topic_priority,
    topic_weakness,
)

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
TODAY = NOW.date()


def attempt(task_id, grade, days_ago=0.0):
    return Attempt(task_id=task_id, attempted_at=NOW - timedelta(days=days_ago), grade=grade)


# --- grade → score -----------------------------------------------------------


def test_grades_map_to_increasing_scores_spanning_zero_to_one():
    scores = [g.score for g in (Grade.AGAIN, Grade.HARD, Grade.GOOD, Grade.EASY)]
    assert scores == sorted(scores)
    assert len(set(scores)) == 4
    assert scores[0] == 0.0
    assert scores[-1] == 1.0


# --- mastery -----------------------------------------------------------------


def test_mastery_is_none_without_attempts():
    assert mastery([], NOW) is None


def test_mastery_of_a_single_attempt_is_its_score_however_old():
    task = uuid4()
    assert mastery([attempt(task, Grade.GOOD, days_ago=30)], NOW) == pytest.approx(0.8)


def test_mastery_weights_an_attempt_one_half_life_old_at_half():
    task = uuid4()
    attempts = [attempt(task, Grade.EASY, days_ago=7), attempt(task, Grade.AGAIN)]
    # (0.5 * 1.0 + 1.0 * 0.0) / (0.5 + 1.0)
    assert mastery(attempts, NOW) == pytest.approx(1 / 3)


def test_recent_failure_outweighs_old_success():
    task = uuid4()
    failed_recently = [attempt(task, Grade.EASY, days_ago=14), attempt(task, Grade.AGAIN)]
    failed_long_ago = [attempt(task, Grade.AGAIN, days_ago=14), attempt(task, Grade.EASY)]
    assert mastery(failed_recently, NOW) < 0.5 < mastery(failed_long_ago, NOW)


def test_mastery_half_life_is_configurable():
    task = uuid4()
    attempts = [attempt(task, Grade.EASY, days_ago=7), attempt(task, Grade.AGAIN)]
    slow = ScoringConfig(half_life_days=70)
    assert mastery(attempts, NOW, slow) > mastery(attempts, NOW)


def test_mastery_ignores_attempts_after_now():
    task = uuid4()
    attempts = [attempt(task, Grade.AGAIN, days_ago=3), attempt(task, Grade.EASY, days_ago=1)]
    as_of_two_days_ago = NOW - timedelta(days=2)
    assert mastery(attempts, as_of_two_days_ago) == pytest.approx(0.0)


def test_mastery_survives_attempts_old_enough_to_underflow_the_decay():
    task = uuid4()
    attempts = [
        attempt(task, Grade.EASY, days_ago=365 * 40),
        attempt(task, Grade.AGAIN, days_ago=365 * 40 + 7),
    ]
    assert mastery(attempts, NOW) == pytest.approx(2 / 3)


# --- staleness ---------------------------------------------------------------


def test_staleness_is_zero_right_after_practice_and_half_after_one_half_life():
    assert staleness(NOW, NOW) == pytest.approx(0.0)
    assert staleness(NOW - timedelta(days=7), NOW) == pytest.approx(0.5)
    assert staleness(NOW - timedelta(days=14), NOW) == pytest.approx(0.75)


def test_never_practised_is_fully_stale():
    assert staleness(None, NOW) == 1.0


# --- coverage gap ------------------------------------------------------------


def test_coverage_gap_is_the_fraction_of_tasks_never_attempted():
    tasks = [uuid4() for _ in range(4)]
    assert coverage_gap(tasks, []) == 1.0
    assert coverage_gap(tasks, tasks[:1]) == pytest.approx(0.75)
    assert coverage_gap(tasks, tasks) == 0.0


def test_coverage_gap_ignores_attempts_at_tasks_outside_the_topic():
    tasks = [uuid4(), uuid4()]
    assert coverage_gap(tasks, [uuid4(), uuid4(), uuid4()]) == 1.0


# --- weakness ----------------------------------------------------------------


def test_unattempted_topic_is_maximally_weak():
    result = topic_weakness([uuid4(), uuid4()], [], NOW)
    assert result.weakness == 1.0
    assert result.mastery is None
    assert result.staleness == 1.0
    assert result.coverage_gap == 1.0


def test_weakness_combines_the_three_terms_with_the_default_weights():
    tasks = [uuid4() for _ in range(4)]
    attempts = [attempt(tasks[0], Grade.GOOD, days_ago=7), attempt(tasks[1], Grade.AGAIN)]

    result = topic_weakness(tasks, attempts, NOW)

    assert result.mastery == pytest.approx(0.4 / 1.5)
    assert result.staleness == pytest.approx(0.0)
    assert result.coverage_gap == pytest.approx(0.5)
    assert result.weakness == pytest.approx(0.6 * (1 - 0.4 / 1.5) + 0.25 * 0.0 + 0.15 * 0.5)


def test_fully_mastered_fresh_and_covered_topic_has_no_weakness():
    tasks = [uuid4(), uuid4()]
    attempts = [attempt(t, Grade.EASY) for t in tasks]
    assert topic_weakness(tasks, attempts, NOW).weakness == pytest.approx(0.0)


def test_failing_makes_a_topic_weaker_than_succeeding():
    tasks = [uuid4(), uuid4()]
    failed = topic_weakness(tasks, [attempt(tasks[0], Grade.AGAIN)], NOW)
    passed = topic_weakness(tasks, [attempt(tasks[0], Grade.GOOD)], NOW)
    assert failed.weakness > passed.weakness


def test_a_topic_grows_weaker_the_longer_it_is_left_alone():
    tasks = [uuid4()]
    attempts = [attempt(tasks[0], Grade.EASY)]
    weaknesses = [
        topic_weakness(tasks, attempts, NOW + timedelta(days=d)).weakness for d in (0, 7, 30)
    ]
    assert weaknesses == sorted(weaknesses)
    assert weaknesses[0] < weaknesses[-1]


def test_weakness_ignores_attempts_at_other_topics_tasks():
    tasks = [uuid4()]
    result = topic_weakness(tasks, [attempt(uuid4(), Grade.EASY)], NOW)
    assert result.weakness == 1.0


def test_weakness_as_of_an_earlier_time_ignores_later_attempts():
    tasks = [uuid4()]
    attempts = [attempt(tasks[0], Grade.EASY, days_ago=1)]
    assert topic_weakness(tasks, attempts, NOW - timedelta(days=2)).weakness == 1.0


def test_weights_are_configurable():
    tasks = [uuid4(), uuid4()]
    attempts = [attempt(tasks[0], Grade.EASY)]
    coverage_only = ScoringConfig(mastery_weight=0, staleness_weight=0, coverage_weight=1)
    assert topic_weakness(tasks, attempts, NOW, coverage_only).weakness == pytest.approx(0.5)


def test_weights_are_normalised_so_weakness_stays_in_range():
    doubled = ScoringConfig(mastery_weight=1.2, staleness_weight=0.5, coverage_weight=0.3)
    tasks = [uuid4() for _ in range(4)]
    attempts = [attempt(tasks[0], Grade.HARD, days_ago=3)]

    assert topic_weakness(tasks, [], NOW, doubled).weakness == 1.0
    assert topic_weakness(tasks, attempts, NOW, doubled).weakness == pytest.approx(
        topic_weakness(tasks, attempts, NOW).weakness
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mastery_weight": -0.1},
        {"mastery_weight": 0, "staleness_weight": 0, "coverage_weight": 0},
        {"staleness_weight": float("nan")},
        {"half_life_days": 0},
        {"urgency_half_life_days": -1},
        {"urgency_floor": 1.5},
    ],
)
def test_invalid_config_is_rejected(kwargs):
    with pytest.raises(ValueError):
        ScoringConfig(**kwargs)


def test_naive_now_is_rejected():
    with pytest.raises(ValueError):
        topic_weakness([uuid4()], [], datetime(2026, 11, 11))


# --- urgency and priority ----------------------------------------------------


def test_urgency_is_one_on_exam_day_and_decays_towards_the_floor():
    assert subject_urgency(TODAY, TODAY) == pytest.approx(1.0)
    assert subject_urgency(TODAY + timedelta(days=14), TODAY) == pytest.approx(0.6)
    assert subject_urgency(TODAY + timedelta(days=3650), TODAY) == pytest.approx(0.2)


def test_closer_exam_is_more_urgent():
    urgencies = [subject_urgency(TODAY + timedelta(days=d), TODAY) for d in (1, 5, 20, 60)]
    assert urgencies == sorted(urgencies, reverse=True)
    assert len(set(urgencies)) == 4


def test_subject_without_exam_date_or_with_a_past_exam_sits_at_the_floor():
    assert subject_urgency(None, TODAY) == 0.2
    assert subject_urgency(date(2026, 11, 10), TODAY) == 0.2


def test_urgency_floor_and_half_life_are_configurable():
    config = ScoringConfig(urgency_floor=0.5, urgency_half_life_days=7)
    assert subject_urgency(None, TODAY, config) == 0.5
    assert subject_urgency(TODAY + timedelta(days=7), TODAY, config) == pytest.approx(0.75)


def test_priority_is_weakness_scaled_by_urgency():
    assert topic_priority(0.5, 0.6) == pytest.approx(0.3)


def test_equally_weak_topic_in_the_subject_with_the_closer_exam_ranks_higher():
    soon = subject_urgency(TODAY + timedelta(days=3), TODAY)
    later = subject_urgency(TODAY + timedelta(days=20), TODAY)
    assert topic_priority(0.7, soon) > topic_priority(0.7, later)
