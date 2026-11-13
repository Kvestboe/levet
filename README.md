# levet

Self-hosted exam practice for one person. Upload an exam PDF once, with its
solution if you have it; the app finds the tasks, and from then on tells you
what to practise next, keeps track of how each topic is going, and brings back
the tasks you failed. It runs in a browser on a phone or a laptop and can be
installed as an app.

The specification the app was built from is in [SPEC.md](SPEC.md).

## Running it

You need Docker with the compose plugin.

```bash
cp .env.example .env
```

Open `.env` and set `LEVET_PASSWORD` to the password you want to log in with.
Then:

```bash
docker compose up -d
```

The app is at http://localhost:8000. The first start builds the image, which
takes a few minutes.

To get going: add a subject with its exam date, upload an exam under Exams,
check the tasks that were found, and approve the exam. The tasks are then in
the practice queue.

### Configuration

Set in `.env` (for Docker) or in the environment:

| Variable | Default | Meaning |
|---|---|---|
| `LEVET_PASSWORD` | (required) | The password you log in with. |
| `LEVET_PORT` | `8000` | Docker only: the port the app is published on. |
| `LEVET_LANGUAGE` | `nb` | Which version to keep of an exam printed in several languages (`nb`, `nn` or `en`; English is the fallback), until you change it on the Settings page. |
| `LEVET_SECRET_KEY` | generated | Signs the login cookie. If unset, a key is generated once and kept with the data. |
| `LEVET_MAX_UPLOAD_MB` | `50` | Largest accepted PDF. |
| `LEVET_SESSION_DAYS` | `30` | How long a login lasts. |
| `LEVET_RENDER_DPI` | `150` | Resolution of the page images. |
| `LEVET_DATA_DIR` | `./data` | Where everything is stored. The image sets it to `/data`. |
| `LEVET_STATIC_DIR` | (none) | Directory with the built frontend for the backend to serve. The image sets it. |

The weights behind the weakness score and the preferred exam language are
changed in the app, on the Settings page.

### On your own domain

Put a reverse proxy that does HTTPS (Caddy, nginx, Traefik, a Cloudflare
tunnel) in front of port 8000. Nothing needs configuring in the app: it sees
from the proxy that the request came over HTTPS and marks the login cookie
`Secure`. Do not expose port 8000 to the internet directly; without HTTPS the
password and the cookie travel in the clear.

After five wrong passwords in a row, further attempts are refused for a
minute.

### Installing it as an app

Over HTTPS (or on `localhost`), the browser offers to install it: "Add to Home
screen" in the browser menu on a phone, or the install icon in the address bar
on a computer. It then opens in its own window. It needs the server to do
anything; without a connection it opens and says so.

### Backups

Everything the app stores is in one Docker volume: the SQLite database, the
uploaded PDFs, and every image. Back up by copying it while the app is
stopped, so that the database is not caught mid-write:

```bash
docker compose stop
docker run --rm -v levet_levet-data:/data -v "$PWD":/backup busybox tar czf /backup/levet-backup.tar.gz -C /data .
docker compose start
```

The volume is named after the directory the compose file is in; check with
`docker volume ls` if yours is not `levet_levet-data`. To restore into an
empty volume:

```bash
docker compose stop
docker run --rm -v levet_levet-data:/data -v "$PWD":/backup busybox tar xzf /backup/levet-backup.tar.gz -C /data
docker compose start
```

### Updating

```bash
git pull
docker compose up -d --build
```

The database is brought up to date automatically at start-up.

## How tasks are extracted

Extraction runs on your own machine and costs nothing: no API key, no model,
no network. The app reads where the text sits on each page, finds task
headings ("Oppgave 3", "Oppg. 3 [15%]", "Problem 3") and "Maks poeng" lines,
and cuts each task out of the pages as images. A task is kept whole, with all
its parts a), b), c), and looks exactly as it did in the exam, formulas and
figures included. Solutions are cut from the solution PDF the same way and
matched to tasks by number.

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

The dashboard shows the days left to each exam, the weakest topics, how many
failed tasks are due and your streak of days practised. Each topic has a page
with its mastery over time, its tasks and every attempt at them.

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
on start-up, in `backend/data`.

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

`npm run build` writes the app to `frontend/dist`. Point `LEVET_STATIC_DIR`
at that directory and the backend serves it, which is how the Docker image
runs.

### Layout

```
backend/src/levet/
  domain/        entities, scoring, scheduling; pure Python, no I/O
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

The container installs the exact versions in `backend/requirements.txt`.
After changing dependencies in `backend/pyproject.toml`, regenerate it with
the command at the top of that file.
