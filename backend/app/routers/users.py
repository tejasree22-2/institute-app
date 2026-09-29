from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(tags=["users"])


@router.post("/users", response_model=schemas.UserOut)
def create_student(
    payload: schemas.CreateStudentRequest,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    existing = auth.find_user_by_email(db, payload.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already in use")
    student = models.User(
        name=payload.name,
        email=auth.normalize_email(payload.email),
        password_hash=auth.hash_password(payload.password),
        role="student",
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student
