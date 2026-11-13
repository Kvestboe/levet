from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fsrs import Card, Rating, Scheduler, State

from levet.domain import Grade, ReviewPhase, ReviewState
from levet.domain.scheduling import from_card, rating_for, review, to_card

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)


def after(*grades, start=None):
    """Review a new task with each grade in turn, each time exactly when it falls due."""
    task_id = uuid4()
    state, now = start, NOW
    for grade in grades:
        state = review(state, task_id, grade, now)
        now = state.due
    return state


# --- the mapping -------------------------------------------------------------


def test_each_grade_maps_to_the_fsrs_rating_of_the_same_name():
    assert [rating_for(grade) for grade in (Grade.AGAIN, Grade.HARD, Grade.GOOD, Grade.EASY)] == [
        Rating.Again,
        Rating.Hard,
        Rating.Good,
        Rating.Easy,
    ]


@pytest.mark.parametrize(
    ("phase", "state"),
    [
        (ReviewPhase.LEARNING, State.Learning),
        (ReviewPhase.REVIEW, State.Review),
        (ReviewPhase.RELEARNING, State.Relearning),
    ],
)
def test_review_state_and_fsrs_card_convert_both_ways_without_loss(phase, state):
    review_state = ReviewState(
        task_id=uuid4(),
        due=NOW + timedelta(days=3),
        phase=phase,
        step=None if phase is ReviewPhase.REVIEW else 1,
        stability=3.17,
        difficulty=5.28,
        last_review=NOW,
    )

    card = to_card(review_state)

    assert (card.state, card.step, card.stability, card.difficulty) == (
        state,
        review_state.step,
        3.17,
        5.28,
    )
    assert (card.due, card.last_review) == (review_state.due, NOW)
    assert from_card(review_state.task_id, card) == review_state


def test_a_fresh_fsrs_card_becomes_a_fresh_review_state():
    task_id = uuid4()
    state = from_card(task_id, Card(due=NOW))
    assert state == ReviewState(task_id=task_id, due=NOW)


# --- scheduling --------------------------------------------------------------


def test_the_first_attempt_creates_the_review_state():
    task_id = uuid4()
    state = review(None, task_id, Grade.GOOD, NOW)
    assert state.task_id == task_id
    assert state.last_review == NOW
    assert state.due > NOW
    assert state.stability is not None and state.difficulty is not None


def test_the_better_the_grade_the_later_the_task_comes_back():
    due = [review(None, uuid4(), grade, NOW).due for grade in Grade]
    assert due == sorted(due)
    assert len(set(due)) == 4


def test_a_failed_task_comes_back_within_minutes_and_an_easy_one_after_days():
    assert review(None, uuid4(), Grade.AGAIN, NOW).due - NOW <= timedelta(minutes=5)
    assert review(None, uuid4(), Grade.EASY, NOW).due - NOW >= timedelta(days=2)


def test_a_failed_task_is_harder_and_less_stable_than_one_that_went_well():
    failed = review(None, uuid4(), Grade.AGAIN, NOW)
    passed = review(None, uuid4(), Grade.GOOD, NOW)
    assert failed.difficulty > passed.difficulty
    assert failed.stability < passed.stability


def test_repeated_success_moves_a_task_into_review_with_growing_intervals():
    learning = after(Grade.GOOD)
    assert learning.phase is ReviewPhase.LEARNING

    reviewed = [after(*[Grade.GOOD] * times) for times in (2, 3, 4)]
    assert all(state.phase is ReviewPhase.REVIEW and state.step is None for state in reviewed)
    intervals = [state.due - state.last_review for state in reviewed]
    assert intervals == sorted(intervals)
    assert intervals[0] >= timedelta(days=1)
    assert intervals[-1] > intervals[0]


def test_failing_a_task_under_review_sends_it_back_for_relearning():
    reviewed = after(Grade.GOOD, Grade.GOOD, Grade.GOOD)
    lapsed = review(reviewed, reviewed.task_id, Grade.AGAIN, reviewed.due)

    assert lapsed.phase is ReviewPhase.RELEARNING
    assert lapsed.due - lapsed.last_review < timedelta(hours=1)
    assert lapsed.stability < reviewed.stability
    assert lapsed.difficulty > reviewed.difficulty


def test_scheduling_is_reproducible():
    task_id = uuid4()
    first = review(None, task_id, Grade.GOOD, NOW)
    second = review(None, task_id, Grade.GOOD, NOW)
    assert first == second


def test_the_result_matches_what_fsrs_computes_directly():
    scheduler = Scheduler(enable_fuzzing=False)
    card, _ = scheduler.review_card(Card(due=NOW), Rating.Hard, review_datetime=NOW)
    card, _ = scheduler.review_card(card, Rating.Good, review_datetime=card.due)

    state = after(Grade.HARD, Grade.GOOD)

    assert (state.due, state.stability, state.difficulty) == (
        card.due,
        card.stability,
        card.difficulty,
    )
    assert state.phase.value == card.state.name.lower()


def test_review_time_must_be_timezone_aware():
    with pytest.raises(ValueError):
        review(None, uuid4(), Grade.GOOD, datetime(2026, 11, 12))
