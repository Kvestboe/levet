"""Turning extracted sections into tasks: language versions, solutions, topics.

Pure functions; the processing pipeline calls them in this order.
"""

import re
from collections.abc import Sequence

from levet.application.ports import ExtractedSection
from levet.domain import Language, Topic
from levet.domain.language import DEFAULT_LANGUAGE, choose_version, detect_language

# --- language versions -------------------------------------------------------


def split_versions(sections: Sequence[ExtractedSection]) -> list[list[ExtractedSection]]:
    """Group sections into runs in which no top-level task number repeats.

    A trilingual exam prints tasks 1..n three times, so its sections fall into
    three runs.
    """
    versions: list[list[ExtractedSection]] = [[]]
    seen: set[str] = set()
    for section in sections:
        if section.parent_number is None:
            if section.number in seen:
                versions.append([])
                seen = set()
            seen.add(section.number)
        versions[-1].append(section)
    return [version for version in versions if version]


def keep_preferred_language(
    sections: Sequence[ExtractedSection], preferred: Language = DEFAULT_LANGUAGE
) -> list[ExtractedSection]:
    """Keep one language version of the tasks: the preferred one, else English, else the first.

    Runs are only treated as translations of each other when they are written
    in different languages. A document whose numbering merely restarts (say, in
    a second part) is left whole.
    """
    versions = split_versions(sections)
    if len(versions) < 2:
        return list(sections)
    languages = [
        detect_language("\n".join(section.text for section in version)) for version in versions
    ]
    known = [language for language in languages if language is not None]
    if len(known) < 2 or len(set(known)) != len(known):
        return list(sections)
    return versions[choose_version(languages, preferred)]


# --- solutions ---------------------------------------------------------------


def match_solutions(
    tasks: Sequence[ExtractedSection], solutions: Sequence[ExtractedSection]
) -> dict[str, list[ExtractedSection]]:
    """Solution sections for each task, by task number.

    A task gets the solution section with its own number. A task that has no
    sub-tasks also gets the solution's sub-sections, for when the solution
    splits a task further than the exam does.
    """
    by_number: dict[str, list[ExtractedSection]] = {}
    children: dict[str, list[ExtractedSection]] = {}
    for solution in solutions:
        by_number.setdefault(_normalize_number(solution.number), []).append(solution)
        if solution.parent_number is not None:
            children.setdefault(_normalize_number(solution.parent_number), []).append(solution)

    has_subtasks = {
        _normalize_number(task.parent_number) for task in tasks if task.parent_number is not None
    }
    matched: dict[str, list[ExtractedSection]] = {}
    for task in tasks:
        number = _normalize_number(task.number)
        found = list(by_number.get(number, []))
        if number not in has_subtasks:
            found.extend(children.get(number, []))
        if found:
            matched[task.number] = found
    return matched


def _normalize_number(number: str) -> str:
    return re.sub(r"[\s.()]", "", number).lower()


# --- topics ------------------------------------------------------------------

_TOPIC_STOPWORDS = frozenset(
    "og i på av for med til om en et ei den det de som er fra ved the and of in for to a an".split()
)
_TOPIC_WORD = re.compile(r"[^\W\d_]+")


def normalize_topic_name(name: str) -> str:
    """Form in which two topic names count as the same name."""
    return " ".join(name.casefold().split())


def find_topic(name: str, topics: Sequence[Topic]) -> Topic | None:
    """The topic with this name, ignoring case and spacing."""
    wanted = normalize_topic_name(name)
    return next((topic for topic in topics if normalize_topic_name(topic.name) == wanted), None)


def matching_topic(title: str, topics: Sequence[Topic]) -> Topic | None:
    """An existing topic that a task with this title belongs to, if any.

    A topic matches when every significant word of the shorter of the two names
    has a counterpart in the other. Words are counterparts when they differ
    only in their ending ("normalfordeling" and "normalfordelingen",
    "hypotesetest" and "hypotesetesting"), but not when one merely starts with
    the other ("sannsynlighet" and "sannsynlighetsfordelinger"). So "Regresjon"
    and "Enkel lineær regresjon" are the same topic, while "Betinget
    sannsynlighet" and "Hendelser og sannsynlighet" are not.
    """
    exact = find_topic(title, topics)
    if exact is not None:
        return exact

    words = _topic_words(title)
    if not words:
        return None
    best: tuple[int, str, Topic] | None = None
    for topic in topics:
        topic_words = _topic_words(topic.name)
        if not topic_words:
            continue
        shorter, longer = sorted((words, topic_words), key=len)
        if all(any(_same_word(a, b) for b in longer) for a in shorter):
            candidate = (-len(shorter), normalize_topic_name(topic.name), topic)
            if best is None or candidate[:2] < best[:2]:
                best = candidate
    return None if best is None else best[2]


def _topic_words(name: str) -> list[str]:
    words = [word.casefold() for word in _TOPIC_WORD.findall(name)]
    return [word for word in words if len(word) > 3 and word not in _TOPIC_STOPWORDS]


def _same_word(a: str, b: str) -> bool:
    shorter, longer = sorted((a, b), key=len)
    common = 0
    for x, y in zip(shorter, longer, strict=False):
        if x != y:
            break
        common += 1
    return common >= max(5, round(0.7 * len(longer)))
