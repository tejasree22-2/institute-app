"""Serves worksheet pages mirrored from the worksheet repo by services/worksheet_sync.py (stored in
the database, see services/file_store.py).

The pages are plain HTML that pull in relative files (../assets/viewer.js, <name>.md), so they are
opened in a browser tab rather than downloaded. A tab can't send the Bearer header, so the caller
first asks for a short-lived link (see view_url) whose token sits in the URL *path*: relative
requests made by the page then carry the same token automatically.
"""
import mimetypes
import os
import posixpath
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..database import get_db
from ..services import file_store

router = APIRouter(tags=["worksheet-content"])

TOKEN_TYPE = "worksheet_view"

mimetypes.add_type("text/markdown", ".md")

# the repo pages link back to the repo's own index pages, which don't exist inside the app
HIDE_INDEX_LINKS = b'<style>a[href$="index.html"]{display:none !important}</style>'
# shown inside the app's viewer (?embed=1): trim the page's own outer spacing so the sheet gets the room
EMBED_STYLE = (
    b"<style>main{padding:14px 10px 40px !important}"
    b".sheet{max-width:980px !important;padding:clamp(18px,3vw,36px) !important}</style>"
)


def view_url(w: models.WorksheetTask, kind: str, user: models.User) -> str:
    record = next((f for f in w.files if f.kind == kind), None)
    if not record or not record.rel_path:
        raise HTTPException(status_code=404, detail="This file can't be opened as a page")
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.worksheet_view_link_minutes)
    payload = {"typ": TOKEN_TYPE, "sub": str(user.id), "ws": w.id, "kind": kind, "exp": expire}
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return f"/content/{token}/{record.rel_path}"


def _markdown_twin(rel_path: str) -> str:
    return os.path.splitext(rel_path)[0] + ".md"


@router.get("/content/{token}/{rel_path:path}")
def serve_content(token: str, rel_path: str, embed: bool = False, db: Session = Depends(get_db)):
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="This link has expired — reopen it from the app")
    if claims.get("typ") != TOKEN_TYPE:
        raise HTTPException(status_code=401, detail="Invalid link")

    w = db.get(models.WorksheetTask, claims["ws"])
    if not w or not w.subject_slug:
        raise HTTPException(status_code=404, detail="Worksheet not found")

    rel_path = posixpath.normpath(rel_path)
    if rel_path.startswith(("..", "/", ".")):
        raise HTTPException(status_code=404, detail="File not found")

    # the link only reaches files of its own subject (shared assets, the page's markdown, images)
    if not rel_path.startswith(w.subject_slug + "/"):
        raise HTTPException(status_code=403, detail="Not allowed")

    # answer pages stay locked unless this link was issued for exactly those answers
    own_answers = set()
    if claims["kind"] in schemas.ANSWER_KINDS:
        record = next((f for f in w.files if f.kind == claims["kind"]), None)
        if record and record.rel_path:
            own_answers = {record.rel_path, _markdown_twin(record.rel_path)}
    answer_rows = (
        db.query(models.WorksheetFile.rel_path)
        .filter(models.WorksheetFile.kind.in_(schemas.ANSWER_KINDS), models.WorksheetFile.rel_path.isnot(None))
        .all()
    )
    protected = {p for (r,) in answer_rows for p in (r, _markdown_twin(r))}
    if rel_path in protected and rel_path not in own_answers:
        raise HTTPException(status_code=403, detail="Answers are locked")

    stored = file_store.get(db, file_store.content_key(rel_path))
    if stored is None:
        raise HTTPException(status_code=404, detail="File not found")

    headers = {"Cache-Control": "private, no-store"}
    media_type = mimetypes.guess_type(rel_path)[0] or "application/octet-stream"
    if media_type == "text/html":
        style = HIDE_INDEX_LINKS + (EMBED_STYLE if embed else b"")
        html = stored.data.replace(b"</head>", style + b"</head>", 1)
        return Response(html, media_type="text/html; charset=utf-8", headers=headers)
    if media_type.startswith("text/"):
        media_type += "; charset=utf-8"
    return Response(stored.data, media_type=media_type, headers=headers)
