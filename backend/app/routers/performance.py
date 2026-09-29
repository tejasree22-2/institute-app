from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from .student import _status_for, _latest_submission

router = APIRouter(tags=["performance"])


@router.get("/batches/{batch_id}/questions/{question_id}/performance", response_model=list[schemas.PerformanceRowOut])
def batch_question_performance(
    batch_id: int,
    question_id: int,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    members = (
        db.query(models.User)
        .join(models.BatchStudent, models.BatchStudent.student_id == models.User.id)
        .filter(models.BatchStudent.batch_id == batch_id)
        .all()
    )
    rows = []
    for m in members:
        attempt_count = (
            db.query(models.Submission)
            .filter(models.Submission.student_id == m.id, models.Submission.question_id == question_id)
            .count()
        )
        sub = _latest_submission(db, m.id, question_id)
        status, detail = _status_for(sub.passed_count if sub else None, sub.total_count if sub else None)
        rows.append(schemas.PerformanceRowOut(
            student_id=m.id, name=m.name, email=m.email,
            status=status, status_detail=detail,
            attempt_count=attempt_count,
            last_try_at=sub.submitted_at if sub else None,
        ))
    return rows


@router.get("/batches/{batch_id}/worksheets/{worksheet_id}/performance", response_model=schemas.WorksheetPerformanceOut)
def batch_worksheet_performance(
    batch_id: int,
    worksheet_id: int,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    assignment = (
        db.query(models.WorksheetAssignment)
        .filter_by(batch_id=batch_id, worksheet_id=worksheet_id)
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="This worksheet isn't assigned to the batch")
    kinds = assignment.kind_list

    members = (
        db.query(models.User)
        .join(models.BatchStudent, models.BatchStudent.student_id == models.User.id)
        .filter(models.BatchStudent.batch_id == batch_id)
        .order_by(models.User.name)
        .all()
    )
    views = (
        db.query(models.WorksheetSheetView)
        .filter(
            models.WorksheetSheetView.worksheet_id == worksheet_id,
            models.WorksheetSheetView.student_id.in_([m.id for m in members] or [0]),
        )
        .all()
    )
    by_student = {}
    for v in views:
        by_student.setdefault(v.student_id, {})[v.kind] = v

    rows = []
    for m in members:
        seen = by_student.get(m.id, {})
        sheets = {}
        for k in kinds:
            v = seen.get(k)
            sheets[k] = schemas.SheetViewOut(
                view_count=v.view_count, first_viewed_at=v.first_viewed_at, last_viewed_at=v.last_viewed_at,
            ) if v else schemas.SheetViewOut()
        rows.append(schemas.WorksheetPerformanceRowOut(student_id=m.id, name=m.name, email=m.email, sheets=sheets))
    return schemas.WorksheetPerformanceOut(kinds=kinds, rows=rows)


@router.get("/students/{student_id}/questions/{question_id}/submissions", response_model=schemas.StudentSubmissionsOut)
def student_submissions(
    student_id: int,
    question_id: int,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    student = db.get(models.User, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    subs = (
        db.query(models.Submission)
        .filter(models.Submission.student_id == student_id, models.Submission.question_id == question_id)
        .order_by(models.Submission.submitted_at.desc())
        .all()
    )
    latest_code = subs[0].code if subs else None

    return schemas.StudentSubmissionsOut(
        student=student,
        question_id=question_id,
        submissions=[
            schemas.SubmissionHistoryItemOut(
                id=s.id, status=s.status, passed_count=s.passed_count,
                total_count=s.total_count, submitted_at=s.submitted_at,
            ) for s in subs
        ],
        latest_code=latest_code,
    )
