"""The layout extractor and region rendering on real PDFs built for the purpose."""

import pymupdf
import pytest

from levet.adapters.extraction.layout_extractor import LayoutExtractor, read_lines
from levet.adapters.pdf.pymupdf_renderer import PyMuPdfRenderer
from levet.application.errors import InvalidPdf
from levet.application.ingestion import keep_preferred_language
from levet.domain import Language, Region

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def heading(text):
    return (text, {"bold": True, "gap": 6})


def summary(sections):
    return [(s.number, s.parent_number, s.title, s.points) for s in sections]


# --- extraction --------------------------------------------------------------


def test_reads_position_size_and_weight_of_every_line(exam_pdf):
    pages, lines = read_lines(exam_pdf)
    assert [(round(p.width), round(p.height)) for p in pages] == [(595, 842)] * 3

    title = next(line for line in lines if line.text == "Oppgave 1: Normalfordeling")
    body = next(line for line in lines if line.text.startswith("La X være"))
    assert title.bold and not body.bold
    assert title.page == body.page == 2
    assert title.y1 < body.y0
    assert title.x0 == pytest.approx(56, abs=1)


def test_finds_whole_tasks_with_titles_and_points_in_an_exam(exam_pdf):
    sections = LayoutExtractor().extract(exam_pdf)
    assert summary(sections) == [
        ("1", None, "Normalfordeling", 2),
        ("2", None, "Hypotesetest", 3),
    ]


def test_front_matter_and_page_furniture_end_up_in_no_task(exam_pdf):
    text = "\n".join(section.text for section in LayoutExtractor().extract(exam_pdf))
    assert "Tillatte hjelpemidler" not in text
    assert "EXAM-H24" not in text
    assert "2/3" not in text


def test_a_task_keeps_all_its_parts_including_over_a_page_break(exam_pdf):
    task = LayoutExtractor().extract(exam_pdf)[0]
    assert [region.page for region in task.regions] == [2, 3]
    assert task.text.splitlines() == [
        "Oppgave 1: Normalfordeling",
        "La X være normalfordelt med forventning 3.",
        "a) Hva er sannsynligheten for at X er mindre enn 1?",
        "0.16",
        "0.84",
        "b) Hva er variansen til 2X?",
        "4",
        "8",
        "Maks poeng: 2",
    ]


def test_finds_the_same_tasks_in_the_solution(solution_pdf):
    sections = LayoutExtractor().extract(solution_pdf)
    assert [(s.number, s.parent_number) for s in sections] == [("1", None), ("2", None)]
    assert "Standardiserer" in sections[0].text
    assert "Var(2X) = 4 Var(X) = 8." in sections[0].text


def test_a_trilingual_exam_yields_one_copy_of_each_task(build_pdf):
    pdf = build_pdf(
        ["Eksamen i statistikk / Eksamen i statistikk / Exam in statistics"],
        [
            heading("Oppgave 1"),
            "Hva er sannsynligheten for at kula ikke er defekt?",
            heading("Oppgave 2"),
            "Regn ut variansen og velg ett alternativ.",
        ],
        [
            heading("Oppgåve 1"),
            "Kva er sannsynet for at kula ikkje er defekt?",
            heading("Oppgåve 2"),
            "Rekn ut variansen og vel eitt alternativ.",
        ],
        [
            heading("Problem 1"),
            "What is the probability that the ball is not defective?",
            heading("Problem 2"),
            "Compute the variance and select one alternative.",
        ],
    )
    sections = LayoutExtractor().extract(pdf)
    assert [s.number for s in sections] == ["1", "2", "1", "2", "1", "2"]

    for language, page, word in [
        (Language.BOKMAL, 2, "sannsynligheten"),
        (Language.NYNORSK, 3, "sannsynet"),
        (Language.ENGLISH, 4, "probability"),
    ]:
        kept = keep_preferred_language(sections, language)
        assert [s.number for s in kept] == ["1", "2"]
        assert word in kept[0].text
        # A task runs up to the next heading, so the last one of a version
        # reaches onto the following page; that sliver is blank and is dropped
        # when the regions are rendered.
        rendered = PyMuPdfRenderer().render_regions(pdf, [r for s in kept for r in s.regions])
        assert {image.region.page for image in rendered if image is not None} == {page}


