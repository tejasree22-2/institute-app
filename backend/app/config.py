import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.dirname(BASE_DIR)

# local settings (DATABASE_URL, …) from institute-app/.env; real environment variables win, so on
# Render — where .env doesn't exist, it's gitignored — the service's Environment settings are used
load_dotenv(os.path.join(PROJECT_DIR, ".env"))

# "production" turns on the strict checks below; anything else is a local/demo run
APP_ENV = os.environ.get("APP_ENV", "development")
IS_PRODUCTION = APP_ENV == "production"

# local SQLite file (when DATABASE_URL isn't set); uploads and synced worksheets live in the DB itself
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))

_DEV_JWT_SECRET = "dev-secret-change-me"


def _jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if secret:
        return secret
    if IS_PRODUCTION:
        raise RuntimeError("JWT_SECRET must be set when APP_ENV=production")
    return _DEV_JWT_SECRET


def _cors_origins() -> list[str]:
    default = "" if IS_PRODUCTION else "http://localhost:8080,http://127.0.0.1:8080,http://localhost:8888,http://127.0.0.1:8888"
    origins = []
    for origin in os.environ.get("CORS_ORIGINS", default).split(","):
        origin = origin.strip().rstrip("/")
        if origin:
            # a bare host (as Render hands out) means its https origin
            origins.append(origin if "://" in origin else f"https://{origin}")
    return origins


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        if IS_PRODUCTION:
            # a SQLite file on a free host's disk is wiped on every restart
            raise RuntimeError("DATABASE_URL must be set when APP_ENV=production (the Supabase connection string)")
        return f"sqlite:///{os.path.join(DATA_DIR, 'app.db')}"
    # Supabase hands out postgres:// / postgresql:// URLs; SQLAlchemy needs the driver named
    for scheme in ("postgres://", "postgresql://"):
        if url.startswith(scheme):
            return "postgresql+psycopg://" + url[len(scheme):]
    return url


class Settings:
    is_production: bool = IS_PRODUCTION

    jwt_secret: str = _jwt_secret()
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = int(os.environ.get("JWT_EXPIRE_MINUTES", 60 * 24))

    data_dir: str = DATA_DIR
    database_url: str = _database_url()

    runner_workdir: str = os.environ.get("RUNNER_WORKDIR", os.path.join(BASE_DIR, "runner_workdir"))
    # "required": never run student code outside the sandbox (services/sandbox.py);
    # "best-effort": fall back to plain rlimits when the kernel can't sandbox (fine on a dev laptop)
    sandbox_mode: str = os.environ.get("SANDBOX_MODE", "required" if IS_PRODUCTION else "best-effort")
    exec_timeout_seconds: int = 5
    exec_stdout_cap_bytes: int = 64 * 1024
    exec_memory_limit_mb: int = 128
    exec_max_processes: int = 32
    exec_max_file_bytes: int = 1024 * 1024
    exec_max_code_chars: int = 20_000
    exec_max_concurrent: int = int(os.environ.get("EXEC_MAX_CONCURRENT", 4))

    worksheet_max_upload_mb: int = 20
    # the worksheet repo's docs/ folder, pulled by the "Sync from GitHub" button in Library → Worksheets
    worksheet_repo_url: str = os.environ.get(
        "WORKSHEET_REPO_URL", "https://raw.githubusercontent.com/aikaryashala/first-steps/main/docs/"
    )
    worksheet_view_link_minutes: int = 120

    # origins of the separately hosted frontend, e.g. "https://institute-app-web.onrender.com"
    cors_origins: list[str] = _cors_origins()

    # only used when the frontend is served by the API itself (local convenience); the deployed
    # frontend is a separate static site and isn't part of the backend image
    frontend_dir: str = os.path.join(PROJECT_DIR, "frontend")


settings = Settings()
