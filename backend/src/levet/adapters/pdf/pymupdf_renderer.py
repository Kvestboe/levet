from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import pymupdf

from levet.adapters.pdf.lock import PDF_LOCK
from levet.application.errors import InvalidPdf
from levet.application.ports import RenderedRegion
from levet.domain import Region

# Anything darker than this (0 = black, 255 = white) counts as content when
# looking for the empty space around a region.
_INK_THRESHOLD = 245
_TRIM_PADDING = 3.0  # points of air left around the content


class PyMuPdfRenderer:
    """Renders PDF pages, and regions of them, to PNG with PyMuPDF."""

    def __init__(self, dpi: int = 150, region_dpi: int = 200) -> None:
        self._dpi = dpi
        self._region_dpi = region_dpi

    def count_pages(self, pdf: bytes) -> int:
        with _open(pdf) as document:
            return document.page_count

    def render_pages(self, pdf: bytes) -> Iterator[bytes]:
        with _open(pdf) as document:
            for page in document:
                yield page.get_pixmap(dpi=self._dpi, alpha=False).tobytes("png")

    def render_regions(self, pdf: bytes, regions: Sequence[Region]) -> list[RenderedRegion | None]:
        with _open(pdf) as document:
            return [self._render_region(document, region) for region in regions]

    def _render_region(self, document: pymupdf.Document, region: Region) -> RenderedRegion | None:
        if region.page > document.page_count:
            return None
        page = document[region.page - 1]
        bounds = page.rect
        clip = pymupdf.Rect(
            bounds.x0 + region.left * bounds.width,
            bounds.y0 + region.top * bounds.height,
            bounds.x0 + region.right * bounds.width,
            bounds.y0 + region.bottom * bounds.height,
        )
        content = _content_rows(page, clip)
        if content is None:
            return None
        top = max(clip.y0, content[0] - _TRIM_PADDING)
        bottom = min(clip.y1, content[1] + _TRIM_PADDING)
        trimmed = pymupdf.Rect(clip.x0, top, clip.x1, bottom)
        png = page.get_pixmap(clip=trimmed, dpi=self._region_dpi, alpha=False).tobytes("png")
        return RenderedRegion(
            region=Region(
                page=region.page,
                top=(top - bounds.y0) / bounds.height,
                bottom=(bottom - bounds.y0) / bounds.height,
                left=region.left,
                right=region.right,
            ),
            png=png,
        )


def _content_rows(page: pymupdf.Page, clip: pymupdf.Rect) -> tuple[float, float] | None:
    """Top and bottom (in points) of what is actually drawn inside ``clip``, or
    None if it is blank. Found by rendering it small in grey and looking for
    the first and last row that is not white."""
    pixmap = page.get_pixmap(clip=clip, dpi=72, colorspace=pymupdf.csGRAY, alpha=False)
    samples, width, stride = pixmap.samples, pixmap.width, pixmap.stride
    inked = [
        row
        for row in range(pixmap.height)
        if min(samples[row * stride : row * stride + width]) < _INK_THRESHOLD
    ]
    if not inked:
        return None
    scale = clip.height / pixmap.height
    return clip.y0 + inked[0] * scale, clip.y0 + (inked[-1] + 1) * scale


@contextmanager
def _open(pdf: bytes) -> Iterator[pymupdf.Document]:
    # The lock is held for as long as the document is open.
    with PDF_LOCK:
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
