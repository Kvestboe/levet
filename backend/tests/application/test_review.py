from uuid import uuid4

import pytest

from levet.application.errors import Conflict, InvalidInput, NotFound
from levet.application.ports import RenderedRegion
from levet.application.review import ReviewService
from levet.domain import Exam, ExamStatus, Region, Subject, Task, Topic

PDF = b"%PDF exam"


class FakeRenderer:
    """Renders any region as bytes naming it; a region thinner than 0.03 is blank."""

    def render_regions(self, pdf, regions):
        return [
            None
            if region.height < 0.03
            else RenderedRegion(
                region, b"image p%d %.3f-%.3f" % (region.page, region.top, region.bottom)
            )
            for region in regions
        ]


def band(page, top, bottom):
    return Region(page=page, top=top, bottom=bottom)


@pytest.fixture
def review(uow_factory, files):
    return ReviewService(uow_factory, files, FakeRenderer())


@pytest.fixture
def exam(uow_factory, files, now):
    exam = Exam(
        subject_code="ISTT1003",
        label="Høst 2024",
        pdf_key="exams/x/exam.pdf",
        uploaded_at=now,
        status=ExamStatus.NEEDS_REVIEW,
        page_count=4,
    )
    files.write(exam.pdf_key, PDF)
    with uow_factory() as uow:
        uow.subjects.save(Subject("ISTT1003", "Statistikk"))
        uow.exams.save(exam)
        uow.commit()
    return exam


@pytest.fixture
def add_task(uow_factory, files, exam):
    """Stores a task with one image file per region."""
    count = 0

    def add(number, *regions, **fields):
        nonlocal count
        regions = regions or (band(1, 0.1, 0.3),)
        keys = tuple(f"exams/{exam.id}/task-images/{uuid4().hex}.png" for _ in regions)
        for key in keys:
            files.write(key, b"old image")
        task = Task(
            exam_id=exam.id,
            number=number,
            position=count,
            regions=regions,
            image_keys=keys,
            **fields,
        )
        count += 1
        with uow_factory() as uow:
            uow.tasks.save(task)
            uow.commit()
        return task

    return add


@pytest.fixture
def add_topic(uow_factory, exam):
    def add(name):
        topic = Topic(subject_code="ISTT1003", name=name)
        with uow_factory() as uow:
            uow.topics.save(topic)
            uow.commit()
        return topic

    return add


def numbers(review, exam):
    return [task.number for task in review.tasks(exam.id).tasks]


def topic_names(review, exam):
    return sorted(topic.name for topic in review.tasks(exam.id).topics)


def task_topics(review, exam, number):
    view = review.tasks(exam.id)
    names = {topic.id: topic.name for topic in view.topics}
    task = next(task for task in view.tasks if task.number == number)
    return sorted(names[i] for i in task.topic_ids)


def set_status(uow_factory, exam, status):
    with uow_factory() as uow:
        current = uow.exams.get(exam.id)
        uow.exams.save(
            Exam(
                id=current.id,
                subject_code=current.subject_code,
                label=current.label,
                pdf_key=current.pdf_key,
                uploaded_at=current.uploaded_at,
                status=status,
                page_count=current.page_count,
            )
        )
        uow.commit()


# --- reading -----------------------------------------------------------------


def test_tasks_are_listed_in_document_order_with_the_subjects_topics(
    review, exam, add_task, add_topic
):
    topic = add_topic("Normalfordeling")
    parent = add_task("1", topic_ids={topic.id})
    add_task("1a", parent_id=parent.id)
    add_task("2")

    view = review.tasks(exam.id)

    assert [task.number for task in view.tasks] == ["1", "1a", "2"]
    assert [t.name for t in view.topics] == ["Normalfordeling"]
    assert view.exam.id == exam.id


def test_reading_the_tasks_of_an_unknown_exam_is_not_found(review):
    with pytest.raises(NotFound):
        review.tasks(uuid4())


def test_task_images_are_served_by_name_and_nothing_else_is(review, exam, add_task):
    task = add_task("1")
    name = task.image_keys[0].rsplit("/", 1)[-1]
    assert review.task_image(exam.id, name) == b"old image"
    for bad in ("../exam.pdf", "exam.pdf", "0" * 32 + ".png", name.upper()):
        with pytest.raises(NotFound):
            review.task_image(exam.id, bad)
    with pytest.raises(NotFound):
        review.task_image(uuid4(), name)


# --- editing fields and topics -----------------------------------------------


