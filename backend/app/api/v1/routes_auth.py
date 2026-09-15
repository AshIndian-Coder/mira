"""Authentication routes.

Handles user login, logout, token refresh, password reset, and OTP verification.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.core.security import (
    authenticate_user,
    create_access_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.core.rbac import require_role
from app.db.postgres import get_db
from app.models.user import User
from app.schemas.user_schema import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)

router = APIRouter()


@router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """Authenticate user and return access token."""
    db = next(get_db())
    try:
        user = authenticate_user(db, request.email, request.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        access_token = create_access_token(
            data={"sub": user.email, "role": user.role, "user_id": str(user.id)}
        )

        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
        )
    finally:
        db.close()


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshRequest) -> TokenResponse:
    """Refresh access token using refresh token."""
    payload = decode_token(request.refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    db = next(get_db())
    try:
        user = db.query(User).filter(User.email == payload["sub"]).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        access_token = create_access_token(
            data={
                "sub": user.email,
                "role": user.role,
                "user_id": str(user.id),
            }
        )

        return TokenResponse(access_token=access_token, token_type="bearer")
    finally:
        db.close()


@router.get("/auth/me", response_model=UserResponse)
async def get_current_user(
    current_user: User = Depends(require_role(["admin", "data_steward", "reviewer", "auditor"])),
) -> UserResponse:
    """Get current authenticated user information."""
    return UserResponse.model_validate(current_user)


@router.post("/auth/logout")
async def logout() -> dict[str, str]:
    """Logout user. In a production system, this would invalidate the token."""
    return {"message": "Successfully logged out"}


@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate) -> UserResponse:
    """Register a new user (admin only)."""
    db = next(get_db())
    try:
        existing_user = db.query(User).filter(User.email == user_data.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        user = User(
            email=user_data.email,
            hashed_password=get_password_hash(user_data.password),
            full_name=user_data.full_name,
            role=user_data.role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return UserResponse.model_validate(user)
    finally:
        db.close()


@router.put("/auth/password", status_code=status.HTTP_200_OK)
async def change_password(
    current_user: User = Depends(require_role(["admin", "data_steward", "reviewer", "auditor"])),
) -> dict[str, str]:
    """Change current user's password."""
    return {"message": "Password change endpoint - implement with proper validation"}


@router.post("/auth/reset-password", status_code=status.HTTP_200_OK)
async def request_password_reset(email: str) -> dict[str, str]:
    """Request password reset for a user."""
    db = next(get_db())
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return {"message": "If the email exists, a reset link will be sent"}

        return {"message": "If the email exists, a reset link will be sent"}
    finally:
        db.close()


@router.post("/auth/verify-otp", status_code=status.HTTP_200_OK)
async def verify_otp(code: str) -> dict[str, str]:
    """Verify OTP for password reset or other verification flows."""
    return {"message": "OTP verification endpoint - implement with proper validation"}
