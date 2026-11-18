"""POST /api/auth/login and GET /api/auth/me."""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.auth import create_access_token, current_user, user_json
from app.config import settings
from app.db.deps import get_db
from app.db.models import User
from app.ratelimit import limiter
from app.security import hash_password, verify_password

router = APIRouter(tags=["auth"])

# Checked when the email is unknown, so a wrong email takes as long as a wrong password
# (the response time must not reveal which emails exist).
_DUMMY_HASH = hash_password("not-a-real-password")


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


@router.post("/auth/login")
@limiter.limit(settings.rate_limit_login)
def login(request: Request, body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.strip().lower()))
    password_ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_ok or not user.is_active:
        # Same answer for unknown email, wrong password and inactive account.
        raise ApiError(401, "UNAUTHORIZED", "Invalid email or password.")
    token, expires_in = create_access_token(user)
    return {"access_token": token, "token_type": "bearer", "expires_in": expires_in, "user": user_json(user)}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return user_json(user)
