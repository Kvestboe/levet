from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from levet.adapters.http.deps import ContainerDep
from levet.adapters.http.schemas import ExamOut
from levet.application.exams import ExamView
from levet.application.storage_keys import PageKind

router = APIRouter(prefix="/exams", tags=["exams"])

_CHUNK = 1024 * 1024
# Room for the multipart framing and the two text fields around the files.
_FORM_OVERHEAD = 64 * 1024


@router.get("")
def list_exams(container: ContainerDep, subject: str | None = None) -> list[ExamOut]:
    return [ExamOut.of(view) for view in container.exams.list_all(subject)]


@router.post("", status_code=202)
async def upload_exam(request: Request, container: ContainerDep) -> ExamOut:
    """Multipart form: ``subject_code``, ``label``, ``pdf`` and optionally ``solution_pdf``.

    Returns as soon as the files are stored; processing continues in the background.
    """
    limit = container.settings.max_upload_bytes
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > 2 * limit + _FORM_OVERHEAD:
        raise _too_large(limit)

    async with request.form(max_files=2, max_fields=4) as form:
        subject_code = form.get("subject_code")
        label = form.get("label")
        pdf = form.get("pdf")
        solution = form.get("solution_pdf")
        if not isinstance(subject_code, str) or not isinstance(label, str):
            raise HTTPException(status_code=422, detail="subject_code and label are required.")
        if not isinstance(pdf, UploadFile):
            raise HTTPException(status_code=422, detail="The exam PDF is required.")
        pdf_bytes = await _read(pdf, limit)
        solution_bytes = await _read(solution, limit) if isinstance(solution, UploadFile) else b""

    exam = await run_in_threadpool(
        container.exams.upload, subject_code, label, pdf_bytes, solution_bytes or None
    )
    return ExamOut.of(ExamView(exam))


@router.get("/{exam_id}")
def get_exam(exam_id: UUID, container: ContainerDep) -> ExamOut:
    return ExamOut.of(container.exams.get(exam_id))


@router.post("/{exam_id}/retry", status_code=202)
def retry_exam(exam_id: UUID, container: ContainerDep) -> ExamOut:
    return ExamOut.of(ExamView(container.exams.retry(exam_id)))


@router.get("/{exam_id}/pages/{kind}/{number}")
def get_page_image(exam_id: UUID, kind: PageKind, number: int, container: ContainerDep) -> Response:
    """PNG of one rendered page of the exam or of its solution; ``number`` starts at 1."""
    image = container.exams.page_image(exam_id, kind, number)
    return Response(
        content=image,
        media_type="image/png",
        # A rendered page never changes, so the browser may keep it.
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


async def _read(upload: UploadFile, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while chunk := await upload.read(_CHUNK):
        size += len(chunk)
        if size > limit:
            raise _too_large(limit)
        chunks.append(chunk)
    return b"".join(chunks)


def _too_large(limit: int) -> HTTPException:
    return HTTPException(
        status_code=413,
        detail=f"The file is too large. The limit is {limit // (1024 * 1024)} MB per PDF.",
    )