def test_number_title_and_points_can_be_changed_one_at_a_time(review, exam, add_task):
    task = add_task("1", title="Gammel tittel", points=2)

    review.update_task(task.id, number="1a")
    review.update_task(task.id, points=4.5)
    (updated,) = review.tasks(exam.id).tasks
    assert (updated.number, updated.title, updated.points) == ("1a", "Gammel tittel", 4.5)

    review.update_task(task.id, title=None, points=None)
    (cleared,) = review.tasks(exam.id).tasks
    assert (cleared.number, cleared.title, cleared.points) == ("1a", None, None)


def test_invalid_field_values_are_rejected(review, add_task):
    task = add_task("1")
    with pytest.raises(InvalidInput):
        review.update_task(task.id, number="  ")
    with pytest.raises(InvalidInput):
        review.update_task(task.id, points=-1)


def test_topics_are_set_by_name_reusing_existing_ones_and_creating_the_rest(
    review, exam, add_task, add_topic
):
    existing = add_topic("Normalfordeling")
    task = add_task("1", topic_ids={existing.id})

    review.update_task(task.id, topic_names=["  normalfordeling ", "Hypotesetest"])

    assert task_topics(review, exam, "1") == ["Hypotesetest", "Normalfordeling"]
    (updated,) = review.tasks(exam.id).tasks
    assert existing.id in updated.topic_ids  # reused, not duplicated
    assert topic_names(review, exam) == ["Hypotesetest", "Normalfordeling"]


def test_a_topic_no_task_uses_any_more_disappears(review, exam, add_task, add_topic):
    old = add_topic("Kaffekopper")
    task = add_task("1", topic_ids={old.id})

    review.update_task(task.id, topic_names=["Konfidensintervall"])

    assert topic_names(review, exam) == ["Konfidensintervall"]


def test_a_task_takes_at_most_three_topics_and_repeats_count_once(review, exam, add_task):
    task = add_task("1")
    review.update_task(task.id, topic_names=["A-tema", "a-tema", "B-tema", "", "C-tema"])
    assert task_topics(review, exam, "1") == ["A-tema", "B-tema", "C-tema"]
    with pytest.raises(InvalidInput):
        review.update_task(task.id, topic_names=["A", "B", "C", "D"])


def test_topics_can_be_cleared_so_a_part_takes_its_parents(review, exam, add_task, add_topic):
    topic = add_topic("Normalfordeling")
    parent = add_task("1", topic_ids={topic.id})
    part = add_task("1a", parent_id=parent.id, topic_ids={topic.id})

    review.update_task(part.id, topic_names=[])

    assert task_topics(review, exam, "1a") == []
    assert topic_names(review, exam) == ["Normalfordeling"]


# --- renaming and merging topics ---------------------------------------------


def test_renaming_a_topic_changes_it_on_every_task(review, exam, add_task, add_topic):
    story = add_topic("Normalfordelte kulediametere")
    add_task("1", topic_ids={story.id})
    add_task("2", topic_ids={story.id})

    renamed = review.rename_topic(story.id, "  Normalfordeling ")

    assert (renamed.id, renamed.name) == (story.id, "Normalfordeling")
    assert topic_names(review, exam) == ["Normalfordeling"]
    assert task_topics(review, exam, "1") == task_topics(review, exam, "2") == ["Normalfordeling"]


def test_renaming_to_an_existing_topics_name_merges_the_two(review, exam, add_task, add_topic):
    story = add_topic("Hypotesetest for fosfor i utslippsvann")
    proper = add_topic("Hypotesetest")
    other = add_topic("Varians")
    add_task("1", topic_ids={story.id})
    add_task("2", topic_ids={story.id, proper.id, other.id})
    add_task("3", topic_ids={proper.id})

    kept = review.rename_topic(story.id, "hypotesetest")

    assert kept.id == proper.id
    assert topic_names(review, exam) == ["Hypotesetest", "Varians"]
    assert task_topics(review, exam, "1") == ["Hypotesetest"]
    assert task_topics(review, exam, "2") == ["Hypotesetest", "Varians"]
    assert task_topics(review, exam, "3") == ["Hypotesetest"]


def test_a_topic_can_be_renamed_after_its_exam_is_approved(review, exam, add_task, add_topic):
    topic = add_topic("Kaffekopper")
    add_task("1", topic_ids={topic.id})
    review.approve(exam.id)

    review.rename_topic(topic.id, "Konfidensintervall")

    assert task_topics(review, exam, "1") == ["Konfidensintervall"]


def test_changing_only_the_case_of_a_topic_name_is_a_rename_not_a_merge(
    review, exam, add_task, add_topic
):
    topic = add_topic("normalfordeling")
    add_task("1", topic_ids={topic.id})
    assert review.rename_topic(topic.id, "Normalfordeling").id == topic.id
    assert topic_names(review, exam) == ["Normalfordeling"]


