"""Spaced repetition of tasks with FSRS.

The ``fsrs`` package does the arithmetic; this module translates between its
cards and ratings and the domain's review states and grades. Pure: the time
of a review is always passed in.
"""

from datetime import datetime
from uuid import UUID

from fsrs import Card, Rating, Scheduler, State

from levet.domain.attempt import Grade
from levet.domain.review import ReviewPhase, ReviewState

_RATINGS = {
    Grade.AGAIN: Rating.Again,
    Grade.HARD: Rating.Hard,
    Grade.GOOD: Rating.Good,
    Grade.EASY: Rating.Easy,
}

_PHASES = {
    State.Learning: ReviewPhase.LEARNING,
    State.Review: ReviewPhase.REVIEW,
    State.Relearning: ReviewPhase.RELEARNING,
}
_STATES = {phase: state for state, phase in _PHASES.items()}

# Fuzzing spreads due dates out at random so that cards learnt together do not
# all come back on the same day. With a few hundred tasks that is not a
# problem worth solving, and without it the schedule is reproducible.
DEFAULT_SCHEDULER = Scheduler(enable_fuzzing=False)


def rating_for(grade: Grade) -> Rating:
    return _RATINGS[grade]


def review(
    state: ReviewState | None,
    task_id: UUID,
    grade: Grade,
    now: datetime,
    scheduler: Scheduler = DEFAULT_SCHEDULER,
) -> ReviewState:
    """The task's review state after it was attempted at ``now`` with ``grade``.

    ``state`` is None for a task that has never been attempted.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    card = Card(due=now) if state is None else to_card(state)
    reviewed, _ = scheduler.review_card(card, rating_for(grade), review_datetime=now)
    return from_card(task_id, reviewed)


def to_card(state: ReviewState) -> Card:
    return Card(
        state=_STATES[state.phase],
        step=state.step,
        stability=state.stability,
        difficulty=state.difficulty,
        due=state.due,
        last_review=state.last_review,
    )


def from_card(task_id: UUID, card: Card) -> ReviewState:
    return ReviewState(
        task_id=task_id,
        due=card.due,
        phase=_PHASES[card.state],
        step=card.step,
        stability=card.stability,
        difficulty=card.difficulty,
        last_review=card.last_review,
    )
