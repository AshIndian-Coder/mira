"""Authentication endpoints: login, token refresh, current user, logout.

    POST /api/v1/auth/login     -> {access_token, token_type, expires_in, user}
    POST /api/v1/auth/refresh   -> new token from a still-valid token
    GET  /api/v1/auth/me        -> current user profile
    POST /api/v1/auth/logout    -> audit-logged client-side logout
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.rbac import require_permission
from app.core.security import (
    create_access_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db.postgres import get_db
from app.models.user import User
from app.schemas.user_schema import (
    RefreshRequest,
    TokenResponse,
    UserLogin,
    UserResponse,
)
from app.services.audit.audit_service import log_action
from app.utils.constants import AUDIT_LOGIN, AUDIT_LOGOUT
from app.utils.helpers import utcnow

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    """Issue a JWT for valid credentials (JWT is stateless)."""
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )
    user.last_login = utcnow()
    token = create_access_token(user)
    log_action(db, user, AUDIT_LOGIN, entity_type="user", entity_id=user.id, commit=True)
    return TokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.from_orm_object(user),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a valid (non-expired) token for a fresh one."""
    token_data = decode_token(payload.access_token)
    user = db.query(User).filter(User.id == int(token_data["sub"])).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists or is deactivated",
        )
    token = create_access_token(user)
    return TokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.from_orm_object(user),
    )


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    """Current user profile (drives role-based UI visibility)."""
    return UserResponse.from_orm_object(user)


@router.post("/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Client-side logout: the JWT is stateless, so we audit + confirm.

    The client discards the token; the token itself stays cryptographically
    valid until expiry (standard stateless-JWT behaviour).
    """
    log_action(db, user, AUDIT_LOGOUT, entity_type="user", entity_id=user.id, commit=True)
    return {"message": "Logged out", "user_id": user.id}

