"""Background processing of an uploaded exam.

The pipeline:

1. render every page of the exam (and of its solution) to an image;
2. find the tasks in the exam, keeping one language version;
3. find the solutions and match them to tasks by number;
4. render each task's and solution's regions to images;
5. suggest topics from the task titles, reusing the subject's existing ones;
6. hand the exam over for review.
"""

import logging
from collections.abc import Sequence
from uuid import UUID, uuid4

from levet.application import storage_keys
from levet.application.errors import InvalidPdf
from levet.application.ingestion import keep_preferred_language, match_solutions, matching_topic
from levet.application.ports import (
    ExtractedSection,
    ExtractionService,
    FileStore,
    PageRenderer,
    Progress,
    ProgressTracker,
    UnitOfWorkFactory,
)
from levet.application.storage_keys import PageKind
from levet.domain import Exam, ExamStatus, Language, Region, Task, Topic
from levet.domain.language import DEFAULT_LANGUAGE

log = logging.getLogger(__name__)

STAGE_RENDERING = "rendering"
STAGE_EXTRACTING = "extracting"
INTERRUPTED_MESSAGE = "Processing was interrupted by a server restart."

_MAX_ATTEMPTS = 2
_MAX_ERROR_LENGTH = 500
_DOCUMENT_NAMES = {PageKind.EXAM: "Exam PDF", PageKind.SOLUTION: "Solution PDF"}


