from fastapi import APIRouter

from levet.adapters.http.deps import ContainerDep
from levet.adapters.http.schemas import SubjectIn, SubjectOut, SubjectUpdate

router = APIRouter(prefix="/subjects", tags=["subjects"])


@router.get("")
def list_subjects(container: ContainerDep) -> list[SubjectOut]:
    return [SubjectOut.of(subject) for subject in container.subjects.list_all()]


@router.post("", status_code=201)
def create_subject(body: SubjectIn, container: ContainerDep) -> SubjectOut:
    return SubjectOut.of(container.subjects.create(body.code, body.name, body.exam_date))


@router.put("/{code}")
def update_subject(code: str, body: SubjectUpdate, container: ContainerDep) -> SubjectOut:
    return SubjectOut.of(container.subjects.update(code, body.name, body.exam_date))


@router.delete("/{code}", status_code=204)
def delete_subject(code: str, container: ContainerDep) -> None:
    container.subjects.delete(code)
