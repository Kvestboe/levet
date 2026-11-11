from datetime import date, datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel

from levet.application.exams import ExamView
from levet.domain import ExamStatus, Subject


class LoginIn(BaseModel):
    password: str


class SessionOut(BaseModel):
    authenticated: bool


class SubjectIn(BaseModel):
    code: str
    name: str
    exam_date: date | None = None


class SubjectUpdate(BaseModel):
    name: str
    exam_date: date | None = None


class SubjectOut(BaseModel):
    code: str
    name: str
    exam_date: date | None

    @classmethod
    def of(cls, subject: Subject) -> Self:
        return cls(code=subject.code, name=subject.name, exam_date=subject.exam_date)


class ProgressOut(BaseModel):
    stage: str
    done: int
    total: int


class ExamOut(BaseModel):
    id: UUID
    subject_code: str
    label: str
    status: ExamStatus
    error: str | None
    has_solution: bool
    page_count: int | None
    solution_page_count: int | None
    uploaded_at: datetime
    progress: ProgressOut | None

    @classmethod
    def of(cls, view: ExamView) -> Self:
        exam, progress = view.exam, view.progress
        return cls(
            id=exam.id,
            subject_code=exam.subject_code,
            label=exam.label,
            status=exam.status,
            error=exam.error,
            has_solution=exam.solution_pdf_key is not None,
            page_count=exam.page_count,
            solution_page_count=exam.solution_page_count,
            uploaded_at=exam.uploaded_at,
            progress=(
                None
                if progress is None
                else ProgressOut(stage=progress.stage, done=progress.done, total=progress.total)
            ),
        )
