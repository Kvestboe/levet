import pymupdf

from levet.adapters.extraction.segmenter import Line, PageSize, segment
from levet.adapters.pdf.lock import PDF_LOCK
from levet.application.errors import InvalidPdf
from levet.application.ports import ExtractedSection

_BOLD_FLAG = 16
_BOLD_NAMES = ("bold", "black", "heavy", "cmbx", "-bd", "demi")


class LayoutExtractor:
    """Finds tasks from the positions of the text in the PDF.

    Runs locally and instantly, with no model or network. It needs a PDF with
    real text in it; a scanned exam has none and comes back as one section per
    page, to be split by hand.
    """

    def extract(self, pdf: bytes) -> list[ExtractedSection]:
        pages, lines = read_lines(pdf)
        return segment(pages, lines)


def read_lines(pdf: bytes) -> tuple[list[PageSize], list[Line]]:
    """Every line of text in the document with its position, size and weight."""
    with PDF_LOCK:
        try:
            document = pymupdf.open(stream=pdf, filetype="pdf")
        except (pymupdf.FileDataError, pymupdf.EmptyFileError) as exc:
            raise InvalidPdf("the file could not be read as a PDF") from exc
        try:
            if document.needs_pass:
                raise InvalidPdf("the PDF is password-protected")
            pages: list[PageSize] = []
            lines: list[Line] = []
            for number, page in enumerate(document, start=1):
                pages.append(PageSize(page.rect.width, page.rect.height))
                for block in page.get_text("dict")["blocks"]:
                    for raw in block.get("lines", []):
                        spans = [span for span in raw["spans"] if span["text"].strip()]
                        if not spans:
                            continue
                        x0, y0, x1, y1 = raw["bbox"]
                        lines.append(
                            Line(
                                page=number,
                                x0=x0,
                                y0=y0,
                                x1=x1,
                                y1=y1,
                                text="".join(span["text"] for span in raw["spans"]).strip(),
                                bold=_is_bold(spans[0]),
                                size=max(span["size"] for span in spans),
                            )
                        )
            return pages, lines
        finally:
            document.close()


def _is_bold(span: dict) -> bool:
    font = span["font"].lower()
    return bool(span["flags"] & _BOLD_FLAG) or any(name in font for name in _BOLD_NAMES)
