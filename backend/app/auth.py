"""Login tokens (JWT) and the two roles.

- viewer:   can read everything and export
- reviewer: can also add companies, start/cancel/retry runs and correct answers

Flow: POST /api/auth/login checks the password and returns a signed token. The browser
(Streamlit) sends it back on every request as "Authorization: Bearer <token>".
The token is signed with JWT_SECRET (HS256), so it cannot be changed without the secret,
and it expires after jwt_expires_minutes.

The user's role and "active" flag are read from the DATABASE on every request (not only
from the token), so deactivating a user or changing a role takes effect immediately.
"""
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.config import settings
from app.db.deps import get_db
from app.db.enums import Role
from app.db.models import User

ALGORITHM = "HS256"
bearer = HTTPBearer(auto_error=False)  # we raise our own 401 in our error shape


def create_access_token(user: User) -> tuple[str, int]:
    """(token, seconds until it expires)."""
    expires_in = settings.jwt_expires_minutes * 60
    now = datetime.now(UTC)
    claims = {"sub": str(user.id), "role": user.role, "iat": now, "exp": now + timedelta(seconds=expires_in)}
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM), expires_in


def _unauthorized(message: str) -> ApiError:
    return ApiError(401, "UNAUTHORIZED", message)


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    """FastAPI dependency: the logged-in user, or 401."""
    if credentials is None:
        raise _unauthorized("Please log in.")
    try:
        claims = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[ALGORITHM],
                            options={"require": ["exp", "sub"]})
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("Your session expired, please log in again.") from exc
    except jwt.InvalidTokenError as exc:  # bad signature, garbage, missing claims
        raise _unauthorized("Invalid login token, please log in again.") from exc

    user = db.get(User, int(claims["sub"])) if str(claims["sub"]).isdigit() else None
    if user is None or not user.is_active:
        raise _unauthorized("This account no longer has access.")
    return user


def require_reviewer(user: User = Depends(current_user)) -> User:
    """FastAPI dependency for every endpoint that CHANGES something."""
    if user.role != Role.REVIEWER:
        raise ApiError(403, "FORBIDDEN", "Reviewer role required.")
    return user


def user_json(user: User) -> dict:
    return {"id": user.id, "email": user.email, "role": user.role}
