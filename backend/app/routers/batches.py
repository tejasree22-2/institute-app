from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(tags=["batches"])


@router.get("/batches", response_model=list[schemas.BatchOut])
def list_batches(
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    batches = db.query(models.Batch).order_by(models.Batch.created_at.desc()).all()
    out = []
    for b in batches:
        count = db.query(models.BatchStudent).filter(models.BatchStudent.batch_id == b.id).count()
        out.append(schemas.BatchOut(id=b.id, name=b.name, member_count=count, created_at=b.created_at))
    return out


@router.post("/batches", response_model=schemas.BatchOut)
def create_batch(
    payload: schemas.CreateBatchRequest,
    db: Session = Depends(get_db),
    instructor: models.User = Depends(auth.require_instructor),
):
    batch = models.Batch(name=payload.name, created_by=instructor.id)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return schemas.BatchOut(id=batch.id, name=batch.name, member_count=0, created_at=batch.created_at)


@router.get("/batches/{batch_id}", response_model=schemas.BatchDetailOut)
def get_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    batch = db.get(models.Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    members = (
        db.query(models.User)
        .join(models.BatchStudent, models.BatchStudent.student_id == models.User.id)
        .filter(models.BatchStudent.batch_id == batch_id)
        .all()
    )
    return schemas.BatchDetailOut(
        id=batch.id,
        name=batch.name,
        created_at=batch.created_at,
        members=[schemas.BatchMemberOut(id=m.id, name=m.name, email=m.email) for m in members],
    )


@router.post("/batches/{batch_id}/students", response_model=schemas.BatchMemberOut)
def add_student(
    batch_id: int,
    payload: schemas.AddStudentRequest,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    batch = db.get(models.Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    if payload.student_id:
        student = db.get(models.User, payload.student_id)
        if not student or student.role != "student":
            raise HTTPException(status_code=404, detail="Student not found")
    else:
        if not payload.email:
            raise HTTPException(status_code=400, detail="Email required")
        student = auth.find_user_by_email(db, payload.email)
        if student and student.role != "student":
            raise HTTPException(status_code=400, detail="That email belongs to an instructor")
        if not student:
            # no account yet: the instructor creates it (a student who signed up needs only the email)
            if not (payload.name and payload.password):
                raise HTTPException(status_code=400, detail="No account with this email yet — enter a name and initial password to create one")
            student = models.User(
                name=payload.name.strip(),
                email=auth.normalize_email(payload.email),
                password_hash=auth.hash_password(payload.password),
                role="student",
            )
            db.add(student)
            db.flush()

    link = (
        db.query(models.BatchStudent)
        .filter(models.BatchStudent.batch_id == batch_id, models.BatchStudent.student_id == student.id)
        .first()
    )
    if not link:
        db.add(models.BatchStudent(batch_id=batch_id, student_id=student.id))
    db.commit()
    return schemas.BatchMemberOut(id=student.id, name=student.name, email=student.email)


@router.delete("/batches/{batch_id}/students/{student_id}")
def remove_student(
    batch_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    link = (
        db.query(models.BatchStudent)
        .filter(models.BatchStudent.batch_id == batch_id, models.BatchStudent.student_id == student_id)
        .first()
    )
    if link:
        db.delete(link)
        db.commit()
    return {"ok": True}


@router.get("/students/unassigned", response_model=list[schemas.BatchMemberOut])
def unassigned_students(
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    """Students in no batch — mostly people who signed up themselves and are waiting to be added."""
    in_a_batch = db.query(models.BatchStudent.student_id)
    students = (
        db.query(models.User)
        .filter(models.User.role == "student", models.User.id.notin_(in_a_batch))
        .order_by(models.User.created_at.desc())
        .all()
    )
    return [schemas.BatchMemberOut(id=s.id, name=s.name, email=s.email) for s in students]