def test_a_topic_cannot_be_renamed_to_nothing_and_an_unknown_topic_is_not_found(review, add_topic):
    topic = add_topic("Varians")
    with pytest.raises(InvalidInput):
        review.rename_topic(topic.id, "   ")
    with pytest.raises(NotFound):
        review.rename_topic(uuid4(), "Varians")


# --- deleting ----------------------------------------------------------------


def test_deleting_a_task_removes_its_parts_images_and_orphaned_topics(
    review, exam, add_task, add_topic, files
):
    junk_topic = add_topic("Forside")
    kept_topic = add_topic("Normalfordeling")
    junk = add_task("0", topic_ids={junk_topic.id})
    part = add_task("0a", parent_id=junk.id)
    kept = add_task("1", topic_ids={kept_topic.id})

    review.delete_task(junk.id)

    assert numbers(review, exam) == ["1"]
    assert topic_names(review, exam) == ["Normalfordeling"]
    assert not files.exists(junk.image_keys[0])
    assert not files.exists(part.image_keys[0])
    assert files.exists(kept.image_keys[0])


# --- merging -----------------------------------------------------------------


def test_merging_appends_a_task_to_the_one_before_it(review, exam, add_task, files):
    first = add_task("1a", band(1, 0.1, 0.3), text="a) Første", points=1, solution_text="Svar a")
    second = add_task("1b", band(1, 0.3, 0.5), band(2, 0.1, 0.2), text="feil delt", points=1)
    add_task("1c")

    merged = review.merge_with_previous(second.id)

    assert numbers(review, exam) == ["1a", "1c"]
    assert merged.id == first.id
    assert merged.regions == first.regions + second.regions
    assert merged.image_keys == first.image_keys + second.image_keys
    assert merged.text == "a) Første\nfeil delt"
    assert merged.points == 2
    assert merged.solution_text == "Svar a"
    assert all(files.exists(key) for key in merged.image_keys)


def test_the_first_part_can_be_merged_into_its_tasks_introduction(review, exam, add_task):
    parent = add_task("1", band(1, 0.1, 0.2))
    part = add_task("1a", band(1, 0.2, 0.4), parent_id=parent.id)

    merged = review.merge_with_previous(part.id)

    assert numbers(review, exam) == ["1"]
    assert merged.regions == (band(1, 0.1, 0.2), band(1, 0.2, 0.4))


def test_merging_is_refused_for_the_first_task_and_for_a_task_with_parts(review, add_task):
    parent = add_task("1")
    add_task("1a", parent_id=parent.id)
    second = add_task("2")
    add_task("2a", parent_id=second.id)
    with pytest.raises(Conflict):
        review.merge_with_previous(parent.id)  # nothing before it
    with pytest.raises(Conflict):
        review.merge_with_previous(second.id)  # has sub-tasks


# --- splitting ---------------------------------------------------------------


def test_splitting_cuts_a_task_in_two_at_the_chosen_point(review, exam, add_task, add_topic, files):
    topic = add_topic("Normalfordeling")
    parent = add_task("3", topic_ids={topic.id})
    task = add_task(
        "3a",
        band(2, 0.2, 0.6),
        band(3, 0.1, 0.4),
        parent_id=parent.id,
        topic_ids={topic.id},
        points=2,
    )
    add_task("3b", parent_id=parent.id)
    replaced_image = task.image_keys[0]

    first, second = review.split_task(task.id, image_index=0, fraction=0.25)

    assert numbers(review, exam) == ["3", "3a", "3b", "3b"]
    assert [t.position for t in review.tasks(exam.id).tasks] == [0, 1, 2, 3]
    # Above the cut stays; below it, and the image after, moves to the new task.
    assert first.id == task.id
    assert [(r.page, r.top, r.bottom) for r in first.regions] == [(2, 0.2, pytest.approx(0.3))]
    assert [(r.page, r.top, r.bottom) for r in second.regions] == [
        (2, pytest.approx(0.3), 0.6),
        (3, 0.1, 0.4),
    ]
    assert second.image_keys[1] == task.image_keys[1]
    assert files.read(first.image_keys[0]) == b"image p2 0.200-0.300"
    assert files.read(second.image_keys[0]) == b"image p2 0.300-0.600"
    assert not files.exists(replaced_image)
    # The new task sits beside the old one and starts with its topics.
    assert second.parent_id == parent.id
    assert second.topic_ids == frozenset({topic.id})
    assert (first.points, second.points) == (2, None)


