from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from ..ratelimit import login_limiter, signup_limiter, signup_total_limiter

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    # keyed by account, not IP: behind Render's proxy the client IP comes from a header anyone can set
    login_limiter.hit(auth.normalize_email(payload.email))
    user = auth.find_user_by_email(db, payload.email)
    if user is None or not auth.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = auth.create_access_token(user.id, user.role)
    return {"token": token, "user": user}


@router.post("/auth/signup", response_model=schemas.UserOut, status_code=201)
def signup(payload: schemas.SignupRequest, db: Session = Depends(get_db)):
    """Self-registration: always a student, in no batch until an instructor adds them to one.
    Doesn't log them in — the sign-up page sends them to the login form."""
    email = auth.normalize_email(payload.email)
    signup_limiter.hit(email)
    signup_total_limiter.hit("all")
    if auth.find_user_by_email(db, email):
        raise HTTPException(status_code=400, detail="An account with this email already exists — log in instead")
    user = models.User(
        name=payload.name.strip(), email=email, password_hash=auth.hash_password(payload.password), role="student",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
