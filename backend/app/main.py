import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import Base, SessionLocal, engine, ensure_columns
from . import models  # noqa: F401  (ensures models are registered before create_all)
from .config import settings
from .services import code_runner, file_store, sandbox
from .routers import auth, users, batches, questions, assignments, student, performance, worksheets, worksheet_content

Base.metadata.create_all(bind=engine)
ensure_columns()
with SessionLocal() as _db:
    file_store.import_legacy_files(_db)

# student code runs as the same OS user as the API: keep our /proc/<pid>/environ (JWT_SECRET) unreadable,
# then check the sandbox that keeps it away from the DB and files
sandbox.protect_current_process()
code_runner.check_sandbox()

# the interactive docs list every endpoint, so they're only exposed outside production
docs_kwargs = {"docs_url": None, "redoc_url": None, "openapi_url": None} if settings.is_production else {}
app = FastAPI(title="Institute App API", **docs_kwargs)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,  # auth is a Bearer header, not cookies
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(batches.router)
app.include_router(questions.router)
app.include_router(assignments.router)
app.include_router(student.router)
app.include_router(performance.router)
app.include_router(worksheets.router)
app.include_router(worksheet_content.router)


@app.get("/health")
def health():
    return {"status": "ok", "code_sandbox": code_runner.sandbox_status}


# serves the frontend too when it sits next to the backend (a local checkout); mounted last so API routes win
if os.path.isdir(settings.frontend_dir):
    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
