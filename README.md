# levet

Self-hosted exam-practice web app. Upload an exam PDF once; the app keeps the
tasks and manages what to practise next. The full specification is in
[SPEC.md](SPEC.md).

The app is being built in milestones. So far: the domain model and scoring,
the database, login, subjects, and exam upload with page rendering.

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

Everything the app stores lives in `LEVET_DATA_DIR`.

## Layout

```
backend/src/levet/
  domain/        entities and scoring; pure Python, no I/O
  application/   use cases and the ports they depend on
  adapters/      database, file store, PDF renderer, background worker, HTTP API
frontend/src/    React app
```

Database changes go through Alembic. After changing
`backend/src/levet/adapters/db/models.py`:

```bash
cd backend
.venv/bin/alembic revision --autogenerate -m "describe the change"
```
