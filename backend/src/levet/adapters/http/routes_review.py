from uuid import UUID

from fastapi import APIRouter, Response

from levet.adapters.http.deps import ContainerDep
from levet.adapters.http.schemas import (
    ExamOut,
    ExamTasksOut,
    TaskSplit,
    TaskUpdate,
    TopicOut,
    TopicRename,
)
from levet.application.exams import ExamView

router = APIRouter(tags=["review"])


@router.get("/exams/{exam_id}/tasks")
def list_tasks(exam_id: UUID, container: ContainerDep) -> ExamTasksOut:
    """The exam's tasks in document order, and the subject's topics."""
    return ExamTasksOut.of(container.review.tasks(exam_id))


@router.get("/exams/{exam_id}/task-images/{name}")
def get_task_image(exam_id: UUID, name: str, container: ContainerDep) -> Response:
    return Response(
        content=container.review.task_image(exam_id, name),
        media_type="image/png",
        # A new image gets a new name, so this one never changes.
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@router.post("/exams/{exam_id}/approve")
def approve_exam(exam_id: UUID, container: ContainerDep) -> ExamOut:
    return ExamOut.of(ExamView(container.review.approve(exam_id)))


@router.get("/subjects/{code}/topics")
def list_topics(code: str, container: ContainerDep) -> list[TopicOut]:
    return [TopicOut.of(topic) for topic in container.review.topics(code)]


@router.patch("/topics/{topic_id}")
def rename_topic(topic_id: UUID, body: TopicRename, container: ContainerDep) -> TopicOut:
    """Rename a topic everywhere. Renaming it to another topic's name merges the two."""
    return TopicOut.of(container.review.rename_topic(topic_id, body.name))


@router.patch("/tasks/{task_id}", status_code=204)
def update_task(task_id: UUID, body: TaskUpdate, container: ContainerDep) -> None:
    sent = body.model_fields_set
    changes: dict[str, object] = {}
    if "title" in sent:
        changes["title"] = body.title
    if "points" in sent:
        changes["points"] = body.points
    container.review.update_task(task_id, number=body.number, topic_names=body.topics, **changes)


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: UUID, container: ContainerDep) -> None:
    container.review.delete_task(task_id)


@router.post("/tasks/{task_id}/merge-previous", status_code=204)
def merge_task(task_id: UUID, container: ContainerDep) -> None:
    container.review.merge_with_previous(task_id)


@router.post("/tasks/{task_id}/split", status_code=204)
def split_task(task_id: UUID, body: TaskSplit, container: ContainerDep) -> None:
    container.review.split_task(task_id, body.image_index, body.fraction)
