from datetime import date

import pytest

from levet.application.errors import Conflict, InvalidInput, NotFound
from levet.application.subjects import SubjectService
from levet.domain import Exam, Subject


@pytest.fixture
def subjects(uow_factory):
    return SubjectService(uow_factory)


def test_created_subject_is_stored_under_its_normalised_code(subjects):
    created = subjects.create(" idatt2202 ", "Operativsystemer", date(2026, 12, 1))
    assert created == Subject("IDATT2202", "Operativsystemer", date(2026, 12, 1))
    assert subjects.list_all() == [created]


def test_creating_the_same_code_twice_is_a_conflict(subjects):
    subjects.create("IDATT2202", "Operativsystemer")
    with pytest.raises(Conflict):
        subjects.create("idatt2202", "Something else")
    assert [s.name for s in subjects.list_all()] == ["Operativsystemer"]


@pytest.mark.parametrize(("code", "name"), [("", "Operativsystemer"), ("IDATT2202", " ")])
def test_blank_code_or_name_is_invalid_input(subjects, code, name):
    with pytest.raises(InvalidInput):
        subjects.create(code, name)


def test_subjects_are_listed_nearest_exam_first_with_undated_last(subjects):
    subjects.create("AAA1000", "No date yet")
    subjects.create("ZZZ9000", "Soon", date(2026, 11, 20))
    subjects.create("MMM5000", "Later", date(2026, 12, 15))
    assert [s.code for s in subjects.list_all()] == ["ZZZ9000", "MMM5000", "AAA1000"]


def test_update_changes_name_and_exam_date(subjects):
    subjects.create("IDATT2202", "Operativsystemer", date(2026, 12, 1))
    subjects.update("idatt2202", "Operating systems", None)
    assert subjects.list_all() == [Subject("IDATT2202", "Operating systems")]


def test_updating_an_unknown_subject_is_not_found(subjects):
    with pytest.raises(NotFound):
        subjects.update("IDATT2202", "Operativsystemer", None)


def test_a_subject_without_exams_can_be_deleted(subjects):
    subjects.create("IDATT2202", "Operativsystemer")
    subjects.delete("idatt2202")
    assert subjects.list_all() == []


def test_a_subject_with_exams_is_kept(subjects, uow_factory, now):
    subjects.create("IDATT2202", "Operativsystemer")
    with uow_factory() as uow:
        uow.exams.save(
            Exam(subject_code="IDATT2202", label="Høst 2023", pdf_key="k", uploaded_at=now)
        )
        uow.commit()
    with pytest.raises(Conflict):
        subjects.delete("IDATT2202")
    assert len(subjects.list_all()) == 1


def test_deleting_an_unknown_subject_is_not_found(subjects):
    with pytest.raises(NotFound):
        subjects.delete("IDATT2202")
