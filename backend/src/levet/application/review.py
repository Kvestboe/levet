"""Reviewing the tasks extracted from an exam before they enter practice."""

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from uuid import UUID

from levet.application import storage_keys
from levet.application.errors import Conflict, InvalidInput, NotFound
from levet.application.ingestion import find_topic, normalize_topic_name
from levet.application.ports import FileStore, PageRenderer, UnitOfWork, UnitOfWorkFactory
from levet.application.processing import render_regions
from levet.domain import MAX_TOPICS_PER_TASK, Exam, ExamStatus, Task, Topic

_UNSET = object()


@dataclass(frozen=True, slots=True)
class ExamTasks:
    """An exam's tasks in document order, with the subject's topics to name them by."""

    exam: Exam
    tasks: tuple[Task, ...]
    topics: tuple[Topic, ...]


class ReviewService:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, files: FileStore, renderer: PageRenderer
    ) -> None:
        self._uow_factory = uow_factory
        self._files = files
        self._renderer = renderer

    # --- reading -----------------------------------------------------------------

    def tasks(self, exam_id: UUID) -> ExamTasks:
        with self._uow_factory() as uow:
            exam = _exam(uow, exam_id)
            return ExamTasks(
                exam=exam,
                tasks=tuple(uow.tasks.list_by_exam(exam_id)),
                topics=tuple(uow.topics.list_by_subject(exam.subject_code)),
            )

    def topics(self, subject_code: str) -> list[Topic]:
        with self._uow_factory() as uow:
            return uow.topics.list_by_subject(subject_code.strip().upper())

    def task_image(self, exam_id: UUID, name: str) -> bytes:
        """PNG of one task or solution region, by the file name the task refers to."""
        if not re.fullmatch(r"[0-9a-f]{32}\.png", name):
            raise NotFound("no such image")
        try:
            return self._files.read(storage_keys.task_image(exam_id, name))
        except FileNotFoundError as exc:
            raise NotFound("no such image") from exc

    # --- editing -----------------------------------------------------------------

    def update_task(
        self,
        task_id: UUID,
        *,
        number: str | None = None,
        title: str | None | object = _UNSET,
        points: float | None | object = _UNSET,
        topic_names: Sequence[str] | None = None,
    ) -> Task:
        """Change a task's label, title, points or topics. Arguments left out are kept.

        Topics are given by name; names the subject does not have yet become
        new topics.
        """
        with self._uow_factory() as uow:
            task, exam = _task_under_review(uow, task_id)
            changes: dict[str, object] = {}
            if number is not None:
                changes["number"] = number
            if title is not _UNSET:
                changes["title"] = title
            if points is not _UNSET:
                changes["points"] = points
            if topic_names is not None:
                changes["topic_ids"] = _resolve_topics(uow, exam.subject_code, topic_names)
            try:
                task = replace(task, **changes)
            except ValueError as exc:
                raise InvalidInput(str(exc)) from exc
            uow.tasks.save(task)
            uow.topics.delete_unused(exam.subject_code)
            uow.commit()
        return task

    def delete_task(self, task_id: UUID) -> None:
        """Remove a task and its sub-tasks, with their images."""
        with self._uow_factory() as uow:
            task, exam = _task_under_review(uow, task_id)
            doomed = [task, *_descendants(task, uow.tasks.list_by_exam(exam.id))]
            for each in doomed:
                uow.tasks.delete(each.id)
            uow.topics.delete_unused(exam.subject_code)
            uow.commit()
        for each in doomed:
            for key in (*each.image_keys, *each.solution_image_keys):
                self._files.delete(key)

    def merge_with_previous(self, task_id: UUID) -> Task:
        """Append a task to the one before it in the document. Undoes a split
        the extraction made in the wrong place."""
        with self._uow_factory() as uow:
            task, exam = _task_under_review(uow, task_id)
            tasks = uow.tasks.list_by_exam(exam.id)
            if any(other.parent_id == task.id for other in tasks):
                raise Conflict("a task with sub-tasks cannot be merged; merge its sub-tasks first")
            index = next(i for i, other in enumerate(tasks) if other.id == task.id)
            if index == 0:
                raise Conflict("the first task has nothing before it to merge with")
            target = tasks[index - 1]

            merged = replace(
                target,
                text="\n".join(part for part in (target.text, task.text) if part),
                points=_sum(target.points, task.points),
                regions=target.regions + task.regions,
                image_keys=target.image_keys + task.image_keys,
                solution_text="\n\n".join(
                    part for part in (target.solution_text, task.solution_text) if part
                )
                or None,
                solution_regions=target.solution_regions + task.solution_regions,
                solution_image_keys=target.solution_image_keys + task.solution_image_keys,
            )
            uow.tasks.delete(task.id)
            uow.tasks.save(merged)
            uow.topics.delete_unused(exam.subject_code)
            uow.commit()
        return merged

    def split_task(self, task_id: UUID, image_index: int, fraction: float) -> tuple[Task, Task]:
        """Cut a task in two at a point in one of its images.

        ``fraction`` is how far down image ``image_index`` the cut goes (0-1).
        The part above stays with the task; the part below, and any images
        after it, becomes a new task right after it.
        """
        with self._uow_factory() as uow:
            task, exam = _task_under_review(uow, task_id)
            if not 0 <= image_index < len(task.regions):
                raise InvalidInput("the task has no such image")
            if not 0.02 <= fraction <= 0.98:
                raise InvalidInput("choose a point inside the image to split at")
            if len(task.regions) != len(task.image_keys):
                raise Conflict("the task's images are out of step with its regions")

            upper, lower = task.regions[image_index].split_at(fraction)
            pdf = self._files.read(exam.pdf_key)
            upper_regions, upper_keys = render_regions(
                self._renderer, self._files, exam.id, pdf, [upper]
            )
            lower_regions, lower_keys = render_regions(
                self._renderer, self._files, exam.id, pdf, [lower]
            )
            if not upper_regions or not lower_regions:
                for key in (*upper_keys, *lower_keys):
                    self._files.delete(key)
                raise InvalidInput("there is nothing on one side of that point")

            tasks = uow.tasks.list_by_exam(exam.id)
            is_parent = any(other.parent_id == task.id for other in tasks)
            first = replace(
                task,
                regions=task.regions[:image_index] + upper_regions,
                image_keys=task.image_keys[:image_index] + upper_keys,
            )
            second = Task(
                exam_id=task.exam_id,
                # Cut off a task that has sub-tasks, and the piece is one more sub-task.
                parent_id=task.id if is_parent else task.parent_id,
                number=_number_after(task.number, is_parent),
                topic_ids=frozenset() if is_parent else task.topic_ids,
                regions=lower_regions + task.regions[image_index + 1 :],
                image_keys=lower_keys + task.image_keys[image_index + 1 :],
            )
            replaced_image = task.image_keys[image_index]

            index = next(i for i, other in enumerate(tasks) if other.id == task.id)
            ordered = [*tasks[:index], first, second, *tasks[index + 1 :]]
            for position, each in enumerate(ordered):
                if each.position != position or each.id in (first.id, second.id):
                    uow.tasks.save(replace(each, position=position))
            uow.commit()
            first, second = replace(first, position=index), replace(second, position=index + 1)
        self._files.delete(replaced_image)
        return first, second

    def rename_topic(self, topic_id: UUID, name: str) -> Topic:
        """Give a topic a new name, on every task that has it.

        If the subject already has a topic by that name the two are merged: the
        tasks move over to the existing topic and this one is removed. Topics
        start out named after task titles, so this is how they are tidied up.
        """
        with self._uow_factory() as uow:
            topic = uow.topics.get(topic_id)
            if topic is None:
                raise NotFound("no such topic")
            try:
                renamed = replace(topic, name=" ".join(name.split()))
            except ValueError as exc:
                raise InvalidInput(str(exc)) from exc

            others = [t for t in uow.topics.list_by_subject(topic.subject_code) if t.id != topic.id]
            existing = find_topic(renamed.name, others)
            if existing is None:
                uow.topics.save(renamed)
                uow.commit()
                return renamed

            for task in uow.tasks.list_by_topic(topic.id):
                uow.tasks.save(
                    replace(task, topic_ids=(task.topic_ids - {topic.id}) | {existing.id})
                )
            uow.topics.delete(topic.id)
            uow.commit()
            return existing

    def approve(self, exam_id: UUID) -> Exam:
        """Finish the review: every remaining task enters practice.

        Each task that will be practised (one without sub-tasks) needs at least
        one topic, its own or its parent's.
        """
        with self._uow_factory() as uow:
            exam = _exam(uow, exam_id)
            if exam.status is not ExamStatus.NEEDS_REVIEW:
                raise Conflict(f"the exam is {exam.status.value}, not awaiting review")
            tasks = uow.tasks.list_by_exam(exam_id)
            if not tasks:
                raise Conflict("the exam has no tasks to approve")

            by_id = {task.id: task for task in tasks}
            parents = {task.parent_id for task in tasks if task.parent_id is not None}
            untagged: list[str] = []
            for task in tasks:
                if task.id in parents:
                    continue
                parent = by_id.get(task.parent_id) if task.parent_id else None
                if task.topic_ids:
                    continue
                if parent is not None and parent.topic_ids:
                    # Write the inherited topics down, so practice need not look them up.
                    uow.tasks.save(replace(task, topic_ids=parent.topic_ids))
                else:
                    untagged.append(task.number)
            if untagged:
                raise Conflict("these tasks have no topic yet: " + ", ".join(untagged))

            exam = exam.approve()
            uow.exams.save(exam)
            uow.topics.delete_unused(exam.subject_code)
            uow.commit()
        return exam


