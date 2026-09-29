# SPECIFICATION.md

## 1. Project Context

An institute web app where instructors build a **library** of learning content and assign items to **batches** of students. Content lives in six task types: Coding, Video, Worksheet, Interactive, Daily Task, Reading. Every student in a batch sees the tasks assigned to that batch and records their understanding and doubts in a notes area. When a new student joins a batch, they automatically see everything already assigned to that batch. Instructors track each student's progress.

## 2. Current Scope

Only the **Coding task type** is being built now. The other five types are out of scope until Coding works end to end, but the student dashboard is designed as a unified task list so future task types can slot in without redesigning the page.

### In scope

- Login for instructors and students (no self signup).
- Batches; a batch contains one or more students.
- Instructor library of coding questions with test cases.
- Instructor must write a reference solution and pass all test cases before a question can be assigned.
- Assigning coding questions from the library to one or more batches at once.
- Student dashboard as a unified task list (only coding tasks appear for now).
- In-browser code editor and terminal for the student.
- Server-side execution of submitted Python code against test cases.
- Notes area per student per question (autosaved).
- Instructor view of each student's status and submissions per question.

### Out of scope (for this phase)

- Video, Worksheet, Interactive, Daily Task, Reading task types.
- Languages other than Python.
- Password reset, email verification, social login.
- Real-time collaboration or notifications.
- Payments; roles beyond instructor and student; multi-institute support.

## 3. Users and Roles

| Role | Capabilities |
|---|---|
| Instructor | Create/edit coding questions with test cases, write and verify a reference solution, create batches, add/remove students in batches, assign questions to batches, view per-student performance. |
| Student | Log in, see own assigned tasks in one list, open a coding task, write code, run against visible test cases, submit against all test cases, save notes. |

## 4. UI Screens

Seven pages total. Each page below matches an approved mockup.

### Shared
1. **Login** (`index.html`) — email + password. Redirects instructors to Library, students to Tasks.

### Student
2. **Tasks** (`student/tasks.html`) — the student's landing page and unified task list. Header shows batch name and total task count. Body is a vertical list of full-width rectangles, one per assigned task. Each rectangle shows: task title (left, larger) + metadata line (difficulty, test-case count, assigned-at) below it; on the right, stacked, the **type badge** (e.g. "Coding" with a code icon in a coloured pill) and the status pill (see §4.7). Rows are clickable — clicking routes to the workspace for that task type. For MVP, all rows are Coding and route to the Coding Workspace. A footer note tells students that Video, Worksheet, Interactive, Daily Task, and Reading tasks will appear in the same list once their instructor starts assigning them.
3. **Coding workspace** (`student/coding-workspace.html`) — Two-column layout. Left: problem statement + sample input/output. Right (stacked): code editor with the question's starter code pre-loaded, tabbed panel for Test results / Terminal, notes area. Header has **Run** (visible test cases only) and **Submit** (all test cases, persisted).

### Instructor
4. **Library** (`instructor/library.html`) — Landing page. Table of all coding questions in the library. Each row: title, difficulty, test-case count, assignment count. Row actions: Edit, Assign to batch. Header has **New question** button. The Assign modal opens on top of this page — multi-select checkboxes for batches, Cancel and Assign buttons. Assigning a question already assigned to a batch is a no-op.
5. **Question editor** (`instructor/question-editor.html`) — Used for both create and edit. Sections top to bottom: (a) title + difficulty + problem description form fields, (b) test-cases table with Input / Expected output / Hidden checkbox / Delete, plus **Add test case**, (c) **Verify your solution** panel with a code editor and **Run all tests** button that executes the reference solution against every test case and shows per-test pass/fail. **Save to library** is disabled until all test cases pass; a green banner appears when they do. Editing the question body or any test case after verification clears the verified state and re-disables Save.
6. **Batches** (`instructor/batches.html`) — Create a batch (name only), list batches with member counts. Click a batch to see its members and add/remove students.
7. **Performance** (`instructor/performance.html`) — Pick a batch and a question; table of students shows status pill, attempt count, and last-try time. Click a row to see the student's full submission history and the code of their latest submission.

### 4.7 Shared status vocabulary

| Status | Meaning | Colour |
|---|---|---|
| All passed | Latest submission passed every test case | Green |
| N of M passed | Latest submission passed some but not all | Amber |
| Not started / Not attempted | No submission yet | Neutral grey |

### 4.8 Task type badges

Every task on the student's list carries a type badge in the top-right of its row. Each type has its own colour and icon so students can scan by type at a glance. Only Coding is active in this phase; the other five are shown here for design consistency when they are added.

