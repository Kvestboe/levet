"""Telling bokmål, nynorsk and English apart, and choosing between versions.

NTNU exams often print every task three times, once per language. Detection
counts words that are typical of exactly one of the three; the words the two
Norwegian forms share ("og", "er", "til" ...) say nothing and are left out.
"""

import re
from collections.abc import Sequence
from enum import StrEnum


class Language(StrEnum):
    BOKMAL = "nb"
    NYNORSK = "nn"
    ENGLISH = "en"


DEFAULT_LANGUAGE = Language.BOKMAL
FALLBACK_LANGUAGE = Language.ENGLISH

_DISTINCT: dict[Language, frozenset[str]] = {
    Language.BOKMAL: frozenset(
        """
        ikke hva hvilke hvilken hvilket hvor hvordan hvorfor jeg en et fra noen bare mer
        dere de være ble uten følgende oppgave oppgaven oppgavene deloppgave
        deloppgaver hver antall tall velg ett regn beregn gjør se mye flere
        sannsynligheten løsning løsningsforslag hjelpemidler tillatte
        """.split()
    ),
    Language.NYNORSK: frozenset(
        """
        ikkje kva kvar kvifor korleis eg ein eit frå nokon nokre berre meir
        dykk dei vere vert vart utan følgjande oppgåve oppgåva oppgåvene deloppgåve
        deloppgåver tal eitt rekn gjer sjå mykje fleire
        sannsynet løysing løysingsforslag tillatne
        """.split()
    ),
    # Left out on purpose: "for", "to", "a", "problem" and other words that are
    # also Norwegian words or appear as sub-task labels.
    Language.ENGLISH: frozenset(
        """
        the and of is are was were what which that with find show let this these those
        from each exercise question compute determine calculate assume given answer
        answers points value probability following how many you your page pages
        solution allowed
        """.split()
    ),
}

_WORD = re.compile(r"[a-zæøåA-ZÆØÅ]+")


def detect_language(text: str) -> Language | None:
    """The language the text is most likely written in, or None if there is no telling."""
    words = [word.lower() for word in _WORD.findall(text)]
    scores = {
        language: sum(1 for word in words if word in markers)
        for language, markers in _DISTINCT.items()
    }
    best = max(scores, key=lambda language: scores[language])
    if scores[best] == 0:
        return None
    runners_up = sorted(scores.values(), reverse=True)[1]
    if scores[best] == runners_up:
        return None
    return best


def choose_version(
    languages: Sequence[Language | None],
    preferred: Language = DEFAULT_LANGUAGE,
    fallback: Language = FALLBACK_LANGUAGE,
) -> int:
    """Index of the version to keep: the preferred language, else the fallback, else the first."""
    if not languages:
        raise ValueError("there is no version to choose from")
    for wanted in (preferred, fallback):
        if wanted in languages:
            return languages.index(wanted)
    return 0
