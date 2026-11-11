from collections.abc import Iterator
from contextlib import contextmanager

import pymupdf

from levet.application.errors import InvalidPdf


class PyMuPdfRenderer:
    """Renders PDF pages to PNG with PyMuPDF.

    PyMuPDF is not safe to use from several threads at once; the application
    only calls this from its single background worker.
    """

    def __init__(self, dpi: int = 150) -> None:
        self._dpi = dpi

    def count_pages(self, pdf: bytes) -> int:
        with _open(pdf) as document:
            return document.page_count

    def render_pages(self, pdf: bytes) -> Iterator[bytes]:
        with _open(pdf) as document:
            for page in document:
                yield page.get_pixmap(dpi=self._dpi, alpha=False).tobytes("png")


@contextmanager
def _open(pdf: bytes) -> Iterator[pymupdf.Document]:
    try:
        document = pymupdf.open(stream=pdf, filetype="pdf")
    except (pymupdf.FileDataError, pymupdf.EmptyFileError) as exc:
        raise InvalidPdf("the file could not be read as a PDF") from exc
    try:
        if document.needs_pass:
            raise InvalidPdf("the PDF is password-protected")
        if document.page_count == 0:
            raise InvalidPdf("the PDF has no pages")
        yield document
    finally:
        document.close()