| Type | Icon | Colour |
|---|---|---|
| Coding | `ti-code` | Purple |
| Video | `ti-video` | Red |
| Worksheet | `ti-file-text` | Blue |
| Interactive | `ti-messages` | Green |
| Daily task | `ti-checklist` | Orange |
| Reading | `ti-book` | Yellow |

## 5. Functional Requirements

### 5.1 Authentication
- Login with email + password.
- Session via JWT stored in `localStorage`; sent as `Authorization: Bearer <token>` on every API call.
- Instructor accounts are seeded via a script. Student accounts are created by instructors from the Batches page — no self signup.

### 5.2 Batch management (instructor)
- Create a batch (name only).
- Add existing students to a batch; remove students from a batch.
- Create a student account (name, email, initial password) directly from the add-student flow.
- View the list of batches with member counts.

### 5.3 Coding question authoring (instructor)
- Create a coding question with: title, difficulty (Easy/Medium/Hard), problem description (Markdown), starter code shown to students, language (Python only for now), reference solution (instructor-only, never sent to students).
- Manage test cases inline on the same page. Each test case: stdin, expected stdout, `is_hidden` flag. Hidden test cases run on Submit but their input and expected output are never returned to the student.
- **Verify before saving:** the editor exposes a **Run all tests** button that executes the reference solution against every test case on the server. When all pass, the question is marked verified (`verified_at` timestamp set) and Save to library becomes enabled.
- Editing any of {title, description, starter code, reference solution, test cases} clears `verified_at` — the instructor must re-verify before the question can be assigned.
- Edit or delete existing questions.

### 5.4 Assignment (instructor)
- From the Library page, click **Assign to batch** on any verified question.
- A modal shows all batches with checkboxes; the instructor can pick one or more and click Assign.
- Only verified questions (`verified_at IS NOT NULL`) can be assigned. Unverified questions have the Assign button disabled with a tooltip explaining why.
- Unassign a question from a batch (from the same modal — checkboxes that are already assigned appear checked; unchecking them removes the assignment).
- **When a new student joins a batch, they automatically see every question assigned to that batch**, because assignments live at the batch level, not per student.

### 5.5 Student flow
1. Student logs in and lands on the **Tasks** page — a unified list of every task assigned to their batch(es).
2. Each row is a rectangle showing task title + metadata on the left, and a coloured type badge + status pill on the right.
3. The list is sorted by assigned-at descending (newest first). For MVP, every row has a Coding badge.
4. Clicking a Coding row routes to the **Coding workspace** for that question. In future phases, clicking a Video row routes to a Video workspace, and so on — the Tasks page itself does not change.
5. In the Coding workspace: problem on the left; editor + test-results/terminal + notes on the right. The editor is pre-populated with the question's starter code on first visit; subsequent visits show the student's last saved code.
6. **Run** sends the current code to the server, executes it against **visible** test cases only, returns per-test pass/fail with actual stdout. Does not create a submission record.
7. **Submit** sends the code to the server, executes against **all** test cases (visible + hidden), stores a submission record, updates the student's status for this question, returns the summary. Hidden test cases return only pass/fail — never their stdin or expected stdout.
8. Notes are a single free-text field per (student, question). Autosaved on blur. There is no delete — students can only add or update.

### 5.6 Instructor performance view
- Pick a batch and a question. See a table of students in the batch with: status pill (from §4.7), attempt count, last-try time.
- Click a student's row to see their full submission history (timestamped) and the code of their latest submission.
- Instructors do not see student notes in this phase.

## 6. Code Execution

One runner service is used by both the instructor's **Run all tests** and the student's **Run** / **Submit**. The endpoint layer decides which test cases to send.

### 6.1 Approach
- FastAPI receives `{ code, test_cases }` where each test case has stdin and expected stdout.
- Server writes the code to a temporary file in an isolated working directory under `runner_workdir/`.
- For each test case: run `python3 <file>` as a subprocess with that test's stdin piped in.
- Per-execution limits: **wall-clock timeout 5 seconds**, **stdout capped at 64 KB**, **memory limit 128 MB** (via `resource.setrlimit` on Linux), **no network** (execute under a namespace with `unshare -n` or an equivalent firewall rule).
- Trim trailing whitespace on both actual and expected stdout, then compare exactly. Pass or fail.

