"""File-store keys for everything that belongs to an exam.

Page images are addressed by exam, document and 1-based page number, so they
can be found from an exam's page count alone.
"""

from enum import StrEnum
from uuid import UUID


class PageKind(StrEnum):
    """Which of an exam's two documents a page comes from."""

    EXAM = "exam"
    SOLUTION = "solution"


def exam_pdf(exam_id: UUID) -> str:
    return f"exams/{exam_id}/exam.pdf"


def solution_pdf(exam_id: UUID) -> str:
    return f"exams/{exam_id}/solution.pdf"


def page_image(exam_id: UUID, kind: PageKind, number: int) -> str:
    return f"exams/{exam_id}/pages/{kind.value}-{number:03d}.png"


def task_images(exam_id: UUID) -> str:
    """Prefix under which the images of an exam's tasks and solutions are kept."""
    return f"exams/{exam_id}/task-images"


def task_image(exam_id: UUID, name: str) -> str:
    return f"{task_images(exam_id)}/{name}"
