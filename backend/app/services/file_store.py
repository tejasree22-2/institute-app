"""File bytes stored in the `stored_files` table instead of on disk.

Keys: "uploads/<worksheet id>/<name>" for instructor uploads, "content/<subject slug>/<path>" for the
worksheet repo mirror written by services/worksheet_sync.py. Callers commit.
"""
import mimetypes
import os
import urllib.parse

from fastapi import HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import models
from ..config import settings

CONTENT_PREFIX = "content/"


def content_key(rel_path: str) -> str:
    return CONTENT_PREFIX + rel_path


def put(db: Session, key: str, data: bytes, content_type: str | None = None):
    row = db.get(models.StoredFile, key)
    if row is None:
        db.add(models.StoredFile(key=key, data=data, content_type=content_type))
    else:
        row.data, row.content_type = data, content_type


def get(db: Session, key: str) -> models.StoredFile | None:
    return db.get(models.StoredFile, key)


def delete(db: Session, key: str):
    db.query(models.StoredFile).filter(models.StoredFile.key == key).delete()


def _under(prefix: str):
    return models.StoredFile.key.startswith(prefix, autoescape=True)


def load_prefix(db: Session, prefix: str) -> dict[str, tuple[bytes, str | None]]:
    """{path relative to prefix: (bytes, etag)} for every file under `prefix`."""
    return {row.key[len(prefix):]: (row.data, row.etag)
            for row in db.query(models.StoredFile).filter(_under(prefix)).yield_per(50)}


def write_dir(files: dict[str, tuple[bytes, str | None]], dest: str):
    for rel, (data, _etag) in files.items():
        out = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(data)


def sync_prefix(db: Session, prefix: str, src: str, old: dict[str, tuple[bytes, str | None]],
                etags: dict[str, str]) -> tuple[set[str], dict[str, int]]:
    """Make the files under `prefix` match folder `src`, touching only what changed: new files are
    inserted, changed ones updated, files no longer in `src` deleted, unchanged rows left alone.
    `old` is load_prefix() of the same prefix; `etags` the source's ETags by relative path.
    Returns (relative paths now stored, counts)."""
    counts = {"new": 0, "updated": 0, "unchanged": 0, "removed": 0}
    stored = set()
    for dirpath, _dirs, filenames in os.walk(src):
        for name in filenames:
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, src).replace(os.sep, "/")
            stored.add(rel)
            with open(path, "rb") as f:
                data = f.read()
            previous = old.get(rel)
            etag = etags.get(rel) or (previous[1] if previous else None)
            if previous is None:
                db.add(models.StoredFile(key=prefix + rel, data=data, etag=etag, content_type=mimetypes.guess_type(name)[0]))
                counts["new"] += 1
            elif previous[0] != data:
                row = db.get(models.StoredFile, prefix + rel)
                row.data, row.etag = data, etag
                counts["updated"] += 1
            else:
                if etag != previous[1]:
                    db.get(models.StoredFile, prefix + rel).etag = etag
                counts["unchanged"] += 1
    removed = [prefix + rel for rel in old if rel not in stored]
    if removed:
        db.query(models.StoredFile).filter(models.StoredFile.key.in_(removed)).delete(synchronize_session=False)
    counts["removed"] = len(removed)
    return stored, counts


def replace_prefix(db: Session, prefix: str, src: str) -> set[str]:
    """Make the files under `prefix` exactly the contents of folder `src`; returns their relative paths."""
    stored, _counts = sync_prefix(db, prefix, src, load_prefix(db, prefix), {})
    return stored


def download_response(db: Session, record: models.WorksheetFile) -> Response:
    row = get(db, record.stored_path)
    if row is None:
        raise HTTPException(status_code=404, detail="File not found")
    filename = urllib.parse.quote(record.original_filename)
    return Response(
        row.data,
        media_type=record.content_type or row.content_type or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


def import_legacy_files(db: Session):
    """One-off move of files an older version kept on disk (data/worksheet_uploads, data/worksheet_content)
    into the table, for databases created before files moved there. A no-op once done."""
    content_dir = os.path.join(settings.data_dir, "worksheet_content")
    legacy = db.query(models.WorksheetFile).filter(models.WorksheetFile.stored_path.startswith("/")).all()
    if not legacy:
        return
    if os.path.isdir(content_dir) and not db.query(models.StoredFile).filter(_under(CONTENT_PREFIX)).first():
        replace_prefix(db, CONTENT_PREFIX, content_dir)
    for record in legacy:
        if record.rel_path:
            record.stored_path = content_key(record.rel_path)
            continue
        key = f"uploads/{record.worksheet_id}/{os.path.basename(record.stored_path)}"
        if os.path.isfile(record.stored_path):
            with open(record.stored_path, "rb") as f:
                put(db, key, f.read(), record.content_type)
        record.stored_path = key
    db.commit()
