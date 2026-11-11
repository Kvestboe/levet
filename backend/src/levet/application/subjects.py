from datetime import date

from levet.application.errors import Conflict, InvalidInput, NotFound
from levet.application.ports import UnitOfWorkFactory
from levet.domain import Subject
from levet.domain.subject import normalize_subject_code


class SubjectService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def list_all(self) -> list[Subject]:
        """All subjects, nearest exam first; subjects without an exam date last."""
        with self._uow_factory() as uow:
            subjects = uow.subjects.list_all()
        return sorted(
            subjects, key=lambda s: (s.exam_date is None, s.exam_date or date.max, s.code)
        )

    def create(self, code: str, name: str, exam_date: date | None = None) -> Subject:
        subject = _build(code, name, exam_date)
        with self._uow_factory() as uow:
            if uow.subjects.get(subject.code) is not None:
                raise Conflict(f"subject {subject.code} already exists")
            uow.subjects.save(subject)
            uow.commit()
        return subject

    def update(self, code: str, name: str, exam_date: date | None) -> Subject:
        subject = _build(code, name, exam_date)
        with self._uow_factory() as uow:
            if uow.subjects.get(subject.code) is None:
                raise NotFound(f"no subject {subject.code}")
            uow.subjects.save(subject)
            uow.commit()
        return subject

    def delete(self, code: str) -> None:
        """Remove a subject that has no exams. Subjects with exams are kept."""
        try:
            code = normalize_subject_code(code)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc
        with self._uow_factory() as uow:
            if uow.subjects.get(code) is None:
                raise NotFound(f"no subject {code}")
            if uow.exams.list_all(code):
                raise Conflict(f"subject {code} has exams and cannot be deleted")
            uow.subjects.delete(code)
            uow.commit()


def _build(code: str, name: str, exam_date: date | None) -> Subject:
    try:
        return Subject(code, name, exam_date)
    except ValueError as exc:
        raise InvalidInput(str(exc)) from exc
