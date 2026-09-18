from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    decode_token,
    get_current_active_user,
    get_current_user,
    verify_password,
)
from app.models.user import User
from app.schemas.user import RefreshRequest, TokenResponse, UserLogin, UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    """Authenticate with email and password, issuing a stateless JWT access token."""
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

    token = create_access_token(user)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserResponse.from_orm_object(user),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange an existing valid JWT for a freshly issued token."""
    token_data = decode_token(payload.access_token)
    user_id = token_data.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists or is deactivated",
        )

    token = create_access_token(user)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserResponse.from_orm_object(user),
    )


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(user: User = Depends(get_current_active_user)):
    """Retrieve profile and permissions for the currently authenticated user."""
    return UserResponse.from_orm_object(user)


@router.post("/logout")
def logout(user: User = Depends(get_current_user)):
    """Stateless logout confirmation."""
    return {"message": "Logged out successfully", "user_id": user.id}
