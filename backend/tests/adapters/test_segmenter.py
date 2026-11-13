"""The layout segmenter, driven with hand-made lines instead of a PDF."""

import pytest

from levet.adapters.extraction.segmenter import Line, PageSize, segment

A4 = PageSize(width=595, height=842)
BODY_X = 56


class Doc:
    """Builds a document line by line. ``y`` advances down the current page."""

    def __init__(self, pages=3, furniture=True):
        self.page_count = pages
        self.lines = []
        self.page = 1
        self.y = 40.0
        if furniture:
            for page in range(1, pages + 1):
                self.lines.append(Line(page, 500, 16, 576, 27, "EXAM2024", size=10))
                self.lines.append(Line(page, 555, 815, 576, 826, f"{page}/{pages}", size=10))

    def at(self, page, y=40.0):
        self.page, self.y = page, y
        return self

    def add(self, text, x=BODY_X, bold=False, size=11.0, gap=4.0, width=300):
        height = size * 1.1
        self.lines.append(
            Line(self.page, x, self.y, x + width, self.y + height, text, bold=bold, size=size)
        )
        self.y += height + gap
        return self

    def space(self, points):
        self.y += points
        return self

    def heading(self, text):
        return self.add(text, bold=True).space(10)

    def options(self, *texts):
        for text in texts:
            self.add(text, x=80, gap=18)
        return self

    def segment(self):
        return segment([A4] * self.page_count, self.lines)


def numbers(sections):
    return [section.number for section in sections]


def by_number(sections):
    return {section.number: section for section in sections}


# --- headings ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("heading", "number", "title"),
    [
        ("Oppgave 1: Normalfordeling", "1", "Normalfordeling"),
        ("Oppgåve 2 Hendingar", "2", "Hendingar"),
        ("Oppg. 3 [15%]", "3", None),
        ("Problem 4", "4", None),
        ("Exercise 5. Regression", "5", "Regression"),
        ("Ekstraoppgave 8: Punktestimering", "8", "Punktestimering"),
        ("7 Oppgave 7: Regresjon", "7", "Regresjon"),
    ],
)
def test_task_headings_are_recognised_in_their_usual_spellings(heading, number, title):
    sections = Doc().heading(heading).add("Forklar begrepet.").segment()
    assert numbers(sections) == [number]
    assert sections[0].title == title


def test_a_heading_must_stand_out_from_running_text():
    doc = Doc().heading("Oppgave 1: Hendelser").add("Les dette først.")
    doc.add("Oppgave 2 handlet om noe annet, se forrige eksamen.")  # plain text, not a heading
    assert numbers(doc.segment()) == ["1"]


def test_a_larger_font_also_makes_a_heading():
    doc = Doc().add("Oppgave 1: Hendelser", size=16.5).add("Tekst.").add("Mer.").add("Enda mer.")
    doc.add("Oppgave 2: Varians", size=16.5).add("Mer tekst.").add("Og mer.")
    assert numbers(doc.segment()) == ["1", "2"]


def test_inspera_margin_number_beside_a_bold_title_is_a_heading():
    doc = Doc()
    doc.lines.append(Line(1, 39, 40, 45, 52, "4", bold=True))
    doc.lines.append(Line(1, 56, 40, 250, 52, "Kaffekopper", bold=True))
    doc.at(1, 70)
    for sentence in range(12):
        doc.add(f"Setning {sentence} om kaffe.")
    sections = doc.segment()
    assert numbers(sections) == ["4"]
    assert sections[0].title == "Kaffekopper"


def test_a_heading_printed_twice_is_one_task():
    doc = Doc()
    doc.add("2 Betinget sannsynlighet", x=39, bold=True, size=16.5)
    doc.heading("Oppgave 2: Betinget sannsynlighet")
    for sentence in range(12):
        doc.add(f"Setning {sentence} om en hurtigtest.")
    sections = doc.segment()
    assert numbers(sections) == ["2"]
    assert sections[0].title == "Betinget sannsynlighet"


def test_points_are_read_from_the_heading_or_from_a_max_points_line():
    doc = Doc().heading("Oppg. 1 [15%]").add("Tekst.").space(30)
    doc.heading("Oppgave 2 (10 poeng)").add("Tekst.").space(30)
    doc.heading("Oppgave 3: Varians").add("Tekst.").add("Maks poeng: 4", x=456)
    points = {s.number: s.points for s in doc.segment()}
    assert points == {"1": 15, "2": 10, "3": 4}


# --- a task is kept whole -----------------------------------------------------


def test_a_task_with_lettered_parts_is_one_section_with_all_of_them():
    doc = Doc().heading("Oppgave 3: Normalfordeling").add("Felles innledning.").space(12)
    doc.add("a) Finn forventningen.", bold=True).options("0.5", "0.7").space(40)
    doc.add("b) Finn variansen.").space(40)
    doc.add("(c) Finn medianen.")

    (section,) = doc.segment()

    assert (section.number, section.parent_number, section.title) == ("3", None, "Normalfordeling")
    assert section.text.splitlines() == [
        "Oppgave 3: Normalfordeling",
        "Felles innledning.",
        "a) Finn forventningen.",
        "0.5",
        "0.7",
        "b) Finn variansen.",
        "(c) Finn medianen.",
    ]


