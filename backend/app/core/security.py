from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

# ---------------------------------------------------------------------- #
# Password hashing (bcrypt)
# ---------------------------------------------------------------------- #


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify plain password against bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8")[:72],
            password_hash.encode("utf-8"),
        )
    except Exception:
        return False


# ---------------------------------------------------------------------- #
# JWT Management
# ---------------------------------------------------------------------- #

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login",
    auto_error=False,
)


def create_access_token(user: User, extra_claims: Optional[dict[str, Any]] = None) -> str:
    """Create a signed JWT for the given user."""
    expire = timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "cpse_id": user.cpse_id,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + expire).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises HTTPException(401) on failure."""
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("type") != "access":
            raise credentials_error
        if "sub" not in payload:
            raise credentials_error
        return payload
    except JWTError:
        raise credentials_error


# ---------------------------------------------------------------------- #
# FastAPI Authentication Dependencies
# ---------------------------------------------------------------------- #


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the Bearer token to an active or inactive User row."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        uid = int(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == uid).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_active_user(user: User = Depends(get_current_user)) -> User:
    """Require the user to be active."""
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )
    return user
