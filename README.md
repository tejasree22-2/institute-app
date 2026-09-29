# Institute App — Coding Task MVP

A demo build of the Coding-task slice described in `docs/SPECIFICATION.md`: instructors build a
library of coding questions, assign them to batches, and students solve them in an in-browser
editor with real server-side Python execution. The database ships pre-seeded with sample
instructors, students, batches, questions and submissions so the UI can be reviewed immediately.

## Quick start

**1. Backend (FastAPI + SQLite), from `institute-app/`:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python3 scripts/init_db.py          # creates + seeds backend/data/app.db (safe to re-run)
# without DATABASE_URL the app uses that local SQLite file; to use Supabase instead, copy
# .env.example to .env and fill in DATABASE_URL (.env is gitignored; real env vars override it)
cd backend
uvicorn app.main:app --reload --port 8010
```
If port 8010 is already taken on your machine, run on another port (e.g. `--port 8020`) and set
`window.API_BASE` in `frontend/js/api.js` (or via `<script>window.API_BASE = "http://localhost:8010"</script>`
before `api.js` loads) to match. Also update `CORS_ORIGINS` if the frontend runs on a non-default port.

**2. Frontend (static files), from `institute-app/frontend/`:**
```bash
python3 -m http.server 8080
```
Then open `http://localhost:8080/index.html`.

## Worksheets from the worksheet repo

The worksheets published at `aikaryashala.com/first-steps/` (Ganitham, Coding, ...) are imported
with `scripts/sync_worksheets.py`, which reads the `docs/` folder of
[aikaryashala/first-steps](https://github.com/aikaryashala/first-steps/tree/main/docs). Every item
in a subject's `index.html` (a task with its `[Questions]` / `[ans]` links, or a `Ref` page) becomes
a verified worksheet under that subject, in the same order, and students see them laid out like that
index. The instructor picks, per file, which batches can open it; the subject folder is
mirrored into `backend/data/worksheet_content/` and served by the backend behind short-lived links,
so a page opens only for batches it was assigned to (answer pages stay locked otherwise).

To pull the repo, an instructor clicks **Sync from GitHub** in **Library → Worksheets** (there is no
automatic sync). New files pushed to the repo then show up in the Library, ready to be opened to
batches. After each sync a **Sync check** lists every item of the repo index: new or already
in the Library, and for each file whether it is in the repo, gone from it (the saved copy is used),
or missing. Students browse worksheets like the site: *Practice* → subject (e.g. Ganitham) → the
subject's index, showing only the files opened to their batch. `WORKSHEET_REPO_URL` points it at another repo or branch.
The same sync can also be run from the command line:

```bash
python3 scripts/sync_worksheets.py                          # from the GitHub repo (main branch)
python3 scripts/sync_worksheets.py --repo ../first-steps    # from a local clone (git pull first)
python3 scripts/sync_worksheets.py --url https://aikaryashala.com/first-steps/   # from the published site
python3 scripts/sync_worksheets.py --subject ganitham       # only one subject
```
Existing worksheets are updated in place and
keep their batch assignments and student progress. `scripts/init_db.py` wipes the DB, so re-run the
sync after it.

## Demo accounts (seeded by `scripts/init_db.py`)

| Role | Email | Password | Batch |
|---|---|---|---|
| Instructor | anita@institute.edu | instructor123 | — |
| Student | ravi@institute.edu | student123 | Python Basics - Morning |
| Student | priya@institute.edu | student123 | Python Basics - Morning |
| Student | aman@institute.edu | student123 | Python Basics - Morning |
| Student | sneha@institute.edu | student123 | Python Basics - Evening |
| Student | karthik@institute.edu | student123 | Python Basics - Evening |

The seed includes 5 verified coding questions (assigned across both batches), one unverified
draft question (to show the "needs verify" state in the Library), sample submissions with a mix
of All passed / Partial / Not started statuses, and a couple of student notes — so Tasks,
Library, Batches and Performance all have realistic content the moment you log in.

## Deploying (Supabase + Render, all free tiers)

| Piece | Where | Notes |
|---|---|---|
| Database | Supabase Postgres | holds everything: data, instructor uploads and the synced worksheet pages (`stored_files` table) |
| Backend | Render web service (native Python) | stateless, so Render's free plan works (its disk is wiped on restart) |
| Frontend | Render static site | `frontend/` as is; `js/config.js` gets the API URL at build time |

**1. Supabase.** Create a project (note the database password). Click **Connect** at the top, choose
**Session pooler**, and copy the URI:
`postgresql://postgres.<project-ref>:[YOUR-PASSWORD]@aws-0-<region>.pooler.supabase.com:5432/postgres`.
Put your password in place of `[YOUR-PASSWORD]` (URL-encode characters like `@`, `#`, `/`). Use the
Session pooler, not the "Direct connection": the direct host is IPv6-only and Render can't reach it.
The app creates its tables itself on first start and turns on row level security for them, so
Supabase's public REST API can't read them.

**2. Render.** Push the project to GitHub, then **New → Blueprint** → pick the repo (`render.yaml`).
When asked, enter:
- `DATABASE_URL` (api) = the Supabase URI from step 1
- `CORS_ORIGINS` (api) = `https://institute-app-web.onrender.com`
- `API_URL` (web) = `https://institute-app-api.onrender.com`

`JWT_SECRET` is generated for you. If Render gives a service a different URL (it adds a suffix when a
name is taken), fix the value under that service's **Environment** tab and redeploy the static site.

**3. First login.** Check `https://<api>/health` says `"code_sandbox": "ok (…)"` (if it says
`unavailable`, Run/Submit answer 503 instead of running code unprotected). In the API service's
**Shell** tab create the first instructor:
`python3 scripts/create_instructor.py --name "Your Name" --email you@example.com`
(or run that locally with the same `DATABASE_URL` set). Then open the frontend, log in, click
**Sync from GitHub** in Library → Worksheets, and create batches and students.

Free-tier limits to know: the Render service sleeps after ~15 minutes idle (the next request takes
~30–60 s to wake it); Supabase's free database is 500 MB and a project with no activity for a week is
paused (resume it from the dashboard). Uploads count toward the 500 MB, so keep them modest.
`scripts/init_db.py` (demo data) refuses to run with `APP_ENV=production`, and refuses to touch a
non-SQLite database without `--force`.

## What's simplified vs. the full spec

- **Code execution sandboxing** (`backend/app/services/code_runner.py`, `sandbox.py`): each submission
  runs as a subprocess in its own temp dir with an empty environment, a wall-clock timeout, stdout
  cap and rlimits on memory, processes and file size, inside a Landlock + seccomp sandbox that needs
  no root: it can read only the Python install and system libraries, write only its temp dir, open
  no sockets and signal no other process. Instead of the spec's dedicated `coderunner` OS user
  (§6.2, `scripts/setup_runner_user.sh`), which a Render native service can't create.
- Everything else (auth, roles, batches, question authoring + verification gate, assignment,
  the unified student task list, Run/Submit semantics, hidden-test-case handling, notes, and the
  performance views) is implemented against the real API surface in §8, backed by SQLite (local) or Postgres (Supabase) via
  SQLAlchemy — not mocked in the frontend.

## Project layout

See `docs/SPECIFICATION.md` §10 for the intended structure; this build follows it directly.
