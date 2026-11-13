from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from levet.adapters.http.deps import ContainerDep
from levet.adapters.http.schemas import (
    AttemptIn,
    AttemptOut,
    PracticeQueueOut,
    PracticeTaskOut,
    TopicProgressOut,
)

router = APIRouter(prefix="/practice", tags=["practice"])


@router.get("/queue")
def queue(
    container: ContainerDep,
    topic_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> PracticeQueueOut:
    """What to practise now, best first. With ``topic_id``, only that topic's tasks."""
    return PracticeQueueOut.of(container.practice.queue(topic_id, limit))


@router.get("/topics")
def topics(container: ContainerDep) -> list[TopicProgressOut]:
    """Every topic with tasks to practise, weakest and most urgent first."""
    return [TopicProgressOut.of(progress) for progress in container.practice.topics()]


@router.get("/exams/{exam_id}/tasks")
def exam_tasks(exam_id: UUID, container: ContainerDep) -> list[PracticeTaskOut]:
    """The tasks of one approved exam in document order, for a mock exam."""
    return [PracticeTaskOut.of(task) for task in container.practice.exam_tasks(exam_id)]


@router.post("/attempts", status_code=201)
def record_attempt(body: AttemptIn, container: ContainerDep) -> AttemptOut:
    spent = body.time_spent_seconds
    result = container.practice.record_attempt(
        body.task_id,
        body.grade,
        time_spent=None if spent is None else timedelta(seconds=spent),
        answer=body.answer,
        note=body.note,
    )
    return AttemptOut.of(result)
