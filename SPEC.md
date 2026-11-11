# Project: levet — self-hosted exam-practice web app

## Purpose
Single-user web app (installable PWA, works on phone + laptop) for exam prep.
I upload an exam PDF once (optionally its solution PDF). The app extracts every
task, assigns topics, stores everything, and from then on manages practice:
what to practise next, logging attempts, tracking weakness per topic, and
resurfacing failed tasks Anki-style. I should never need to open the PDF again.

## Tech stack
- Backend: Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, SQLite (one file).
- PDF: PyMuPDF (render pages to PNG at ~150 DPI, crop figures).
- Extraction + topic tagging: Anthropic Claude API (vision), structured JSON
  output validated with Pydantic. API key via env var.
- Background jobs: simple in-process task queue (FastAPI BackgroundTasks or
  a small worker thread). No Redis/Celery.
- Scheduling: `fsrs` Python package for spaced-repetition of tasks.
- Frontend: React + Vite + TypeScript + Tailwind, KaTeX for math,
  react-markdown for task text. PWA manifest + service worker.
- Deploy: one Docker image (backend serves built frontend), docker-compose,
  volume for DB + files. Must run well on a laptop server with 8 GB RAM.
- Auth: single user, password login with session cookie (it's exposed on my domain).
- Tests: pytest for domain, scoring, and extraction-parsing logic.

## Architecture
Light hexagonal: `domain` (entities, scoring, scheduling — pure Python, no I/O),
`application` (use cases + ports: TaskRepository, ExtractionService, FileStore),
`adapters` (FastAPI routes, SQLAlchemy repos, Claude extractor, local file store).
The Claude extractor must sit behind an ExtractionService port so it can be swapped.

## Domain model
- Subject: course code (natural key, e.g. IDATT2202), name, exam date.
- Topic: belongs to subject; name; created/merged automatically by the app.
- Exam: subject, label (e.g. "Høst 2023"), original PDF, optional solution PDF,
  status (processing / needs_review / ready / failed).
- Task: exam, task number ("3b"), parent task (for sub-tasks, so shared context
  from "Oppgave 3" is shown with 3a/3b), text as Markdown + LaTeX, figure images,
  points, topics (1–3), solution text (if solution PDF given), source page numbers.
- Attempt: immutable — task, timestamp, self-grade (Again/Hard/Good/Easy) mapped
  to a score 0–1, time spent, optional typed answer, optional note.
- Review state per task: FSRS card state (due date, stability, difficulty).

## Ingestion pipeline (the critical feature)
1. Upload exam PDF (+ optional solution PDF), choose subject. Returns immediately;
   processing runs in background with progress shown in UI.
2. Render each page to PNG. Send pages to Claude (batched) with a prompt asking for
   JSON: tasks with number, parent, text (Markdown/LaTeX), points, page,
   bounding boxes of figures/tables/code that must be shown as images.
3. Language dedupe: NTNU exams often repeat all tasks in bokmål, nynorsk and English.
   Detect duplicate versions and keep one (preferred language configurable,
   default bokmål, fall back to English).
4. Crop figures from page renders using returned bounding boxes.
5. If solution PDF: extract solutions and match them to tasks by number.
6. Topic tagging: send the subject's existing topic list + new tasks to Claude;
   reuse existing topics where they fit, create new ones only when needed, so topics
   stay consistent across exams.
7. Exam goes to `needs_review`: a review screen shows each extracted task next to
   its original page image. I can edit text, fix topics, merge/split tasks,
   delete junk, then "Approve all". Only approved tasks enter practice.
8. Store the original PDF and page images; never require re-upload.
Handle failures: retry once, then mark exam `failed` with the error visible and a
"retry" button. Never silently drop pages.

## Practice logic
- Weakness per topic in [0,1]:
  weakness = 0.6*(1 - recency-weighted mastery) + 0.25*staleness + 0.15*coverage gap.
  Mastery uses exponential decay (half-life 7 days). Unattempted topics = max weak.
  Multiply by subject urgency (closer exam date ranks higher). Weights configurable.
- "Practise now" queue mixes: (a) FSRS-due tasks I previously failed,
  (b) tasks from the weakest topics, preferring never-attempted ones.
- Practice flow per task: show task (with parent context + figures) → optional timer
  → optional typed answer → reveal solution (if any) → self-grade
  Again/Hard/Good/Easy → next. Keyboard shortcuts on desktop (space, 1–4), large
  tap targets on mobile.
- Modes: "Practise now" (mixed queue), "By topic", "Full mock exam" (all tasks from
  one exam, timed, graded at the end).

## Pages
Dashboard (days to each exam, weakest topics, due count, streak) · Subjects ·
Exams (upload, status, review) · Practice · Topic detail (mastery over time,
tasks, attempts) · Settings (weights, preferred language, API key status).

## Out of scope
Multi-user, AI grading of answers, generating new questions, native mobile apps,
OCR of handwritten answers.

## Acceptance criteria
1. Uploading a typical 10-page NTNU exam produces correctly split tasks with math
   rendered and figures cropped, ready for review in under ~2 minutes.
2. A trilingual exam yields one copy of each task, not three.
3. Topics from a second exam of the same subject reuse topics from the first.
4. After logging attempts, weak topics and failed tasks clearly rise in the queue.
5. Usable on a phone browser and installable as a PWA.
6. `docker compose up` on a fresh machine runs everything; README covers setup,
   env vars, and backups (copy the volume).
7. Unit tests cover scoring, FSRS mapping, language dedupe, and JSON validation.

## How to work
Milestones, stop after each for review:
(1) domain + scoring + tests, (2) DB + upload + page rendering,
(3) Claude extraction + dedupe + review screen, (4) practice flow + FSRS,
(5) dashboard + PWA + Docker. Don't add features outside this spec.
