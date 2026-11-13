# levet

Self-hosted exam-practice web app. Upload an exam PDF once; the app keeps the
tasks and manages what to practise next. The full specification is in
[SPEC.md](SPEC.md).

The app is being built in milestones. So far: the domain model and scoring,
the database, login, subjects, exam upload with page rendering, task
extraction, the review screen, and practice. The dashboard, installable app
and Docker image come next.

## How tasks are extracted

Extraction runs locally and costs nothing: no API key, no model, no network.
The app reads where the text sits on each page, finds task headings
("Oppgave 3", "Oppg. 3 [15%]", "Problem 3"), sub-task labels ("a)", "b)") and
Inspera's answer prompts, and cuts each task out of the page as an image. A
task therefore looks exactly as it did in the exam, formulas and figures
included. Solutions are cut from the solution PDF the same way and matched to
tasks by number.

This needs a PDF with real text in it. A scanned exam has none; it comes in
as one task per page, which can be split by hand in the review screen.

Topics are suggested from task titles and reuse the subject's existing
topics when the names match. They can be changed per task, and renamed or
merged for the whole subject, in the review screen.

## How practice works

Only tasks of approved exams are practised. There are three modes:

- **Practise now** serves one task at a time from a queue that alternates
  between tasks you have failed and that are due again, and tasks from your
  weakest topics, new ones first. A topic's weakness combines how well its
  tasks went (recent attempts count more), how long since you practised it and
  how much of it you have not tried; topics of a subject whose exam is close
  rank higher.
- **By topic** is the same queue limited to one topic.
- **Mock exam** is a whole exam against the clock, graded against the
  solutions at the end.

You grade yourself Again, Hard, Good or Easy. The grade schedules the task
with FSRS, the algorithm Anki uses: a failed task returns within minutes, one
that went well after days. On a keyboard, space shows the solution and 1-4
grade.

## Development

Two processes: the Python backend and the Vite dev server for the frontend.

### Backend

Requires Python 3.12 or newer.

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
LEVET_PASSWORD=choose-a-password .venv/bin/uvicorn levet.main:create_app --factory --reload
```

The API listens on http://127.0.0.1:8000. The database is created and migrated
on start-up.

```bash
.venv/bin/pytest        # tests
.venv/bin/ruff check .  # lint
```

### Frontend

Requires Node 22 or newer.

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Requests to `/api` are forwarded to the backend;
set `LEVET_API` if it runs somewhere other than `http://127.0.0.1:8000`.

## Configuration

Environment variables read by the backend:

| Variable | Default | Meaning |
|---|---|---|
| `LEVET_PASSWORD` | (required) | The login password. |
| `LEVET_DATA_DIR` | `./data` | Where the SQLite database, uploaded PDFs and page images are stored. |
| `LEVET_SECRET_KEY` | generated | Signs session cookies. If unset, a key is generated and kept in the data directory. |
| `LEVET_RENDER_DPI` | `150` | Resolution of the rendered page images. |
| `LEVET_MAX_UPLOAD_MB` | `50` | Largest accepted PDF. |
| `LEVET_SESSION_DAYS` | `30` | How long a login lasts. |
| `LEVET_LANGUAGE` | `nb` | Which version to keep of an exam printed in several languages: `nb`, `nn` or `en`. English is the fallback. |

Everything the app stores lives in `LEVET_DATA_DIR`.

## Layout

```
backend/src/levet/
  domain/        entities and scoring; pure Python, no I/O
  application/   use cases and the ports they depend on
  adapters/      database, file store, PDF renderer, task extractor, background worker, HTTP API
frontend/src/    React app
```

Database changes go through Alembic. After changing
`backend/src/levet/adapters/db/models.py`:

```bash
cd backend
.venv/bin/alembic revision --autogenerate -m "describe the change"
```
