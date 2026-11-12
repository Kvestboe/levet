from levet.application.ingestion import (
    find_topic,
    keep_preferred_language,
    match_solutions,
    matching_topic,
    split_versions,
)
from levet.application.ports import ExtractedSection
from levet.domain import Language, Region, Topic

BAND = (Region(page=1, top=0.1, bottom=0.2),)

NB = "Hva er sannsynligheten for at kula ikke er defekt? Regn ut og velg ett alternativ."
NN = "Kva er sannsynet for at kula ikkje er defekt? Rekn ut og vel eitt alternativ."
EN = "What is the probability that the ball is not defective? Compute the value and answer."


def section(number, text="", parent=None):
    return ExtractedSection(number=number, regions=BAND, text=text, parent_number=parent)


def version(text):
    return [
        section("1", text),
        section("1a", text, "1"),
        section("1b", text, "1"),
        section("2", text),
    ]


def numbers(sections):
    return [s.number for s in sections]


# --- language dedupe ---------------------------------------------------------


def test_a_trilingual_exam_yields_one_copy_of_each_task():
    sections = version(NB) + version(NN) + version(EN)

    kept = keep_preferred_language(sections)

    assert numbers(kept) == ["1", "1a", "1b", "2"]
    assert all(s.text == NB for s in kept)


def test_the_preferred_language_decides_which_copy_is_kept():
    sections = version(NB) + version(NN) + version(EN)
    assert keep_preferred_language(sections, Language.NYNORSK)[0].text == NN
    assert keep_preferred_language(sections, Language.ENGLISH)[0].text == EN


def test_the_order_of_the_versions_in_the_document_does_not_matter():
    sections = version(EN) + version(NB)
    assert keep_preferred_language(sections)[0].text == NB


def test_english_is_kept_when_the_preferred_language_is_not_in_the_exam():
    sections = version(NN) + version(EN)
    assert keep_preferred_language(sections, Language.BOKMAL)[0].text == EN


def test_a_single_language_exam_is_left_as_it_is():
    sections = version(NB)
    assert keep_preferred_language(sections) == sections


def test_numbering_that_restarts_in_the_same_language_is_not_a_translation():
    # Part A has tasks 1-2 and part B starts again at 1, all in bokmål.
    sections = version(NB) + version(NB)
    assert keep_preferred_language(sections) == sections


def test_versions_whose_language_cannot_be_told_are_all_kept():
    sections = version("x = 2") + version("y = 3")
    assert keep_preferred_language(sections) == sections


def test_versions_are_runs_in_which_no_top_level_number_repeats():
    sections = version(NB) + version(EN)
    assert [numbers(v) for v in split_versions(sections)] == [
        ["1", "1a", "1b", "2"],
        ["1", "1a", "1b", "2"],
    ]
    assert split_versions([]) == []


# --- solutions ---------------------------------------------------------------


def test_solutions_are_matched_to_tasks_by_number():
    tasks = [section("1"), section("1a", parent="1"), section("1b", parent="1"), section("2")]
    solutions = [
        section("1", "intro"),
        section("1a", "svar a", "1"),
        section("1b", "svar b", "1"),
        section("2", "svar 2"),
    ]

    matched = match_solutions(tasks, solutions)

    assert {number: [s.text for s in found] for number, found in matched.items()} == {
        "1": ["intro"],
        "1a": ["svar a"],
        "1b": ["svar b"],
        "2": ["svar 2"],
    }


def test_number_matching_ignores_case_dots_and_spaces():
    matched = match_solutions([section("3B")], [section("3 b.", "svar")])
    assert [s.text for s in matched["3B"]] == ["svar"]


def test_a_task_without_parts_gets_all_parts_of_its_solution():
    tasks = [section("3")]
    solutions = [section("3", "intro"), section("3a", "del a", "3"), section("3b", "del b", "3")]
    assert [s.text for s in match_solutions(tasks, solutions)["3"]] == ["intro", "del a", "del b"]


def test_a_task_with_parts_does_not_swallow_its_parts_solutions():
    tasks = [section("3"), section("3a", parent="3")]
    solutions = [section("3", "intro"), section("3a", "del a", "3")]
    assert [s.text for s in match_solutions(tasks, solutions)["3"]] == ["intro"]


def test_tasks_without_a_solution_are_simply_absent():
    matched = match_solutions([section("1"), section("2")], [section("2", "svar")])
    assert list(matched) == ["2"]
    assert match_solutions([section("1")], []) == {}


# --- topics ------------------------------------------------------------------


def topics(*names):
    return [Topic(subject_code="ISTT1003", name=name) for name in names]


def match(title, *names):
    found = matching_topic(title, topics(*names))
    return None if found is None else found.name


def test_a_title_that_is_already_a_topic_reuses_it_whatever_the_case():
    assert match("hendelser og  SANNSYNLIGHET", "Hendelser og sannsynlighet") == (
        "Hendelser og sannsynlighet"
    )
    assert find_topic(" normalfordeling ", topics("Normalfordeling")).name == "Normalfordeling"
    assert find_topic("Varians", topics("Normalfordeling")) is None


def test_inflected_and_extended_titles_reuse_the_existing_topic():
    assert match("Normalfordelingen", "Normalfordeling") == "Normalfordeling"
    assert match("Hypotesetesting", "Hypotesetest") == "Hypotesetest"
    assert match("Lineær regresjon", "Enkel lineær regresjon") == "Enkel lineær regresjon"
    assert match("Regresjon", "Enkel lineær regresjon") == "Enkel lineær regresjon"
    assert match("Poissonfordeling", "Poissonfordelt stokastisk variabel") == (
        "Poissonfordelt stokastisk variabel"
    )


def test_titles_that_only_share_a_word_are_different_topics():
    assert match("Betinget sannsynlighet", "Hendelser og sannsynlighet") is None
    assert match("Kaffekopper", "Normalfordeling", "Hypotesetest") is None


def test_a_compound_word_is_not_the_word_it_starts_with():
    assert match("Sannsynlighetsfordelinger", "Betinget sannsynlighet") is None
    assert match("Sannsynlighet", "Sannsynlighetsfordelinger") is None


def test_small_words_do_not_make_a_match():
    assert match("Forventning og varians", "Hendelser og sannsynlighet") is None
    assert match("Bremser i bil", "Lakselus i oppdrett") is None


def test_the_closest_of_several_matching_topics_wins():
    assert match("Lineær regresjon", "Regresjon", "Enkel lineær regresjon") == (
        "Enkel lineær regresjon"
    )


def test_no_title_or_no_topics_means_no_match():
    assert match("", "Normalfordeling") is None
    assert match("Normalfordeling") is None
