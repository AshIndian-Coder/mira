from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

ROLES = ["admin", "data_steward", "reviewer", "auditor"]


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
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
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)
    is_active: Optional[bool] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ROLES:
            raise ValueError(f"role must be one of: {', '.join(ROLES)}")
        return v


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: Optional[str] = None
    role: str
    cpse_id: Optional[int] = None
    cpse_short_code: Optional[str] = None
    is_active: bool
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
            created_at=user.created_at,
        )


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
