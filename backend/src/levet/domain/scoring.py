"""Topic weakness scoring.

    weakness = 0.60 * (1 - mastery) + 0.25 * staleness + 0.15 * coverage_gap
    priority = weakness * subject_urgency

Every term is in [0, 1], so weakness and priority are too. All functions are
pure and score "as of" the ``now`` they are given: attempts logged after ``now``
are ignored, which is what makes mastery-over-time charts possible.
"""

import math
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from levet.domain.attempt import Attempt

_SECONDS_PER_DAY = 86_400.0


@dataclass(frozen=True, slots=True, kw_only=True)
class ScoringConfig:
    """Tunable constants of the weakness formula.

    The three weights are relative: they are divided by their sum, so weakness
    stays in [0, 1] whatever values are configured.
    """

    mastery_weight: float = 0.60
    staleness_weight: float = 0.25
    coverage_weight: float = 0.15

    # An attempt this old counts half as much towards mastery as one made now,
    # and a topic left alone this long is half-way to fully stale.
    half_life_days: float = 7.0

    # Urgency is 1.0 on exam day, halves its distance to the floor every
    # ``urgency_half_life_days`` further out, and never drops below the floor.
    urgency_half_life_days: float = 14.0
    urgency_floor: float = 0.2

    def __post_init__(self) -> None:
        weights = (self.mastery_weight, self.staleness_weight, self.coverage_weight)
        if any(not math.isfinite(w) or w < 0 for w in weights):
            raise ValueError("scoring weights must be non-negative numbers")
        if sum(weights) <= 0:
            raise ValueError("at least one scoring weight must be positive")
        for name in ("half_life_days", "urgency_half_life_days"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive")
        if not 0.0 <= self.urgency_floor <= 1.0:
            raise ValueError("urgency_floor must be between 0 and 1")


DEFAULT_SCORING = ScoringConfig()


@dataclass(frozen=True, slots=True)
class TopicWeakness:
    """Weakness of one topic, with the terms it was built from.

    ``mastery`` is None for a topic that has never been attempted.
    """

    mastery: float | None
    staleness: float
    coverage_gap: float
    weakness: float


def mastery(
    attempts: Iterable[Attempt],
    now: datetime,
    config: ScoringConfig = DEFAULT_SCORING,
) -> float | None:
    """Recency-weighted mean score of ``attempts``, or None if there are none.

    Each attempt is weighted by ``0.5 ** (age / half_life)``.
    """
    _require_aware(now)
    scored = [
        (_age_days(attempt.attempted_at, now), attempt.score)
        for attempt in attempts
        if attempt.attempted_at <= now
    ]
    if not scored:
        return None

    # Ages are measured from the newest attempt rather than from ``now``. The
    # weighted mean is identical, but the weights cannot all underflow to zero
    # when every attempt is very old.
    newest = min(age for age, _ in scored)
    weight_sum = 0.0
    score_sum = 0.0
    for age, score in scored:
        weight = _decay(age - newest, config.half_life_days)
        weight_sum += weight
        score_sum += weight * score
    return score_sum / weight_sum


def staleness(
    last_attempt_at: datetime | None,
    now: datetime,
    config: ScoringConfig = DEFAULT_SCORING,
) -> float:
    """How long the topic has been left alone: 0 right after practice, approaching 1.

    Never practised counts as fully stale.
    """
    _require_aware(now)
    if last_attempt_at is None:
        return 1.0
    age = max(0.0, _age_days(last_attempt_at, now))
    return 1.0 - _decay(age, config.half_life_days)


def coverage_gap(task_ids: Collection[UUID], attempted_task_ids: Collection[UUID]) -> float:
    """Fraction of the topic's tasks that have never been attempted."""
    tasks = frozenset(task_ids)
    if not tasks:
        return 1.0
    return 1.0 - len(tasks & frozenset(attempted_task_ids)) / len(tasks)


def topic_weakness(
    task_ids: Collection[UUID],
    attempts: Iterable[Attempt],
    now: datetime,
    config: ScoringConfig = DEFAULT_SCORING,
) -> TopicWeakness:
    """Weakness of a topic in [0, 1]; 1.0 for a topic that has never been attempted.

    ``task_ids`` are the practisable tasks tagged with the topic. ``attempts``
    may contain attempts at other tasks; those are ignored.
    """
    _require_aware(now)
    tasks = frozenset(task_ids)
    relevant = [a for a in attempts if a.task_id in tasks and a.attempted_at <= now]

    topic_mastery = mastery(relevant, now, config)
    topic_staleness = staleness(max((a.attempted_at for a in relevant), default=None), now, config)
    topic_gap = coverage_gap(tasks, {a.task_id for a in relevant})

    weighted = (
        config.mastery_weight * (1.0 - (0.0 if topic_mastery is None else topic_mastery))
        + config.staleness_weight * topic_staleness
        + config.coverage_weight * topic_gap
    )
    total_weight = config.mastery_weight + config.staleness_weight + config.coverage_weight
    return TopicWeakness(
        mastery=topic_mastery,
        staleness=topic_staleness,
        coverage_gap=topic_gap,
        weakness=_clamp(weighted / total_weight),
    )


def subject_urgency(
    exam_date: date | None,
    today: date,
    config: ScoringConfig = DEFAULT_SCORING,
) -> float:
    """Multiplier in [urgency_floor, 1]: the closer the exam, the higher.

    A subject with no exam date, or whose exam has passed, sits at the floor.
    """
    if exam_date is None:
        return config.urgency_floor
    days_left = (exam_date - today).days
    if days_left < 0:
        return config.urgency_floor
    closeness = _decay(days_left, config.urgency_half_life_days)
    return config.urgency_floor + (1.0 - config.urgency_floor) * closeness


def topic_priority(weakness: float, urgency: float) -> float:
    """What topics are ranked by across subjects: weakness scaled by subject urgency."""
    return _clamp(weakness * urgency)


def _decay(age_days: float, half_life_days: float) -> float:
    return 0.5 ** (age_days / half_life_days)


def _age_days(then: datetime, now: datetime) -> float:
    return (now - then).total_seconds() / _SECONDS_PER_DAY


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _require_aware(now: datetime) -> None:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
