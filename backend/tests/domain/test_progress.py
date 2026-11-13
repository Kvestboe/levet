from datetime import UTC, date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from levet.domain import Attempt, Grade
from levet.domain.progress import mastery_history, practice_days, streak
from levet.domain.scoring import ScoringConfig

OSLO = ZoneInfo("Europe/Oslo")
TODAY = date(2026, 11, 13)
NOW = datetime(2026, 11, 13, 15, 0, tzinfo=OSLO)


def days_ago(*offsets):
    return {TODAY - timedelta(days=offset) for offset in offsets}


def attempt(when, grade=Grade.GOOD):
    return Attempt(task_id=uuid4(), attempted_at=when, grade=grade)


# --- streak ------------------------------------------------------------------


def test_no_practice_means_no_streak():
    assert streak(set(), TODAY) == 0


def test_consecutive_days_up_to_today_are_counted():
    assert streak(days_ago(0), TODAY) == 1
    assert streak(days_ago(0, 1, 2, 3), TODAY) == 4


def test_a_streak_is_still_alive_before_todays_practice():
    assert streak(days_ago(1, 2, 3), TODAY) == 3


def test_a_missed_day_breaks_the_streak():
    assert streak(days_ago(2, 3, 4), TODAY) == 0
    assert streak(days_ago(0, 1, 3, 4, 5), TODAY) == 2


def test_practice_dated_in_the_future_does_not_count():
    assert streak({TODAY + timedelta(days=1)}, TODAY) == 0


# --- practice days -----------------------------------------------------------


def test_days_are_counted_in_the_users_time_zone():
    # 23:30 UTC on the 12th is already 00:30 on the 13th in Oslo.
    late = attempt(datetime(2026, 11, 12, 23, 30, tzinfo=UTC))
    assert practice_days([late], UTC) == {date(2026, 11, 12)}
    assert practice_days([late], OSLO) == {date(2026, 11, 13)}


def test_several_attempts_on_one_day_are_one_day():
    morning = attempt(datetime(2026, 11, 13, 8, 0, tzinfo=OSLO))
    evening = attempt(datetime(2026, 11, 13, 21, 0, tzinfo=OSLO))
    assert practice_days([morning, evening], OSLO) == {TODAY}


# --- mastery over time -------------------------------------------------------


def test_no_attempts_means_no_history():
    assert mastery_history([], NOW, OSLO) == []


def test_history_runs_day_by_day_from_the_first_attempt_to_today():
    attempts = [attempt(NOW - timedelta(days=3))]
    history = mastery_history(attempts, NOW, OSLO)
    assert [day for day, _ in history] == [TODAY - timedelta(days=d) for d in (3, 2, 1, 0)]
    assert [value for _, value in history] == [pytest.approx(0.8)] * 4


def test_each_day_shows_mastery_as_it_stood_at_the_end_of_that_day():
    attempts = [
        attempt(NOW - timedelta(days=2), Grade.AGAIN),
        attempt(NOW - timedelta(days=1), Grade.EASY),
        attempt(NOW - timedelta(hours=1), Grade.EASY),
    ]
    history = dict(mastery_history(attempts, NOW, OSLO))

    assert history[TODAY - timedelta(days=2)] == pytest.approx(0.0)
    assert 0.5 < history[TODAY - timedelta(days=1)] < history[TODAY] < 1.0


def test_an_attempt_late_in_the_evening_belongs_to_that_local_day():
    late = attempt(datetime(2026, 11, 11, 23, 30, tzinfo=OSLO), Grade.EASY)
    history = mastery_history([late], NOW, OSLO)
    assert history[0] == (date(2026, 11, 11), pytest.approx(1.0))


def test_todays_value_is_mastery_right_now_not_at_midnight():
    later_today = attempt(NOW + timedelta(hours=2), Grade.AGAIN)
    earlier = attempt(NOW - timedelta(hours=2), Grade.EASY)
    history = mastery_history([earlier, later_today], NOW, OSLO)
    assert history == [(TODAY, pytest.approx(1.0))]


def test_history_is_limited_to_the_most_recent_days():
    attempts = [attempt(NOW - timedelta(days=200))]
    history = mastery_history(attempts, NOW, OSLO, max_days=30)
    assert len(history) == 30
    assert history[0][0] == TODAY - timedelta(days=29)
    assert history[-1][0] == TODAY


def test_history_uses_the_configured_half_life():
    attempts = [attempt(NOW - timedelta(days=7), Grade.EASY), attempt(NOW, Grade.AGAIN)]
    default = mastery_history(attempts, NOW, OSLO)[-1][1]
    slow = mastery_history(attempts, NOW, OSLO, config=ScoringConfig(half_life_days=70))[-1][1]
    assert default == pytest.approx(1 / 3)
    assert slow > default