@pytest.mark.parametrize(
    ("number", "expected"), [("3b", "3c"), ("3", "4"), ("12", "13"), ("A1", "A1-2")]
)
def test_the_split_off_task_gets_the_next_label_as_a_suggestion(review, add_task, number, expected):
    task = add_task(number, band(1, 0.1, 0.9))
    _, second = review.split_task(task.id, 0, 0.5)
    assert second.number == expected


def test_a_piece_cut_from_a_task_with_parts_becomes_its_first_part(
    review, exam, add_task, add_topic
):
    topic = add_topic("Normalfordeling")
    parent = add_task("3", band(1, 0.1, 0.5), topic_ids={topic.id})
    add_task("3b", parent_id=parent.id)

    _, piece = review.split_task(parent.id, 0, 0.5)

    assert numbers(review, exam) == ["3", "3a", "3b"]
    assert piece.parent_id == parent.id
    assert piece.topic_ids == frozenset()  # takes its parent's


def test_splitting_needs_a_point_inside_one_of_the_tasks_images(review, add_task):
    task = add_task("1", band(1, 0.1, 0.9))
    for image_index, fraction in [(1, 0.5), (-1, 0.5), (0, 0.0), (0, 1.0), (0, 0.001)]:
        with pytest.raises(InvalidInput):
            review.split_task(task.id, image_index, fraction)


def test_a_split_that_would_leave_one_side_empty_is_refused_and_changes_nothing(
    review, exam, add_task, files
):
    task = add_task("1", band(1, 0.10, 0.20))
    with pytest.raises(InvalidInput):
        review.split_task(task.id, 0, 0.2)  # the upper piece would be 0.02 tall: blank
    (unchanged,) = review.tasks(exam.id).tasks
    assert unchanged == task
    assert files.exists(task.image_keys[0])


# --- approving ---------------------------------------------------------------


def test_approving_makes_the_exam_ready_and_writes_inherited_topics_down(
    review, exam, add_task, add_topic
):
    normal = add_topic("Normalfordeling")
    test = add_topic("Hypotesetest")
    parent = add_task("1", topic_ids={normal.id})
    add_task("1a", parent_id=parent.id)
    add_task("1b", parent_id=parent.id, topic_ids={test.id})
    add_task("2", topic_ids={test.id})

    approved = review.approve(exam.id)

    assert approved.status is ExamStatus.READY
    assert review.tasks(exam.id).exam.status is ExamStatus.READY
    assert task_topics(review, exam, "1a") == ["Normalfordeling"]
    assert task_topics(review, exam, "1b") == ["Hypotesetest"]


def test_every_task_to_be_practised_needs_a_topic(review, exam, add_task, add_topic):
    topic = add_topic("Normalfordeling")
    tagged = add_task("1", topic_ids={topic.id})
    add_task("1a", parent_id=tagged.id)
    untagged = add_task("2")
    add_task("2a", parent_id=untagged.id)
    add_task("2b", parent_id=untagged.id)
    add_task("3")

    with pytest.raises(Conflict, match="2a, 2b, 3"):
        review.approve(exam.id)
    assert review.tasks(exam.id).exam.status is ExamStatus.NEEDS_REVIEW


def test_a_task_with_parts_needs_no_topic_of_its_own(review, exam, add_task, add_topic):
    topic = add_topic("Normalfordeling")
    parent = add_task("1")
    add_task("1a", parent_id=parent.id, topic_ids={topic.id})
    assert review.approve(exam.id).status is ExamStatus.READY


def test_an_exam_without_tasks_cannot_be_approved(review, exam):
    with pytest.raises(Conflict):
        review.approve(exam.id)


def test_only_an_exam_awaiting_review_can_be_approved_or_edited(
    review, exam, add_task, add_topic, uow_factory
):
    topic = add_topic("Normalfordeling")
    task = add_task("1", band(1, 0.1, 0.9), topic_ids={topic.id})
    other = add_task("2", topic_ids={topic.id})
    review.approve(exam.id)

    with pytest.raises(Conflict):
        review.approve(exam.id)
    for change in (
        lambda: review.update_task(task.id, number="9"),
        lambda: review.delete_task(task.id),
        lambda: review.merge_with_previous(other.id),
        lambda: review.split_task(task.id, 0, 0.5),
    ):
        with pytest.raises(Conflict):
            change()
    assert numbers(review, exam) == ["1", "2"]


def test_changing_an_unknown_task_is_not_found(review):
    for change in (
        lambda: review.update_task(uuid4(), number="1"),
        lambda: review.delete_task(uuid4()),
        lambda: review.merge_with_previous(uuid4()),
        lambda: review.split_task(uuid4(), 0, 0.5),
    ):
        with pytest.raises(NotFound):
            change()