def _exam(uow: UnitOfWork, exam_id: UUID) -> Exam:
    exam = uow.exams.get(exam_id)
    if exam is None:
        raise NotFound("no such exam")
    return exam


def _task_under_review(uow: UnitOfWork, task_id: UUID) -> tuple[Task, Exam]:
    task = uow.tasks.get(task_id)
    if task is None:
        raise NotFound("no such task")
    exam = _exam(uow, task.exam_id)
    if exam.status is not ExamStatus.NEEDS_REVIEW:
        raise Conflict(
            f"tasks can only be changed while the exam awaits review; it is {exam.status.value}"
        )
    return task, exam


def _resolve_topics(uow: UnitOfWork, subject_code: str, names: Sequence[str]) -> frozenset[UUID]:
    # The same name spelled twice, in whatever case, is one topic.
    spellings: dict[str, str] = {}
    for name in names:
        if name.strip():
            spellings.setdefault(normalize_topic_name(name), " ".join(name.split()))
    wanted = list(spellings.values())
    if len(wanted) > MAX_TOPICS_PER_TASK:
        raise InvalidInput(f"a task can have at most {MAX_TOPICS_PER_TASK} topics")
    existing = uow.topics.list_by_subject(subject_code)
    ids: set[UUID] = set()
    for name in wanted:
        topic = find_topic(name, existing)
        if topic is None:
            try:
                topic = Topic(subject_code=subject_code, name=name)
            except ValueError as exc:
                raise InvalidInput(str(exc)) from exc
            uow.topics.save(topic)
            existing.append(topic)
        ids.add(topic.id)
    return frozenset(ids)


def _descendants(task: Task, tasks: Sequence[Task]) -> list[Task]:
    found: list[Task] = []
    frontier = {task.id}
    while frontier:
        children = [other for other in tasks if other.parent_id in frontier]
        found.extend(children)
        frontier = {child.id for child in children}
    return found


def _sum(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return a if b is None else b
    return a + b


def _number_after(number: str, as_first_subtask: bool) -> str:
    """A label for the piece split off a task: "3b" -> "3c", "3" -> "4"; the
    first sub-task of "3" is "3a". Only a suggestion; it can be edited."""
    if as_first_subtask:
        return f"{number}a"
    if number[-1:].isalpha() and number[-1].lower() != "z":
        return number[:-1] + chr(ord(number[-1]) + 1)
    if number.isdigit():
        return str(int(number) + 1)
    return f"{number}-2"
