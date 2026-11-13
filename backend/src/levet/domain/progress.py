"""Progress over time: the practice streak and how mastery has developed. Pure."""

from collections.abc import Collection, Sequence
from datetime import date, datetime, time, timedelta, tzinfo

from levet.domain.attempt import Attempt
from levet.domain.scoring import DEFAULT_SCORING, ScoringConfig, mastery


def practice_days(attempts: Sequence[Attempt], zone: tzinfo) -> set[date]:
    """The calendar days, in the given time zone, on which something was attempted."""
    return {attempt.attempted_at.astimezone(zone).date() for attempt in attempts}


def streak(days: Collection[date], today: date) -> int:
    """How many days in a row were practised, up to today.

    A streak is still alive on a day that has not been practised yet: it then
    counts up to yesterday. It is broken once a whole day has been missed.
    """
    day = today if today in days else today - timedelta(days=1)
    length = 0
    while day in days:
        length += 1
        day -= timedelta(days=1)
    return length


def mastery_history(
    attempts: Sequence[Attempt],
    now: datetime,
    zone: tzinfo,
    max_days: int = 60,
    config: ScoringConfig = DEFAULT_SCORING,
) -> list[tuple[date, float]]:
    """Mastery at the end of each day from the first attempt until today.

    At most the last ``max_days`` days are returned. Today's value is the
    mastery right now. Empty if nothing has been attempted.
    """
    past = [attempt for attempt in attempts if attempt.attempted_at <= now]
    if not past:
        return []
    today = now.astimezone(zone).date()
    first = min(attempt.attempted_at for attempt in past).astimezone(zone).date()
    start = max(first, today - timedelta(days=max_days - 1))

    history: list[tuple[date, float]] = []
    day = start
    while day <= today:
        end_of_day = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
        value = mastery(past, min(end_of_day, now), config)
        if value is not None:
            history.append((day, value))
        day += timedelta(days=1)
    return history