def test_a_pdf_without_recognisable_tasks_comes_back_one_section_per_page(make_pdf):
    sections = LayoutExtractor().extract(make_pdf("håndskrevet", "notat", "uten struktur"))
    assert [s.number for s in sections] == ["1", "2", "3"]
    assert [region.page for s in sections for region in s.regions] == [1, 2, 3]


def test_a_pdf_with_no_text_at_all_still_yields_every_page():
    document = pymupdf.open()
    for _ in range(2):
        document.new_page().draw_rect((100, 100, 300, 300), fill=(0, 0, 0))
    sections = LayoutExtractor().extract(document.tobytes())
    assert [(s.number, s.text) for s in sections] == [("1", ""), ("2", "")]


@pytest.mark.parametrize("data", [b"", b"not a pdf", b"%PDF-1.7\ngarbage"])
def test_unreadable_documents_are_reported_as_invalid(data):
    with pytest.raises(InvalidPdf):
        LayoutExtractor().extract(data)


# --- rendering regions -------------------------------------------------------


def image_size(png):
    pixmap = pymupdf.Pixmap(png)
    return pixmap.width, pixmap.height


def test_a_region_is_rendered_trimmed_to_its_content(exam_pdf):
    # Below part a of task 1 the page is empty for a long way before part b.
    requested = Region(page=2, top=0.03, bottom=0.6, left=0.05, right=0.95)

    (rendered,) = PyMuPdfRenderer().render_regions(exam_pdf, [requested])

    assert rendered.png.startswith(PNG_SIGNATURE)
    # The image leaves the empty space out.
    assert requested.height > 0.5
    assert rendered.region.height < 0.3
    assert requested.top <= rendered.region.top < rendered.region.bottom <= requested.bottom
    assert (rendered.region.left, rendered.region.right) == (requested.left, requested.right)

    width, height = image_size(rendered.png)
    assert width == pytest.approx((requested.right - requested.left) * 595 / 72 * 200, abs=2)
    assert height == pytest.approx(rendered.region.height * 842 / 72 * 200, abs=2)


def test_region_images_use_their_own_higher_resolution(exam_pdf):
    region = Region(page=2, top=0.05, bottom=0.5)
    (coarse,) = PyMuPdfRenderer(region_dpi=100).render_regions(exam_pdf, [region])
    (fine,) = PyMuPdfRenderer(region_dpi=200).render_regions(exam_pdf, [region])
    assert image_size(fine.png)[0] == pytest.approx(2 * image_size(coarse.png)[0], abs=2)
    assert coarse.region == fine.region


def test_a_blank_region_and_a_region_on_a_missing_page_render_as_nothing(exam_pdf):
    blank = Region(page=2, top=0.5, bottom=0.7)
    beyond = Region(page=9, top=0.1, bottom=0.9)
    written = Region(page=2, top=0.05, bottom=0.2)
    rendered = PyMuPdfRenderer().render_regions(exam_pdf, [blank, written, beyond])
    assert [r is not None for r in rendered] == [False, True, False]


def test_what_a_region_image_shows_is_what_the_region_says(exam_pdf):
    """Rendering the trimmed region again gives the same picture: the region
    stored with a task describes its image exactly."""
    renderer = PyMuPdfRenderer()
    (first,) = renderer.render_regions(exam_pdf, [Region(page=2, top=0.03, bottom=0.6)])
    (again,) = renderer.render_regions(exam_pdf, [first.region])
    assert image_size(again.png)[1] == pytest.approx(image_size(first.png)[1], abs=3)
    assert again.region.top == pytest.approx(first.region.top, abs=0.002)
    assert again.region.bottom == pytest.approx(first.region.bottom, abs=0.002)