class ExamProcessor:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        files: FileStore,
        renderer: PageRenderer,
        extractor: ExtractionService,
        progress: ProgressTracker,
        preferred_language: Language = DEFAULT_LANGUAGE,
    ) -> None:
        self._uow_factory = uow_factory
        self._files = files
        self._renderer = renderer
        self._extractor = extractor
        self._progress = progress
        self._preferred_language = preferred_language

    def process(self, exam_id: UUID) -> None:
        """Run the pipeline for one exam. Never raises for a pipeline failure.

        A failed run is retried once. If it fails again, or the failure is one
        a retry cannot fix, the exam is marked ``failed`` with the error.
        """
        error: Exception | None = None
        try:
            for attempt in range(1, _MAX_ATTEMPTS + 1):
                try:
                    self._run(exam_id)
                    return
                except InvalidPdf as exc:
                    error = exc
                    break
                except Exception as exc:
                    log.warning(
                        "processing exam %s failed (attempt %d of %d)",
                        exam_id,
                        attempt,
                        _MAX_ATTEMPTS,
                        exc_info=True,
                    )
                    error = exc
        finally:
            self._progress.clear(exam_id)
        self._mark_failed(exam_id, _describe(error))

    def recover_interrupted(self) -> int:
        """Fail exams left in ``processing`` by a previous run of the server.

        The job queue lives in memory, so such exams would otherwise stay in
        ``processing`` for ever. Returns how many exams were marked failed.
        """
        with self._uow_factory() as uow:
            stuck = uow.exams.list_by_status(ExamStatus.PROCESSING)
            for exam in stuck:
                uow.exams.save(exam.fail(INTERRUPTED_MESSAGE))
            uow.commit()
        return len(stuck)

    # --- the pipeline ----------------------------------------------------------

    def _run(self, exam_id: UUID) -> None:
        exam = self._load_processing(exam_id)
        if exam is None:
            return

        documents = {PageKind.EXAM: self._files.read(exam.pdf_key)}
        if exam.solution_pdf_key is not None:
            documents[PageKind.SOLUTION] = self._files.read(exam.solution_pdf_key)

        page_counts = self._render_pages(exam_id, documents)
        tasks, new_topics = self._build_tasks(exam, documents)

        with self._uow_factory() as uow:
            current = uow.exams.get(exam_id)
            if current is None or current.status is not ExamStatus.PROCESSING:
                return
            # A retry starts from a clean slate.
            uow.tasks.delete_by_exam(exam_id)
            for topic in new_topics:
                uow.topics.save(topic)
            for task in tasks:
                uow.tasks.save(task)
            uow.topics.delete_unused(exam.subject_code)
            uow.exams.save(
                current.with_pages(
                    page_counts[PageKind.EXAM], page_counts.get(PageKind.SOLUTION)
                ).mark_needs_review()
            )
            uow.commit()

    def _render_pages(self, exam_id: UUID, documents: dict[PageKind, bytes]) -> dict[PageKind, int]:
        page_counts = {kind: self._count_pages(kind, pdf) for kind, pdf in documents.items()}
        total = sum(page_counts.values())
        done = 0
        self._progress.report(exam_id, Progress(STAGE_RENDERING, done, total))

        for kind, pdf in documents.items():
            rendered = 0
            for number, png in enumerate(self._renderer.render_pages(pdf), start=1):
                self._files.write(storage_keys.page_image(exam_id, kind, number), png)
                rendered += 1
                done += 1
                self._progress.report(exam_id, Progress(STAGE_RENDERING, done, total))
            if rendered != page_counts[kind]:
                # Never carry on with pages missing.
                raise RuntimeError(
                    f"{_DOCUMENT_NAMES[kind]}: rendered {rendered} of {page_counts[kind]} pages"
                )
        return page_counts

    def _build_tasks(
        self, exam: Exam, documents: dict[PageKind, bytes]
    ) -> tuple[list[Task], list[Topic]]:
        self._progress.report(exam.id, Progress(STAGE_EXTRACTING, 0, 1))
        exam_pdf = documents[PageKind.EXAM]
        solution_pdf = documents.get(PageKind.SOLUTION)

        sections = keep_preferred_language(
            self._extractor.extract(exam_pdf), self._preferred_language
        )
        solutions: dict[str, list[ExtractedSection]] = {}
        if solution_pdf is not None:
            solutions = match_solutions(
                sections,
                keep_preferred_language(
                    self._extractor.extract(solution_pdf), self._preferred_language
                ),
            )

        # Images from an earlier, failed run are no longer referenced by anything.
        self._files.delete_tree(storage_keys.task_images(exam.id))

        with self._uow_factory() as uow:
            topics = uow.topics.list_by_subject(exam.subject_code)
        new_topics: list[Topic] = []

        tasks: list[Task] = []
        parents: dict[str, UUID] = {}
        total = len(sections)
        for done, section in enumerate(sections, start=1):
            regions, image_keys = self._render(exam.id, exam_pdf, section.regions)
            answer = solutions.get(section.number, [])
            solution_regions: tuple[Region, ...] = ()
            solution_keys: tuple[str, ...] = ()
            if answer and solution_pdf is not None:
                solution_regions, solution_keys = self._render(
                    exam.id, solution_pdf, [r for part in answer for r in part.regions]
                )

            topic_ids: frozenset[UUID] = frozenset()
            if section.parent_number is None and section.title:
                topic = matching_topic(section.title, [*topics, *new_topics])
                if topic is None:
                    topic = Topic(subject_code=exam.subject_code, name=section.title)
                    new_topics.append(topic)
                topic_ids = frozenset({topic.id})

            task = Task(
                exam_id=exam.id,
                number=section.number,
                title=section.title,
                position=len(tasks),
                parent_id=parents.get(section.parent_number) if section.parent_number else None,
                text=section.text,
                points=section.points,
                topic_ids=topic_ids,
                regions=regions,
                image_keys=image_keys,
                solution_text="\n\n".join(part.text for part in answer if part.text) or None,
                solution_regions=solution_regions,
                solution_image_keys=solution_keys,
            )
            if section.parent_number is None:
                parents[section.number] = task.id
            tasks.append(task)
            self._progress.report(exam.id, Progress(STAGE_EXTRACTING, done, total))

        used = {topic_id for task in tasks for topic_id in task.topic_ids}
        return tasks, [topic for topic in new_topics if topic.id in used]

    def _render(
        self, exam_id: UUID, pdf: bytes, regions: Sequence[Region]
    ) -> tuple[tuple[Region, ...], tuple[str, ...]]:
        """Render regions to stored images. Blank regions are dropped; the
        regions returned are the ones the images actually show."""
        return render_regions(self._renderer, self._files, exam_id, pdf, regions)

    def _count_pages(self, kind: PageKind, pdf: bytes) -> int:
        try:
            return self._renderer.count_pages(pdf)
        except InvalidPdf as exc:
            raise InvalidPdf(f"{_DOCUMENT_NAMES[kind]}: {exc}") from exc

    def _load_processing(self, exam_id: UUID) -> Exam | None:
        with self._uow_factory() as uow:
            exam = uow.exams.get(exam_id)
        if exam is None or exam.status is not ExamStatus.PROCESSING:
            log.info("skipping exam %s: nothing to process", exam_id)
            return None
        return exam

    def _mark_failed(self, exam_id: UUID, error: str) -> None:
        with self._uow_factory() as uow:
            exam = uow.exams.get(exam_id)
            if exam is None or exam.status is not ExamStatus.PROCESSING:
                return
            uow.exams.save(exam.fail(error))
            uow.commit()


def render_regions(
    renderer: PageRenderer,
    files: FileStore,
    exam_id: UUID,
    pdf: bytes,
    regions: Sequence[Region],
) -> tuple[tuple[Region, ...], tuple[str, ...]]:
    """Render regions of a PDF and store the images under fresh names.

    Returns the regions the images show (blank ones dropped, empty space
    trimmed) and the images' file-store keys, in matching order.
    """
    kept: list[Region] = []
    keys: list[str] = []
    for rendered in renderer.render_regions(pdf, list(regions)):
        if rendered is None:
            continue
        key = storage_keys.task_image(exam_id, f"{uuid4().hex}.png")
        files.write(key, rendered.png)
        kept.append(rendered.region)
        keys.append(key)
    return tuple(kept), tuple(keys)


def _describe(error: Exception | None) -> str:
    if error is None:
        return "Processing failed."
    message = str(error).strip()
    if not isinstance(error, InvalidPdf):
        message = f"{type(error).__name__}: {message}" if message else type(error).__name__
    if len(message) > _MAX_ERROR_LENGTH:
        message = message[: _MAX_ERROR_LENGTH - 1] + "…"
    return message
