"""What to practise next. Pure functions over tasks, attempts and review states.

The queue mixes two things:

* tasks that were failed at some point and are due again according to FSRS,
  most overdue first;
* tasks from the weakest topics (weakness scaled by how close the subject's
  exam is), never-attempted tasks before attempted ones.

They alternate, so a backlog of failed tasks does not push new material out
and new material does not push failed tasks back. Tasks that were attempted
and are not due yet come last: they are only reached when nothing else is left.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID

from levet.domain.attempt import Attempt, Grade
from levet.domain.review import ReviewState
from levet.domain.scoring import (
    DEFAULT_SCORING,
    ScoringConfig,
    TopicWeakness,
    subject_urgency,
    topic_priority,
    topic_weakness,
)

_EPOCH = datetime.min.replace(tzinfo=UTC)


class Reason(StrEnum):
    """Why a task is in the queue."""

    DUE = "due"  # failed before, and due again
    NEW = "new"  # never attempted, from a weak topic
    WEAK = "weak"  # attempted before, from a weak topic


@dataclass(frozen=True, slots=True)
class Candidate:
    """A task that can be practised, as far as the queue needs to know it."""

    task_id: UUID
    subject_code: str
    topic_ids: frozenset[UUID] = frozenset()
    # Breaks ties so the order is stable: tasks come in document order.
    order: tuple = ()


@dataclass(frozen=True, slots=True)
class TopicScore:
    topic_id: UUID
    subject_code: str
    weakness: TopicWeakness
    urgency: float
    priority: float
    task_count: int
    attempted_count: int


@dataclass(frozen=True, slots=True)
class QueueItem:
    task_id: UUID
    reason: Reason
    # The topic that earned the task its place; None for a task without topics.
    topic_id: UUID | None = None


def score_topics(
    candidates: Sequence[Candidate],
    attempts: Sequence[Attempt],
    exam_dates: Mapping[str, date | None],
    now: datetime,
    config: ScoringConfig = DEFAULT_SCORING,
) -> dict[UUID, TopicScore]:
    """Weakness and priority of every topic that has at least one practisable task."""
    tasks_by_topic: dict[UUID, set[UUID]] = defaultdict(set)
    subject_of: dict[UUID, str] = {}
    for candidate in candidates:
        for topic_id in candidate.topic_ids:
            tasks_by_topic[topic_id].add(candidate.task_id)
            subject_of.setdefault(topic_id, candidate.subject_code)

    attempted = {attempt.task_id for attempt in attempts if attempt.attempted_at <= now}
    today = now.date()
    scores: dict[UUID, TopicScore] = {}
    for topic_id, task_ids in tasks_by_topic.items():
        subject_code = subject_of[topic_id]
        weakness = topic_weakness(task_ids, attempts, now, config)
        urgency = subject_urgency(exam_dates.get(subject_code), today, config)
        scores[topic_id] = TopicScore(
            topic_id=topic_id,
            subject_code=subject_code,
            weakness=weakness,
            urgency=urgency,
            priority=topic_priority(weakness.weakness, urgency),
            task_count=len(task_ids),
            attempted_count=len(task_ids & attempted),
        )
    return scores


def build_queue(
    candidates: Sequence[Candidate],
    attempts: Sequence[Attempt],
    states: Mapping[UUID, ReviewState],
    exam_dates: Mapping[str, date | None],
    now: datetime,
    config: ScoringConfig = DEFAULT_SCORING,
    topic_id: UUID | None = None,
) -> list[QueueItem]:
    """Every practisable task, in the order to practise them.

    With ``topic_id`` the queue is limited to that topic's tasks; topics are
    still scored over all tasks, so the order within the topic is the same as
    in the full queue.
    """
    scores = score_topics(candidates, attempts, exam_dates, now, config)
    failed = {attempt.task_id for attempt in attempts if attempt.grade is Grade.AGAIN}
    last_attempt: dict[UUID, datetime] = {}
    for attempt in attempts:
        if attempt.attempted_at > last_attempt.get(attempt.task_id, _EPOCH):
            last_attempt[attempt.task_id] = attempt.attempted_at

    pool = [c for c in candidates if topic_id is None or topic_id in c.topic_ids]

    def is_due(candidate: Candidate) -> bool:
        state = states.get(candidate.task_id)
        return state is None or state.is_due(now)

    def weakest_topic(candidate: Candidate) -> UUID | None:
        if topic_id is not None:
            return topic_id
        return max(
            candidate.topic_ids,
            key=lambda topic: (scores[topic].priority, str(topic)),
            default=None,
        )

    def priority(candidate: Candidate) -> float:
        topic = weakest_topic(candidate)
        return 0.0 if topic is None else scores[topic].priority

    def item(candidate: Candidate, reason: Reason) -> QueueItem:
        return QueueItem(candidate.task_id, reason, weakest_topic(candidate))

    due_again = sorted(
        (c for c in pool if c.task_id in failed and c.task_id in states and is_due(c)),
        key=lambda c: (states[c.task_id].due, c.order),
    )
    taken = {c.task_id for c in due_again}

    fresh: list[Candidate] = []
    resting: list[Candidate] = []
    for candidate in pool:
        if candidate.task_id in taken:
            continue
        attempted = candidate.task_id in last_attempt
        (resting if attempted and not is_due(candidate) else fresh).append(candidate)

    def by_weakness(candidate: Candidate) -> tuple:
        return (
            -priority(candidate),
            candidate.task_id in last_attempt,  # never attempted first
            last_attempt.get(candidate.task_id, _EPOCH),  # then the longest untouched
            candidate.order,
        )

    fresh.sort(key=by_weakness)
    resting.sort(key=by_weakness)

    def weak_item(candidate: Candidate) -> QueueItem:
        reason = Reason.WEAK if candidate.task_id in last_attempt else Reason.NEW
        return item(candidate, reason)

    queue: list[QueueItem] = []
    for index in range(max(len(due_again), len(fresh))):
        if index < len(due_again):
            queue.append(item(due_again[index], Reason.DUE))
        if index < len(fresh):
            queue.append(weak_item(fresh[index]))
    queue.extend(weak_item(candidate) for candidate in resting)
    return queue
