"""Import worksheets from the worksheet repo (github.com/aikaryashala/first-steps, folder docs/).

The app does this with the "Sync from GitHub" button in Library → Worksheets; this script is for
doing it from the command line, e.g. from a local clone. See
backend/app/services/worksheet_sync.py for how the repo's index pages are read.

Run from the institute-app/ directory:
    python3 scripts/sync_worksheets.py                          # from the GitHub repo (main branch)
    python3 scripts/sync_worksheets.py --repo ../first-steps    # from a local clone (git pull first)
    python3 scripts/sync_worksheets.py --url https://aikaryashala.com/first-steps/  # from the published site
    python3 scripts/sync_worksheets.py --subject ganitham       # only one subject
"""
import argparse
import os
import sys

BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, BACKEND_DIR)

from app.config import settings  # noqa: E402
from app.database import Base, engine, SessionLocal, ensure_columns  # noqa: E402
from app.services.worksheet_sync import RepoSource, SyncError, UrlSource, run_sync  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--repo", help="local clone of the worksheet repo (or its docs/ folder)")
    src.add_argument("--url", default=settings.worksheet_repo_url, help=f"site to read from (default {settings.worksheet_repo_url})")
    parser.add_argument("--subject", action="append", help="subject folder to sync, e.g. ganitham (repeatable; default all)")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    ensure_columns()
    db = SessionLocal()
    try:
        source = RepoSource(args.repo) if args.repo else UrlSource(args.url)
        result = run_sync(db, source, args.subject)
        print(f"New worksheets: {len(result['added'])}")
    except SyncError as err:
        sys.exit(str(err))
    finally:
        db.close()


if __name__ == "__main__":
    main()
