import pymupdf
import pytest

from levet.adapters.pdf.pymupdf_renderer import PyMuPdfRenderer
from levet.application.errors import InvalidPdf

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def image_size(png: bytes) -> tuple[int, int]:
    pixmap = pymupdf.Pixmap(png)
    return pixmap.width, pixmap.height


def test_counts_pages(make_pdf):
    assert PyMuPdfRenderer().count_pages(make_pdf("1", "2", "3")) == 3


def test_renders_one_png_per_page_in_order(make_pdf):
    pages = list(PyMuPdfRenderer().render_pages(make_pdf("Oppgave 1", "Oppgave 2")))
    assert len(pages) == 2
    assert all(page.startswith(PNG_SIGNATURE) for page in pages)
    assert pages[0] != pages[1]


def test_a4_page_at_150_dpi_has_the_expected_pixel_size(make_pdf):
    (page,) = PyMuPdfRenderer(dpi=150).render_pages(make_pdf("x"))
    width, height = image_size(page)
    # A4 is 8.27 × 11.69 inches.
    assert width == pytest.approx(8.27 * 150, abs=2)
    assert height == pytest.approx(11.69 * 150, abs=2)


def test_resolution_follows_the_configured_dpi(make_pdf):
    pdf = make_pdf("x")
    (low,) = PyMuPdfRenderer(dpi=75).render_pages(pdf)
    (high,) = PyMuPdfRenderer(dpi=150).render_pages(pdf)
    assert image_size(high)[0] == pytest.approx(2 * image_size(low)[0], abs=2)


def test_rendered_page_shows_the_page_content(make_pdf):
    (blank,) = PyMuPdfRenderer().render_pages(make_pdf(""))
    (written,) = PyMuPdfRenderer().render_pages(make_pdf("Oppgave 1 æøå"))
    assert blank != written


@pytest.mark.parametrize("data", [b"", b"not a pdf", b"%PDF-1.7\ngarbage"])
def test_unreadable_documents_are_reported_as_invalid(data):
    renderer = PyMuPdfRenderer()
    with pytest.raises(InvalidPdf):
        renderer.count_pages(data)
    with pytest.raises(InvalidPdf):
        list(renderer.render_pages(data))


def test_password_protected_pdf_is_reported_as_invalid(make_pdf):
    document = pymupdf.open(stream=make_pdf("secret"), filetype="pdf")
    encrypted = document.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="user", owner_pw="owner"
    )
    with pytest.raises(InvalidPdf, match="password"):
        PyMuPdfRenderer().count_pages(encrypted)
