import os
import re
import threading
import uuid
from typing import get_args
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..config import settings
from ..database import get_db
from ..services import file_store, worksheet_sync
from .worksheet_content import view_url

router = APIRouter(tags=["worksheets"])

FILE_KINDS = ("topic", "questions", "answers")  # needed before an uploaded worksheet can be verified
ALL_KINDS = get_args(schemas.WorksheetFileKind)


def _sanitize_filename(name: str) -> str:
    name = os.path.basename(name or "file")
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name[-150:] or "file"


def _remove_uploaded(db: Session, f: models.WorksheetFile):
    # synced files live in the shared repo mirror (other pages use them too), so only uploads are deleted
    if f.rel_path is None:
        file_store.delete(db, f.stored_path)


def _worksheet_list_item(db: Session, w: models.WorksheetTask) -> schemas.WorksheetListItemOut:
    file_count = db.query(models.WorksheetFile).filter(models.WorksheetFile.worksheet_id == w.id).count()
    rows = db.query(models.WorksheetAssignment).filter(models.WorksheetAssignment.worksheet_id == w.id).all()
    return schemas.WorksheetListItemOut(
        id=w.id, title=w.title, subject=w.subject, subject_slug=w.subject_slug,
        file_count=file_count, assignment_count=len(rows), verified_at=w.verified_at,
        files=[schemas.WorksheetFileOut.model_validate(f) for f in w.files],
        assignments=[schemas.WorksheetBatchSheets(batch_id=a.batch_id, kinds=a.kind_list) for a in rows],
    )


def _worksheet_detail(w: models.WorksheetTask) -> schemas.WorksheetDetailOut:
    return schemas.WorksheetDetailOut(
        id=w.id, title=w.title, subject=w.subject, subject_slug=w.subject_slug, description=w.description, verified_at=w.verified_at,
        files=[schemas.WorksheetFileOut.model_validate(f) for f in w.files],
    )


