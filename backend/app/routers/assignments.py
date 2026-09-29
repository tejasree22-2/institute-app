from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(tags=["assignments"])


@router.get("/batches/{batch_id}/assignments", response_model=list[schemas.QuestionListItemOut])
def batch_assignments(
    batch_id: int,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    rows = (
        db.query(models.CodingQuestion)
        .join(models.Assignment, models.Assignment.question_id == models.CodingQuestion.id)
        .filter(models.Assignment.batch_id == batch_id)
        .all()
    )
    out = []
    for q in rows:
        tc_count = db.query(models.TestCase).filter(models.TestCase.question_id == q.id).count()
        a_count = db.query(models.Assignment).filter(models.Assignment.question_id == q.id).count()
        out.append(schemas.QuestionListItemOut(
            id=q.id, title=q.title, difficulty=q.difficulty,
            test_case_count=tc_count, assignment_count=a_count, verified_at=q.verified_at,
        ))
    return out


@router.get("/questions/{question_id}/assignments")
def question_assignments(
    question_id: int,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    rows = db.query(models.Assignment).filter(models.Assignment.question_id == question_id).all()
    return {"batch_ids": [a.batch_id for a in rows]}


@router.post("/assignments")
def assign(
    payload: schemas.AssignRequest,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    q = db.get(models.CodingQuestion, payload.question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    if not q.verified_at:
        raise HTTPException(status_code=400, detail="Question must be verified before assigning")

    existing_batch_ids = {
        a.batch_id for a in
        db.query(models.Assignment).filter(models.Assignment.question_id == payload.question_id).all()
    }

    for batch_id in payload.batch_ids:
        if batch_id not in existing_batch_ids:
            db.add(models.Assignment(question_id=payload.question_id, batch_id=batch_id))

    # unassign batches that were previously checked but are no longer in the list
    to_remove = existing_batch_ids - set(payload.batch_ids)
    if to_remove:
        db.query(models.Assignment).filter(
            models.Assignment.question_id == payload.question_id,
            models.Assignment.batch_id.in_(to_remove),
        ).delete(synchronize_session=False)

    db.commit()
    return {"ok": True}


@router.delete("/assignments/{assignment_id}")
def unassign(
    assignment_id: int,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    a = db.get(models.Assignment, assignment_id)
    if a:
        db.delete(a)
        db.commit()
    return {"ok": True}