def test_answer_prompts_do_not_split_a_task():
    doc = Doc().heading("Oppgave 1: Observasjoner").add("Vi har gjort tre observasjoner.")
    for question in ("Hva blir gjennomsnittet?", "Hva blir standardavviket?"):
        doc.space(18).add(question).add("Velg ett alternativ", bold=True).options("1", "2")
    assert numbers(doc.segment()) == ["1"]


def test_the_whole_tasks_points_stay_with_it():
    doc = Doc().heading("Oppgave 1").add("a) En.").space(30).add("b) To.")
    doc.add("Maks poeng: 6", x=456)
    assert [(s.number, s.points) for s in doc.segment()] == [("1", 6)]


def test_consecutive_tasks_follow_each_other_as_separate_sections():
    doc = Doc().heading("Oppgave 1").add("a) En.").add("b) To.").space(20)
    doc.heading("Oppgave 2").add("a) Tre.")
    sections = doc.segment()
    assert numbers(sections) == ["1", "2"]
    assert "a) Tre." not in sections[0].text
    assert sections[1].text.endswith("a) Tre.")


# --- regions -----------------------------------------------------------------


def test_sections_tile_the_page_from_the_first_heading_without_gaps_or_overlap():
    doc = Doc().heading("Oppgave 1").add("Innledning.").space(30)
    doc.add("a) En.").space(60).add("b) To.").space(60)
    doc.heading("Oppgave 2").add("Tekst.").space(30)
    doc.heading("Oppgave 3").add("Tekst.")
    regions = [region for section in doc.segment() for region in section.regions]
    assert [r.page for r in regions[:3]] == [1, 1, 1]
    for above, below in zip(regions[:2], regions[1:3], strict=True):
        assert below.top == pytest.approx(above.bottom)
    assert regions[0].top < 40 / 842  # starts just above the first heading


def test_a_task_running_over_a_page_break_gets_one_region_per_page():
    doc = Doc().heading("Oppgave 1").add("a) Starter nederst på siden.").at(1, 700)
    doc.add("b) Spørsmålet står her.").at(2, 40).options("0.1", "0.2").space(30)
    doc.heading("Oppgave 2").add("Neste oppgave.")
    task = doc.segment()[0]
    assert [region.page for region in task.regions] == [1, 2]
    assert task.regions[0].bottom < 815 / 842  # stops above the footer
    assert task.regions[1].top > 27 / 842  # starts below the header
    assert "0.1" in task.text
    assert "Neste oppgave." not in task.text


def test_running_headers_and_footers_are_left_out_of_text_and_regions():
    doc = Doc(pages=4).heading("Oppgave 1").add("Tekst på side én.").at(2).add("Mer på side to.")
    section = doc.segment()[0]
    assert "EXAM2024" not in section.text
    assert "/4" not in section.text
    assert all(region.top > 27 / 842 for region in section.regions)
    assert all(region.bottom < 815 / 842 for region in section.regions)


def test_regions_share_one_horizontal_extent_around_the_text():
    doc = Doc().heading("Oppgave 1").add("En.", width=400).space(30)
    doc.heading("Oppgave 2").add("To.", width=100)
    regions = [region for section in doc.segment() for region in section.regions]
    assert len({(r.left, r.right) for r in regions}) == 1
    assert 0 < regions[0].left < BODY_X / 595
    assert (BODY_X + 400) / 595 < regions[0].right < 1


def test_a_task_ends_at_its_max_points_line():
    doc = Doc().heading("Oppgave 1").add("Tekst.").add("Maks poeng: 2", x=456).space(40)
    doc.add("Vedlegg: formelark som ikke hører til noen oppgave.")
    section = doc.segment()[0]
    assert "Vedlegg" not in section.text
    assert "Maks poeng: 2" in section.text


def test_what_comes_before_the_first_heading_belongs_to_no_task():
    doc = Doc().add("Eksamen i statistikk. Tillatte hjelpemidler: kalkulator.").at(2)
    doc.heading("Oppgave 1").add("Tekst.")
    sections = doc.segment()
    assert numbers(sections) == ["1"]
    assert all(region.page >= 2 for region in sections[0].regions)
    assert "hjelpemidler" not in sections[0].text


def test_the_last_task_without_a_points_line_runs_to_the_end_of_the_document():
    doc = Doc(pages=3).heading("Oppgave 1").add("Starter på side én.").at(3).add("Slutter her.")
    section = doc.segment()[0]
    assert [region.page for region in section.regions] == [1, 2, 3]


# --- language versions and fallback ------------------------------------------


def test_every_language_version_is_returned_for_the_caller_to_choose_from():
    doc = Doc().heading("Oppgave 1").add("Hva er svaret?").at(2)
    doc.heading("Oppgåve 1").add("Kva er svaret?").at(3)
    doc.heading("Problem 1").add("What is the answer?")
    assert numbers(doc.segment()) == ["1", "1", "1"]


def test_a_document_without_recognisable_tasks_becomes_one_section_per_page():
    doc = Doc(pages=3, furniture=False).add("Skannet tekst uten overskrifter.").at(3).add("Mer.")
    sections = doc.segment()
    assert numbers(sections) == ["1", "2", "3"]
    assert [s.title for s in sections] == ["Page 1", "Page 2", "Page 3"]
    assert [(r.page, r.top, r.bottom) for s in sections for r in s.regions] == [
        (1, 0.0, 1.0),
        (2, 0.0, 1.0),
        (3, 0.0, 1.0),
    ]
    assert sections[0].text == "Skannet tekst uten overskrifter."


def test_an_empty_document_has_no_sections():
    assert segment([], []) == []
