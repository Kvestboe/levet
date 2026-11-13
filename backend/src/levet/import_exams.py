"""Import a folder of exam PDFs in one go.

    python -m levet.import_exams FOLDER --subject CODE [--name NAME] [--topics FILE] [--approve]

Exams are found by file name: ``...Eksamen<tag>.pdf`` (H24 is "Høst 2024", K23
"Kont 2023"), ``...ProveEksamen<tag>.pdf`` (a practice exam), and the solution
to an exam is ``...LF<tag>.pdf`` in the same folder. Each exam is uploaded and
processed as if it had been uploaded in the app. Exams whose label the subject
already has are left alone, so the command can be run again safely.

``--topics`` names a JSON file giving the topics of each task, by exam tag and
task number; these replace the topics suggested from the task titles::

    {"H24": {"1": ["Beskrivende statistikk"], "2": ["Betinget sannsynlighet"]}}

With ``--approve`` every exam that ends up with a topic on each task is
approved, which puts it in the practice queue.

Uses the same settings as the app (LEVET_DATA_DIR and so on); LEVET_PASSWORD
is not needed. Stop the app while it runs.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from levet.application.errors import ApplicationError
from levet.bootstrap import Container, build_container
from levet.config import Settings
from levet.domain import ExamStatus

_EXAM = re.compile(r"(?P<practice>Prove)?Eksamen(?P<tag>[HK]\d\d)\.pdf$", re.IGNORECASE)
_TERMS = {"H": "Høst", "K": "Kont"}


@dataclass(frozen=True, slots=True)
class FoundExam:
    path: Path
    tag: str  # "H24"; "ProveH21" for a practice exam
    label: str
    solution: Path | None


def find_exams(folder: Path) -> list[FoundExam]:
    """The exams in a folder, with their solutions, oldest first."""
    found: list[FoundExam] = []
    for path in folder.glob("*.pdf"):
        match = _EXAM.search(path.name)
        if not match:
            continue
        term, year = match["tag"][0].upper(), match["tag"][1:]
        label = f"{_TERMS[term]} 20{year}"
        solution: Path | None = None
        tag = f"{term}{year}"
        if match["practice"]:
            label = f"Prøveeksamen {label.lower()}"
            tag = f"Prove{tag}"
        else:
            candidates = list(folder.glob(f"*LF{term}{year}.pdf"))
            solution = candidates[0] if candidates else None
        found.append(FoundExam(path, tag, label, solution))
    return sorted(found, key=lambda e: (e.tag[-2:], e.tag[-3] == "H", "Prove" in e.tag))


def import_exam(
    container: Container,
    subject: str,
    exam: FoundExam,
    topics: dict[str, list[str]],
    approve: bool,
) -> str:
    """Upload, process, tag and optionally approve one exam. Returns a line for the report."""
    existing = {view.exam.label for view in container.exams.list_all(subject)}
    if exam.label in existing:
        return f"{exam.label}: already there, left alone"

    uploaded = container.exams.upload(
        subject,
        exam.label,
        exam.path.read_bytes(),
        exam.solution.read_bytes() if exam.solution else None,
    )
    # Processed here and now rather than by the app's background worker.
    container.processor.process(uploaded.id)
    view = container.review.tasks(uploaded.id)
    if view.exam.status is not ExamStatus.NEEDS_REVIEW:
        return f"{exam.label}: FAILED: {view.exam.error}"

    for task in view.tasks:
        names = topics.get(task.number)
        if names:
            container.review.update_task(task.id, topic_names=names)

    solved = sum(1 for task in view.tasks if task.has_solution)
    line = f"{exam.label}: {len(view.tasks)} tasks, {solved} with solution"
    if approve:
        try:
            container.review.approve(uploaded.id)
            line += ", approved"
        except ApplicationError as exc:
            line += f", left for review ({exc})"
    return line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m levet.import_exams", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument("folder", type=Path)
    parser.add_argument("--subject", required=True, help="course code, e.g. ISTT1003")
    parser.add_argument("--name", help="subject name, if the subject does not exist yet")
    parser.add_argument("--topics", type=Path, help="JSON file with the topics of each task")
    parser.add_argument("--approve", action="store_true", help="approve the imported exams")
    args = parser.parse_args(argv)

    # The password guards the web app, which this does not start.
    env = {"LEVET_PASSWORD": "unused", **os.environ}
    container = build_container(Settings.from_env(env))
    try:
        subject = args.subject.strip().upper()
        if all(s.code != subject for s in container.subjects.list_all()):
            if not args.name:
                parser.error(f"there is no subject {subject}; give --name to create it")
            container.subjects.create(subject, args.name)

        topics = json.loads(args.topics.read_text()) if args.topics else {}
        exams = find_exams(args.folder)
        if not exams:
            print(f"No exams found in {args.folder}", file=sys.stderr)
            return 1
        for exam in exams:
            print(import_exam(container, subject, exam, topics.get(exam.tag, {}), args.approve))
        return 0
    finally:
        container.engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
