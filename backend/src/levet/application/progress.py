"""How practice is going: the dashboard, and one topic in detail."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, tzinfo
from uuid import UUID

from levet.application.errors import NotFound
from levet.application.ports import Clock, UnitOfWorkFactory
from levet.application.practice import PracticeData, PracticeTask, TopicProgress
from levet.domain import Attempt, Exam, Subject, Task
from levet.domain.practice import Reason, build_queue, score_topics
from levet.domain.progress import mastery_history, practice_days, streak
from levet.domain.scoring import DEFAULT_SCORING, ScoringConfig

WEAKEST_TOPICS_SHOWN = 5


@dataclass(frozen=True, slots=True)
class Dashboard:
    subjects: tuple[Subject, ...]  # nearest exam first
    weakest_topics: tuple[TopicProgress, ...]
    due_count: int  # failed tasks that are due again
    task_count: int  # tasks that can be practised
    attempted_count: int  # of which have been attempted at least once
    streak_days: int
    attempts_today: int


@dataclass(frozen=True, slots=True)
class LoggedAttempt:
    attempt: Attempt
    task: Task
    exam: Exam


@dataclass(frozen=True, slots=True)
class TopicDetail:
    progress: TopicProgress
    history: tuple[tuple[date, float], ...]  # mastery at the end of each day
    tasks: tuple[PracticeTask, ...]  # in document order
    attempts: tuple[LoggedAttempt, ...]  # newest first


class ProgressService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        scoring: Callable[[], ScoringConfig] = lambda: DEFAULT_SCORING,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._scoring = scoring

    def dashboard(self, zone: tzinfo) -> Dashboard:
        """The overview. ``zone`` is the user's time zone: it decides what "today" is."""
        now = self._clock()
        scoring = self._scoring()
        with self._uow_factory() as uow:
            data = PracticeData.load(uow)
            subjects = uow.subjects.list_all()

        scores = score_topics(data.candidates, data.attempts, data.exam_dates, now, scoring)
        weakest = sorted(
            (TopicProgress(data.topics[topic_id], score) for topic_id, score in scores.items()),
            key=lambda p: (-p.score.priority, p.topic.name.casefold()),
        )
        queue = build_queue(
            data.candidates, data.attempts, data.states, data.exam_dates, now, scoring
        )
        today = now.astimezone(zone).date()
        days = practice_days(data.attempts, zone)
        return Dashboard(
            subjects=tuple(
                sorted(
                    subjects, key=lambda s: (s.exam_date is None, s.exam_date or date.max, s.code)
                )
            ),
            weakest_topics=tuple(weakest[:WEAKEST_TOPICS_SHOWN]),
            due_count=sum(1 for item in queue if item.reason is Reason.DUE),
            task_count=len(data.candidates),
            attempted_count=len({attempt.task_id for attempt in data.attempts}),
            streak_days=streak(days, today),
            attempts_today=sum(
                1
                for attempt in data.attempts
                if attempt.attempted_at.astimezone(zone).date() == today
            ),
        )

    def topic(self, topic_id: UUID, zone: tzinfo) -> TopicDetail:
        """One topic: its score, mastery day by day, its tasks and every attempt at them."""
        now = self._clock()
        scoring = self._scoring()
        with self._uow_factory() as uow:
            data = PracticeData.load(uow)

        scores = score_topics(data.candidates, data.attempts, data.exam_dates, now, scoring)
        if topic_id not in data.topics or topic_id not in scores:
            # Unknown, or without any task that can be practised yet.
            raise NotFound("no such topic")

        task_ids = {c.task_id for c in data.candidates if topic_id in c.topic_ids}
        attempts = [attempt for attempt in data.attempts if attempt.task_id in task_ids]
        return TopicDetail(
            progress=TopicProgress(data.topics[topic_id], scores[topic_id]),
            history=tuple(mastery_history(attempts, now, zone, config=scoring)),
            tasks=tuple(
                data.practice_task(c.task_id) for c in data.candidates if c.task_id in task_ids
            ),
            attempts=tuple(
                LoggedAttempt(
                    attempt=attempt,
                    task=data.tasks[attempt.task_id],
                    exam=data.exams[data.tasks[attempt.task_id].exam_id],
                )
                for attempt in reversed(attempts)
            ),
        )
