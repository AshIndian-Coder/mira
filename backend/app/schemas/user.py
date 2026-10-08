from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

ROLES = ["admin", "data_steward", "reviewer", "auditor"]

# Roles tied to a single organisation. These must be bound to a CPSE,
# otherwise the account would implicitly have national visibility.
# reviewer is a government officer with national scope and needs no CPSE.
CPSE_BOUND_ROLES = ["data_steward"]

MIN_PASSWORD_LENGTH = 10
SPECIAL_CHARS = "@#$%&*!?"


def validate_password_strength(value: str) -> str:
    """Shared password policy for issued and user-chosen passwords."""
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    if not any(c.islower() for c in value):
        raise ValueError("password must contain a lowercase letter")
    if not any(c.isupper() for c in value):
        raise ValueError("password must contain an uppercase letter")
    if not any(c.isdigit() for c in value):
        raise ValueError("password must contain a digit")
    if not any(c in SPECIAL_CHARS for c in value):
        raise ValueError(f"password must contain one of {SPECIAL_CHARS}")
    return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    role: str = Field(default="reviewer", description="One of: " + ", ".join(ROLES))
    cpse_id: Optional[int] = Field(default=None, description="NULL for national-level users")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ROLES:
            raise ValueError(f"role must be one of: {', '.join(ROLES)}")
        return v


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    cpse_id: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ROLES:
            raise ValueError(f"role must be one of: {', '.join(ROLES)}")
        return v


class ChangePasswordRequest(BaseModel):
    email: EmailStr
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)

    @field_validator("new_password")
    @classmethod
    def check_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: Optional[str] = None
    role: str
    cpse_id: Optional[int] = None
    cpse_short_code: Optional[str] = None
    is_active: bool
    must_change_password: bool = False
    created_at: Optional[datetime] = None

    @classmethod
    def from_orm_object(cls, user) -> "UserResponse":
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            cpse_id=user.cpse_id,
            cpse_short_code=user.cpse.short_code if getattr(user, "cpse", None) else None,
            is_active=bool(user.is_active),
            must_change_password=bool(getattr(user, "must_change_password", False)),
            created_at=user.created_at,
        )


class UserCreatedResponse(UserResponse):
    """Returned only by POST /users and POST /users/{id}/reset-password.

    Carries the plaintext temporary password exactly once. It is never
    persisted and can never be retrieved again.
    """

    temporary_password: str


class PasswordResetResponse(BaseModel):
    user: UserResponse
    temporary_password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Seconds until token expiry")
    user: UserResponse


class RefreshRequest(BaseModel):
    access_token: str


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int = 1
    page_size: int = 50


class CpseOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    short_code: str