### 6.2 Isolation (MVP)
- Run each execution as an unprivileged OS user `coderunner` with no write access outside its per-execution temp dir.
- Network access disabled for the runner user.
- **Note:** subprocess + unprivileged user + rlimit is sufficient for internal testing but is not a full sandbox. Before opening this to real students, migrate execution into per-run Docker containers or `nsjail`. This is tracked as a follow-up, not a blocker.

### 6.3 Response shape
Every execution endpoint returns the same shape (with an optional `submission_id` when persisted):
```json
{
  "submission_id": 42,
  "results": [
    { "test_case_id": 1, "passed": true,  "hidden": false, "actual_output": "9\n", "runtime_ms": 34 },
    { "test_case_id": 2, "passed": false, "hidden": true,  "actual_output": "",     "runtime_ms": 12, "error": "IndexError: list index out of range" }
  ],
  "summary": { "total": 2, "passed": 1, "failed": 1 }
}
```
For hidden test cases returned to a student, `actual_output` and `error` are stripped — only `passed` and `runtime_ms` are visible.

## 7. Data Model (SQLite)

```
users
  id PK, name, email UNIQUE, password_hash, role ('instructor'|'student'), created_at

batches
  id PK, name, created_by FK->users.id, created_at

batch_students
  batch_id FK->batches.id, student_id FK->users.id
  PRIMARY KEY (batch_id, student_id)

coding_questions
  id PK, title, description, difficulty ('easy'|'medium'|'hard'),
  starter_code, reference_solution, language DEFAULT 'python',
  verified_at TIMESTAMP NULL,   -- set on successful verify, cleared on edit
  created_by FK->users.id, created_at, updated_at

test_cases
  id PK, question_id FK->coding_questions.id ON DELETE CASCADE,
  stdin, expected_stdout, is_hidden BOOL, ordering INT

assignments
  id PK, question_id FK->coding_questions.id, batch_id FK->batches.id, assigned_at
  UNIQUE (question_id, batch_id)

submissions
  id PK, student_id FK->users.id, question_id FK->coding_questions.id,
  code, status ('all_passed'|'partial'|'failed'|'error'),
  passed_count INT, total_count INT, submitted_at

submission_results
  id PK, submission_id FK->submissions.id, test_case_id FK->test_cases.id,
  passed BOOL, actual_output, error, runtime_ms

notes
  id PK, student_id FK->users.id, question_id FK->coding_questions.id,
  content, updated_at
  UNIQUE (student_id, question_id)
```

## 8. API Surface

All non-auth endpoints require `Authorization: Bearer <jwt>`. Role checks are enforced server-side.

```
# Auth
POST   /auth/login                             -> { token, user }

# Instructor · users
POST   /users                                  create student  { name, email, password }

# Instructor · batches
GET    /batches
POST   /batches                                { name }
GET    /batches/{id}                           batch + members
POST   /batches/{id}/students                  { student_id }
DELETE /batches/{id}/students/{student_id}

# Instructor · questions
GET    /questions                              list library
POST   /questions                              create  { title, difficulty, description, starter_code, reference_solution, test_cases[] }
GET    /questions/{id}                         full question (instructor view — includes hidden inputs + reference solution)
PUT    /questions/{id}                         update; clears verified_at
DELETE /questions/{id}
POST   /questions/{id}/verify                  runs reference_solution against ALL test cases; on all-pass sets verified_at
POST   /questions/{id}/test-cases              add test case; clears verified_at
PUT    /test-cases/{id}                        update; clears parent's verified_at
DELETE /test-cases/{id}                        clears parent's verified_at

# Instructor · assignments
GET    /batches/{id}/assignments               questions currently assigned to a batch
POST   /assignments                            { question_id, batch_ids: [] }    bulk assign
DELETE /assignments/{id}

# Instructor · performance
GET    /batches/{id}/questions/{qid}/performance     table of members with status
GET    /students/{sid}/questions/{qid}/submissions   history + latest code

# Student · unified task list
GET    /me/tasks                               all assigned tasks across all types, sorted assigned_at desc
                                               each item:
                                               {
                                                 "type": "coding",          # future: "video" | "worksheet" | ...
                                                 "id": 12,                  # question_id for coding
                                                 "title": "Sum of digits",
                                                 "metadata": { "difficulty": "easy", "test_case_count": 4 },
                                                 "status": "partial",
                                                 "status_detail": "2 of 4 passed",
                                                 "assigned_at": "..."
                                               }

# Student · coding-specific
GET    /me/questions/{id}                      question view (student — hides hidden test cases and reference solution)
POST   /me/questions/{id}/run                  runs code against visible test cases only; not persisted
POST   /me/questions/{id}/submit               runs against all test cases; persists submission; returns hidden results as pass/fail only
GET    /me/questions/{id}/notes
PUT    /me/questions/{id}/notes                { content }
```