@router.get("/worksheets", response_model=list[schemas.WorksheetListItemOut])
def list_worksheets(
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    worksheets = (
        db.query(models.WorksheetTask)
        .order_by(models.WorksheetTask.position, models.WorksheetTask.created_at.desc())
        .all()
    )
    return [_worksheet_list_item(db, w) for w in worksheets]


# ---- Sync from the worksheet repo ----
# one sync at a time; the status lives in memory (reset when the server restarts)
_sync_lock = threading.Lock()
_sync_status = {"last_synced_at": None, "last_error": None, "added": [], "items": [], "log": []}


def _sync_status_out() -> schemas.WorksheetSyncStatusOut:
    return schemas.WorksheetSyncStatusOut(
        repo_url=settings.worksheet_repo_url,
        running=_sync_lock.locked(),
        last_synced_at=_sync_status["last_synced_at"],
        last_error=_sync_status["last_error"],
        added=_sync_status["added"],
        items=_sync_status["items"],
        log=_sync_status["log"],
    )


@router.get("/worksheets/sync", response_model=schemas.WorksheetSyncStatusOut)
def worksheet_sync_status(_instructor: models.User = Depends(auth.require_instructor)):
    return _sync_status_out()


@router.post("/worksheets/sync", response_model=schemas.WorksheetSyncStatusOut)
def sync_worksheets_from_repo(
    db: Session = Depends(get_db),
    instructor: models.User = Depends(auth.require_instructor),
):
    """Pulls the worksheet repo's docs/ folder: new items appear in Library → Worksheets, changed
    pages are updated in place, batch assignments are kept."""
    if not _sync_lock.acquire(blocking=False):
        return _sync_status_out()  # another instructor's sync is already running
    log = []
    try:
        result = worksheet_sync.run_sync(db, instructor_id=instructor.id, log=log.append)
        _sync_status.update(last_synced_at=datetime.now(timezone.utc), last_error=None,
                            added=result["added"], items=result["items"], log=log)
    except Exception as err:  # network / repo problems are shown on the page instead of a 500
        db.rollback()
        _sync_status.update(last_error=f"Could not sync from the worksheet repo: {err}", log=log)
    finally:
        _sync_lock.release()
    return _sync_status_out()


@router.post("/worksheets", response_model=schemas.WorksheetDetailOut)
def create_worksheet(
    payload: schemas.CreateWorksheetRequest,
    db: Session = Depends(get_db),
    instructor: models.User = Depends(auth.require_instructor),
):
    w = models.WorksheetTask(title=payload.title, description=payload.description, created_by=instructor.id)
    db.add(w)
    db.commit()
    db.refresh(w)
    return _worksheet_detail(w)


@router.get("/worksheets/{worksheet_id}", response_model=schemas.WorksheetDetailOut)
def get_worksheet(
    worksheet_id: int,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    w = db.get(models.WorksheetTask, worksheet_id)
    if not w:
        raise HTTPException(status_code=404, detail="Worksheet not found")
    return _worksheet_detail(w)


@router.put("/worksheets/{worksheet_id}", response_model=schemas.WorksheetDetailOut)
def update_worksheet(
    worksheet_id: int,
    payload: schemas.UpdateWorksheetRequest,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    w = db.get(models.WorksheetTask, worksheet_id)
    if not w:
        raise HTTPException(status_code=404, detail="Worksheet not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(w, field, value)
    w.verified_at = None
    db.commit()
    db.refresh(w)
    return _worksheet_detail(w)


@router.delete("/worksheets/{worksheet_id}")
def delete_worksheet(
    worksheet_id: int,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    w = db.get(models.WorksheetTask, worksheet_id)
    if not w:
        raise HTTPException(status_code=404, detail="Worksheet not found")
    for f in w.files:
        _remove_uploaded(db, f)
    # rows that point at the worksheet go first (Postgres enforces the foreign keys)
    db.query(models.WorksheetAssignment).filter(models.WorksheetAssignment.worksheet_id == worksheet_id).delete()
    db.query(models.WorksheetProgress).filter(models.WorksheetProgress.worksheet_id == worksheet_id).delete()
    db.query(models.WorksheetSheetView).filter(models.WorksheetSheetView.worksheet_id == worksheet_id).delete()
    db.delete(w)
    db.commit()
    return {"ok": True}


@router.post("/worksheets/{worksheet_id}/files", response_model=schemas.WorksheetFileOut)
async def upload_worksheet_file(
    worksheet_id: int,
    kind: schemas.WorksheetFileKind = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    w = db.get(models.WorksheetTask, worksheet_id)
    if not w:
        raise HTTPException(status_code=404, detail="Worksheet not found")

    max_bytes = settings.worksheet_max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status_code=400, detail=f"File exceeds {settings.worksheet_max_upload_mb} MB limit")

    safe_name = _sanitize_filename(file.filename)
    stored_path = f"uploads/{worksheet_id}/{kind}__{uuid.uuid4().hex}__{safe_name}"
    file_store.put(db, stored_path, data, file.content_type)

    existing = (
        db.query(models.WorksheetFile)
        .filter(models.WorksheetFile.worksheet_id == worksheet_id, models.WorksheetFile.kind == kind)
        .first()
    )
    if existing:
        _remove_uploaded(db, existing)
        existing.original_filename = safe_name
        existing.stored_path = stored_path
        existing.content_type = file.content_type
        existing.rel_path = None
        existing.uploaded_at = datetime.now(timezone.utc)
        record = existing
    else:
        record = models.WorksheetFile(
            worksheet_id=worksheet_id, kind=kind, original_filename=safe_name,
            stored_path=stored_path, content_type=file.content_type,
        )
        db.add(record)

    w.verified_at = None
    db.commit()
    db.refresh(record)
    return record


@router.delete("/worksheets/{worksheet_id}/files/{kind}")
def delete_worksheet_file(
    worksheet_id: int,
    kind: schemas.WorksheetFileKind,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    record = (
        db.query(models.WorksheetFile)
        .filter(models.WorksheetFile.worksheet_id == worksheet_id, models.WorksheetFile.kind == kind)
        .first()
    )
    if record:
        _remove_uploaded(db, record)
        db.delete(record)
        w = db.get(models.WorksheetTask, worksheet_id)
        if w:
            w.verified_at = None
        db.commit()
    return {"ok": True}


@router.get("/worksheets/{worksheet_id}/files/{kind}/download")
def download_worksheet_file(
    worksheet_id: int,
    kind: schemas.WorksheetFileKind,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    record = (
        db.query(models.WorksheetFile)
        .filter(models.WorksheetFile.worksheet_id == worksheet_id, models.WorksheetFile.kind == kind)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    return file_store.download_response(db, record)


@router.post("/worksheets/{worksheet_id}/files/{kind}/view-link", response_model=schemas.WorksheetViewLinkOut)
def worksheet_file_view_link(
    worksheet_id: int,
    kind: schemas.WorksheetFileKind,
    db: Session = Depends(get_db),
    instructor: models.User = Depends(auth.require_instructor),
):
    w = db.get(models.WorksheetTask, worksheet_id)
    if not w:
        raise HTTPException(status_code=404, detail="Worksheet not found")
    return schemas.WorksheetViewLinkOut(url=view_url(w, kind, instructor))


@router.post("/worksheets/{worksheet_id}/verify", response_model=schemas.WorksheetDetailOut)
def verify_worksheet(
    worksheet_id: int,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    w = db.get(models.WorksheetTask, worksheet_id)
    if not w:
        raise HTTPException(status_code=404, detail="Worksheet not found")

    present_kinds = {f.kind for f in w.files}
    missing = [k for k in FILE_KINDS if k not in present_kinds]
    if missing:
        raise HTTPException(status_code=400, detail=f"Upload the {', '.join(missing)} file(s) before verifying")

    w.verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(w)
    return _worksheet_detail(w)


# ---- Assignments ----
@router.get("/worksheets/{worksheet_id}/assignments", response_model=schemas.WorksheetAssignmentsOut)
def worksheet_assignments(
    worksheet_id: int,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    rows = db.query(models.WorksheetAssignment).filter(models.WorksheetAssignment.worksheet_id == worksheet_id).all()
    return schemas.WorksheetAssignmentsOut(
        batch_ids=[a.batch_id for a in rows],
        assignments=[schemas.WorksheetBatchSheets(batch_id=a.batch_id, kinds=a.kind_list) for a in rows],
    )


@router.put("/worksheets/{worksheet_id}/assignments", response_model=schemas.WorksheetAssignmentsOut)
def set_worksheet_assignments(
    worksheet_id: int,
    payload: schemas.SetWorksheetAssignmentsRequest,
    db: Session = Depends(get_db),
    instructor: models.User = Depends(auth.require_instructor),
):
    w = db.get(models.WorksheetTask, worksheet_id)
    if not w:
        raise HTTPException(status_code=404, detail="Worksheet not found")
    if payload.assignments and not w.verified_at:
        raise HTTPException(status_code=400, detail="Worksheet must be verified before assigning")
    present = {f.kind for f in w.files}

    wanted = {}
    for entry in payload.assignments:
        kinds = [k for k in ALL_KINDS if k in entry.kinds]
        missing = [k for k in kinds if k not in present]
        if missing:
            raise HTTPException(status_code=400, detail=f"This worksheet has no {', '.join(missing)} sheet to assign")
        if kinds:
            wanted[entry.batch_id] = ",".join(kinds)

    existing = {
        a.batch_id: a for a in
        db.query(models.WorksheetAssignment).filter(models.WorksheetAssignment.worksheet_id == worksheet_id).all()
    }
    for batch_id, a in existing.items():
        if batch_id not in wanted:
            db.delete(a)
    for batch_id, kinds in wanted.items():
        if batch_id in existing:
            existing[batch_id].kinds = kinds
        else:
            db.add(models.WorksheetAssignment(worksheet_id=worksheet_id, batch_id=batch_id, kinds=kinds))
    db.commit()
    return worksheet_assignments(worksheet_id, db, instructor)


@router.get("/batches/{batch_id}/worksheets", response_model=list[schemas.BatchWorksheetOut])
def batch_worksheets(
    batch_id: int,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    rows = (
        db.query(models.WorksheetAssignment, models.WorksheetTask)
        .join(models.WorksheetTask, models.WorksheetTask.id == models.WorksheetAssignment.worksheet_id)
        .filter(models.WorksheetAssignment.batch_id == batch_id)
        .order_by(models.WorksheetAssignment.assigned_at.desc())
        .all()
    )
    return [
        schemas.BatchWorksheetOut(
            id=w.id, title=w.title, subject=w.subject, assigned_at=a.assigned_at, kinds=a.kind_list,
            files=[schemas.WorksheetFileOut.model_validate(f) for f in w.files],
        )
        for a, w in rows
    ]


@router.delete("/batches/{batch_id}/worksheets/{worksheet_id}")
def unassign_batch_worksheet(
    batch_id: int,
    worksheet_id: int,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    db.query(models.WorksheetAssignment).filter(
        models.WorksheetAssignment.batch_id == batch_id,
        models.WorksheetAssignment.worksheet_id == worksheet_id,
    ).delete()
    db.commit()
    return {"ok": True}


@router.post("/worksheet-assignments")
def assign_worksheet(
    payload: schemas.WorksheetAssignRequest,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    w = db.get(models.WorksheetTask, payload.worksheet_id)
    if not w:
        raise HTTPException(status_code=404, detail="Worksheet not found")
    if not w.verified_at:
        raise HTTPException(status_code=400, detail="Worksheet must be verified before assigning")

    existing_batch_ids = {
        a.batch_id for a in
        db.query(models.WorksheetAssignment).filter(models.WorksheetAssignment.worksheet_id == payload.worksheet_id).all()
    }

    for batch_id in payload.batch_ids:
        if batch_id not in existing_batch_ids:
            db.add(models.WorksheetAssignment(worksheet_id=payload.worksheet_id, batch_id=batch_id))

    to_remove = existing_batch_ids - set(payload.batch_ids)
    if to_remove:
        db.query(models.WorksheetAssignment).filter(
            models.WorksheetAssignment.worksheet_id == payload.worksheet_id,
            models.WorksheetAssignment.batch_id.in_(to_remove),
        ).delete(synchronize_session=False)

    db.commit()
    return {"ok": True}
