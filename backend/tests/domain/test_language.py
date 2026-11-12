import pytest

from levet.domain.language import Language, choose_version, detect_language

BOKMAL = (
    "Oppgave 2. En bedrift produserer kuler. Hva er sannsynligheten for at en tilfeldig valgt "
    "kule ikke er defekt? Velg ett alternativ. Regn ut verdien og oppgi svaret med to desimaler."
)
NYNORSK = (
    "Oppgåve 2. Ei bedrift produserer kuler. Kva er sannsynet for at ei tilfeldig vald "
    "kule ikkje er defekt? Vel eitt alternativ. Rekn ut verdien og oppgje svaret med to desimalar."
)
ENGLISH = (
    "Problem 2. A company produces balls. What is the probability that a randomly chosen "
    "ball is not defective? Select one alternative. Compute the value and give your answer."
)


@pytest.mark.parametrize(
    ("text", "language"),
    [(BOKMAL, Language.BOKMAL), (NYNORSK, Language.NYNORSK), (ENGLISH, Language.ENGLISH)],
)
def test_detects_the_three_exam_languages(text, language):
    assert detect_language(text) is language


def test_the_heading_word_alone_is_enough_to_tell_the_norwegian_forms_apart():
    assert detect_language("Oppgave 3") is Language.BOKMAL
    assert detect_language("Oppgåve 3") is Language.NYNORSK


@pytest.mark.parametrize("text", ["", "a) 0.5  b) 0.7  c) 1.2", "P(X ≤ 3) = 0.42", "og er til for"])
def test_text_without_telling_words_has_no_detectable_language(text):
    assert detect_language(text) is None


def test_sub_task_labels_do_not_count_as_english():
    # "a" is an English word, but "a)" in front of every sub-task is not English.
    text = "a) Hva er forventningen? b) Hva er variansen? c) Regn ut. d) Vis at. a) a) a) a)"
    assert detect_language(text) is Language.BOKMAL


def test_the_preferred_language_is_chosen_when_present():
    versions = [Language.BOKMAL, Language.NYNORSK, Language.ENGLISH]
    assert choose_version(versions) == 0
    assert choose_version(versions, preferred=Language.NYNORSK) == 1
    assert choose_version(versions, preferred=Language.ENGLISH) == 2


def test_english_is_the_fallback_when_the_preferred_language_is_missing():
    assert choose_version([Language.NYNORSK, Language.ENGLISH]) == 1
    assert choose_version([Language.ENGLISH, Language.NYNORSK], preferred=Language.BOKMAL) == 0


def test_the_first_version_is_kept_when_neither_preferred_nor_fallback_exists():
    assert choose_version([Language.NYNORSK, None]) == 0


def test_choosing_among_no_versions_is_an_error():
    with pytest.raises(ValueError):
        choose_version([])
