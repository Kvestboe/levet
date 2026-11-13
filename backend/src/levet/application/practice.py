"""Practising: what comes next, logging attempts, and progress per topic.

Only tasks of approved (``ready``) exams take part, and only tasks without
sub-tasks are practised; a task with sub-tasks is the context of its parts.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Self
from uuid import UUID

from levet.application.errors import Conflict, InvalidInput, NotFound
from levet.application.ports import Clock, UnitOfWork, UnitOfWorkFactory
from levet.domain import Attempt, Exam, ExamStatus, Grade, ReviewState, Task, Topic
from levet.domain.practice import Candidate, Reason, TopicScore, build_queue, score_topics
from levet.domain.scheduling import review
from levet.domain.scoring import DEFAULT_SCORING, ScoringConfig


@dataclass(frozen=True, slots=True)
class PracticeTask:
    """A task with everything needed to show and practise it."""

    task: Task
    exam: Exam
    # The task this one is a part of, whose content is the shared context.
    parent: Task | None
    # The whole top-level task in document order: the parent and all its parts.
    group: tuple[Task, ...]
    # The task whose solution to show: this one, or its parent if only that has one.
    solution: Task | None
    topics: tuple[Topic, ...]
    attempt_count: int
    last_grade: Grade | None
    due: datetime | None


@dataclass(frozen=True, slots=True)
class QueueEntry:
    practice: PracticeTask
    reason: Reason
    topic: Topic | None


@dataclass(frozen=True, slots=True)
class PracticeQueue:
    entries: tuple[QueueEntry, ...]  # the head of the queue
    total: int  # how many tasks the whole queue holds
    due_count: int  # how many of them are failed tasks that are due again


@dataclass(frozen=True, slots=True)
class TopicProgress:
    topic: Topic
    score: TopicScore


@dataclass(frozen=True, slots=True)
class AttemptResult:
    attempt: Attempt
    state: ReviewState


class PracticeService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        scoring: Callable[[], ScoringConfig] = lambda: DEFAULT_SCORING,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        # Asked for on every use, so a change in the settings applies at once.
        self._scoring = scoring

    def queue(self, topic_id: UUID | None = None, limit: int = 10) -> PracticeQueue:
        """What to practise now, best first; limited to one topic if ``topic_id`` is given."""
        now = self._clock()
        with self._uow_factory() as uow:
            world = PracticeData.load(uow)
        if topic_id is not None and topic_id not in world.topics:
            raise NotFound("no such topic")

        items = build_queue(
            world.candidates,
            world.attempts,
            world.states,
            world.exam_dates,
            now,
            self._scoring(),
            topic_id,
        )
        return PracticeQueue(
            entries=tuple(
                QueueEntry(
                    practice=world.practice_task(item.task_id),
                    reason=item.reason,
                    topic=world.topics.get(item.topic_id) if item.topic_id else None,
                )
                for item in items[: max(0, limit)]
            ),
            total=len(items),
            due_count=sum(1 for item in items if item.reason is Reason.DUE),
        )

    def topics(self) -> list[TopicProgress]:
        """Every topic that has tasks to practise, weakest and most urgent first."""
        now = self._clock()
        with self._uow_factory() as uow:
            world = PracticeData.load(uow)
        scores = score_topics(
            world.candidates, world.attempts, world.exam_dates, now, self._scoring()
        )
        progress = [TopicProgress(world.topics[i], score) for i, score in scores.items()]
        return sorted(progress, key=lambda p: (-p.score.priority, p.topic.name.casefold()))

    def exam_tasks(self, exam_id: UUID) -> list[PracticeTask]:
        """The tasks of one approved exam in document order, for a mock exam."""
        with self._uow_factory() as uow:
            exam = uow.exams.get(exam_id)
            if exam is None:
                raise NotFound("no such exam")
            if exam.status is not ExamStatus.READY:
                raise Conflict("only an approved exam can be practised")
            world = PracticeData.load(uow)
        return [
            world.practice_task(candidate.task_id)
            for candidate in world.candidates
            if world.tasks[candidate.task_id].exam_id == exam_id
        ]

    def record_attempt(
        self,
        task_id: UUID,
        grade: Grade,
        time_spent: timedelta | None = None,
        answer: str | None = None,
        note: str | None = None,
    ) -> AttemptResult:
        """Log one attempt and reschedule the task. Attempts are never changed afterwards."""
        now = self._clock()
        with self._uow_factory() as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                raise NotFound("no such task")
            exam = uow.exams.get(task.exam_id)
            if exam is None or exam.status is not ExamStatus.READY:
                raise Conflict("only tasks of an approved exam can be practised")
            if any(other.parent_id == task.id for other in uow.tasks.list_by_exam(exam.id)):
                raise Conflict("this task has sub-tasks; practise those instead")
            try:
                attempt = Attempt(
                    task_id=task_id,
                    attempted_at=now,
                    grade=grade,
                    time_spent=time_spent,
                    answer=(answer or "").strip() or None,
                    note=(note or "").strip() or None,
                )
            except ValueError as exc:
                raise InvalidInput(str(exc)) from exc
            state = review(uow.review_states.get(task_id), task_id, attempt.grade, now)
            uow.attempts.add(attempt)
            uow.review_states.save(state)
            uow.commit()
        return AttemptResult(attempt, state)


@dataclass(frozen=True, slots=True)
class PracticeData:
    """Everything the practice and progress logic looks at, read in one go:
    the approved exams, their tasks, and what has been attempted."""

    exams: dict[UUID, Exam]
    tasks: dict[UUID, Task]
    by_exam: dict[UUID, tuple[Task, ...]]
    candidates: tuple[Candidate, ...]
    attempts: tuple[Attempt, ...]
    states: dict[UUID, ReviewState]
    topics: dict[UUID, Topic]
    exam_dates: dict[str, date | None]

    @classmethod
    def load(cls, uow: UnitOfWork) -> Self:
        exams = {exam.id: exam for exam in uow.exams.list_by_status(ExamStatus.READY)}
        task_list = uow.tasks.list_by_exam_status(ExamStatus.READY)
        tasks = {task.id: task for task in task_list}
        by_exam: dict[UUID, list[Task]] = {}
        for task in task_list:
            by_exam.setdefault(task.exam_id, []).append(task)

        parents = {task.parent_id for task in task_list if task.parent_id is not None}
        candidates = tuple(
            Candidate(
                task_id=task.id,
                subject_code=exams[task.exam_id].subject_code,
                topic_ids=task.topic_ids,
                order=(exams[task.exam_id].uploaded_at, str(task.exam_id), task.position),
            )
            for task in task_list
            if task.id not in parents
        )
        practisable = {candidate.task_id for candidate in candidates}

        subjects = uow.subjects.list_all()
        topics = {
            topic.id: topic
            for subject in subjects
            for topic in uow.topics.list_by_subject(subject.code)
        }
        return cls(
            exams=exams,
            tasks=tasks,
            by_exam={exam_id: tuple(group) for exam_id, group in by_exam.items()},
            candidates=candidates,
            attempts=tuple(a for a in uow.attempts.list_all() if a.task_id in practisable),
            states={
                state.task_id: state
                for state in uow.review_states.list_all()
                if state.task_id in practisable
            },
            topics=topics,
            exam_dates={subject.code: subject.exam_date for subject in subjects},
        )

    def practice_task(self, task_id: UUID) -> PracticeTask:
        task = self.tasks[task_id]
        parent = self.tasks.get(task.parent_id) if task.parent_id else None
        root = parent or task
        group = tuple(
            other
            for other in self.by_exam[task.exam_id]
            if other.id == root.id or other.parent_id == root.id
        )
        mine = [attempt for attempt in self.attempts if attempt.task_id == task_id]
        state = self.states.get(task_id)
        return PracticeTask(
            task=task,
            exam=self.exams[task.exam_id],
            parent=parent,
            group=group,
            solution=_solution_source(task, parent),
            topics=tuple(
                sorted(
                    (self.topics[i] for i in task.topic_ids if i in self.topics),
                    key=lambda topic: topic.name.casefold(),
                )
            ),
            attempt_count=len(mine),
            last_grade=mine[-1].grade if mine else None,
            due=state.due if state else None,
        )


def _solution_source(task: Task, parent: Task | None) -> Task | None:
    for candidate in (task, parent):
        if candidate is not None and candidate.has_solution:
            return candidate
    return None
