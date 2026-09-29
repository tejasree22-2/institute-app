import os
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings

IS_SQLITE = settings.database_url.startswith("sqlite")

if IS_SQLITE:
    os.makedirs(settings.data_dir, exist_ok=True)
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
else:
    # Postgres (Supabase). Small pool: the free tier caps connections. pre_ping/recycle replace
    # connections the pooler dropped; prepare_threshold=None keeps it working through Supabase's
    # transaction pooler (port 6543) too, which can't hold prepared statements.
    engine = create_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"prepare_threshold": None},
    )

    @event.listens_for(engine, "connect")
    def _utc(dbapi_conn, _record):
        # the DateTime columns store naive UTC, as they did in SQLite
        with dbapi_conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'UTC'")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# create_all() never alters existing tables, so columns added after a DB was created are patched in here
_ADDED_COLUMNS = {
    "worksheet_tasks": {
        "subject": "VARCHAR",
        "subject_slug": "VARCHAR",
        "source_key": "VARCHAR",
        "position": "INTEGER NOT NULL DEFAULT 0",
    },
    "worksheet_assignments": {
        "kinds": "VARCHAR NOT NULL DEFAULT 'topic,questions,answers'",
    },
    "worksheet_files": {
        "rel_path": "VARCHAR",
        "label": "VARCHAR",
    },
}


def ensure_columns():
    with engine.begin() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        for table, columns in _ADDED_COLUMNS.items():
            if table not in tables:
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        if not IS_SQLITE:
            # Supabase also exposes the public schema through its REST API; with row level security on
            # and no policies, that API sees nothing. The app connects as the tables' owner, which
            # bypasses RLS, so this changes nothing for it.
            for table in Base.metadata.tables:
                conn.exec_driver_sql(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