## 9. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | HTML, CSS, vanilla JS | Multi-page. One HTML file per screen listed in §4. |
| Code editor widget | CodeMirror 6 (loaded via CDN) | Python syntax highlighting. Same widget on instructor and student sides. |
| Backend | FastAPI (Python 3.11+) | Uvicorn as the ASGI server. |
| ORM / DB | SQLAlchemy 2 + SQLite | Single file at `backend/data/app.db`. |
| Auth | JWT via PyJWT, bcrypt for password hashing | |
| Code execution | `subprocess` + `resource.setrlimit` + unprivileged `coderunner` user | Same Ubuntu host as FastAPI in the MVP. |

## 10. Folder Structure

```
institute-app/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                     # FastAPI app + router registration + CORS
│   │   ├── config.py                   # Settings (JWT secret, DB path, exec limits)
│   │   ├── database.py                 # SQLAlchemy engine + session factory
│   │   ├── models.py                   # ORM models matching §7
│   │   ├── schemas.py                  # Pydantic request/response schemas
│   │   ├── auth.py                     # JWT, password hashing, role dependencies
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                 # POST /auth/login
│   │   │   ├── users.py                # POST /users
│   │   │   ├── batches.py              # /batches/*
│   │   │   ├── questions.py            # /questions/*, /test-cases/*, /questions/{id}/verify
│   │   │   ├── assignments.py          # /assignments/*, /batches/{id}/assignments
│   │   │   ├── student.py              # /me/tasks, /me/questions/* (run, submit, notes)
│   │   │   └── performance.py          # instructor performance endpoints
│   │   └── services/
│   │       ├── __init__.py
│   │       └── code_runner.py          # Sandboxed subprocess execution; shared by verify/run/submit
│   ├── data/
│   │   └── app.db                      # SQLite file (gitignored)
│   ├── runner_workdir/                 # Per-execution temp dirs (gitignored)
│   ├── requirements.txt
│   └── README.md
│
├── frontend/
│   ├── index.html                      # Login (screen 1)
│   ├── student/
│   │   ├── tasks.html                  # Screen 2 — unified task list
│   │   └── coding-workspace.html       # Screen 3
│   ├── instructor/
│   │   ├── library.html                # Screen 4 (includes assign modal)
│   │   ├── question-editor.html        # Screen 5 (create + edit + verify)
│   │   ├── batches.html                # Screen 6
│   │   └── performance.html            # Screen 7
│   ├── css/
│   │   ├── main.css                    # Shared styles, layout, buttons, status pills, type badges
│   │   └── workspace.css               # Workspace-specific (editor + panels)
│   ├── js/
│   │   ├── api.js                      # fetch wrapper + JWT header injection
│   │   ├── auth.js                     # Login + logout + role-based redirect
│   │   ├── student/
│   │   │   ├── tasks.js                # Fetch /me/tasks, render list, route by type
│   │   │   └── workspace.js            # CodeMirror init, Run, Submit, notes autosave
│   │   └── instructor/
│   │       ├── library.js              # Library table + assign modal
│   │       ├── question-editor.js      # Form + test-case table + verify flow
│   │       ├── batches.js
│   │       └── performance.js
│   └── assets/
│
├── docs/
│   ├── SPECIFICATION.md                # this file
│   └── SCOPE.md
│
├── scripts/
│   ├── init_db.py                      # Create tables + seed default instructor account
│   └── setup_runner_user.sh            # Create unprivileged coderunner OS user + workdir perms
│
├── .gitignore
└── README.md
```

## 11. Assumptions

- Single institute, single subject — no multi-tenant separation.
- Instructor accounts are seeded manually via `init_db.py`; no admin panel to create instructors.
- SQLite is sufficient for MVP scale (dozens to low hundreds of students, few concurrent submissions).
- Backend and code runner live on the same Ubuntu host. If load grows, the runner moves to its own service; the API contract in §6.3 does not change.
- Notes are private to the student in this phase.
- Frontend uses vanilla JS multi-page navigation — no client-side router, no build step. CodeMirror is the only external JS dependency.
- The frontend and backend run on separate origins in dev (e.g. `localhost:8080` and `localhost:8000`); FastAPI has CORS enabled for the frontend origin.
- The `GET /me/tasks` response uses a `type` discriminator so future task types (video, worksheet, etc.) can be added without changing the endpoint contract or the Tasks page structure.
