from __future__ import annotations

import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rbac import ROLE_ADMIN, ROLE_DATA_STEWARD, require_permission, require_roles
from app.core.security import get_current_active_user, hash_password
from app.models.cpse import Cpse
from app.models.user import User
from app.schemas.user import (
    CPSE_BOUND_ROLES,
    SPECIAL_CHARS,
    CpseOption,
    PasswordResetResponse,
    UserCreate,
    UserCreatedResponse,
    UserListResponse,
    UserResponse,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["Users"])


def generate_password(length: int = 14) -> str:
    """Cryptographically random password satisfying the project password policy."""
    alphabet = string.ascii_letters + string.digits + SPECIAL_CHARS
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in candidate)
            and any(c.isupper() for c in candidate)
            and any(c.isdigit() for c in candidate)
            and any(c in SPECIAL_CHARS for c in candidate)
        ):
            return candidate


# Only the data steward acts for a single organisation. Reviewer is a
# government officer with national scope; admin and auditor oversee the
# whole system. None of them may be tied to one CPSE.
CPSE_BOUND_ROLES = {ROLE_DATA_STEWARD}


def _validate_cpse_assignment(role: str, cpse_id: int | None) -> None:
    """Enforce that only CPSE-bound roles carry a cpse_id."""
    if role in CPSE_BOUND_ROLES and cpse_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"role '{role}' must be assigned to a CPSE — it acts for a single organisation",
        )
    if role not in CPSE_BOUND_ROLES and cpse_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"role '{role}' operates nationally and cannot be assigned to a CPSE",
        )


@router.get("/cpses", response_model=list[CpseOption])
def list_cpses(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List active CPSEs for user assignment dropdowns."""
    cpses = db.query(Cpse).filter(Cpse.is_active == True).order_by(Cpse.short_code).all()
    return [CpseOption.model_validate(c) for c in cpses]


@router.get("", response_model=UserListResponse)
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    role: str | None = None,
    current_user: User = Depends(require_permission("manage_users")),
    db: Session = Depends(get_db),
):
    """List system users (Admin only)."""
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)

    total = query.count()
    items = query.order_by(User.id).offset((page - 1) * page_size).limit(page_size).all()

    return UserListResponse(
        items=[UserResponse.from_orm_object(u) for u in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=UserCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    current_user: User = Depends(require_permission("manage_users")),
    db: Session = Depends(get_db),
):
    """Create a user and issue temporary credentials (Admin only).

    The password is generated here, returned once in the response, and never
    stored in plaintext. The new user cannot log in to the API until they
    change it via POST /api/auth/change-password.
    """
    email = payload.email.lower()

    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{payload.email}' already exists",
        )

    _validate_cpse_assignment(payload.role, payload.cpse_id)

    if payload.cpse_id is not None:
        cpse = db.query(Cpse).filter(Cpse.id == payload.cpse_id).first()
        if cpse is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CPSE {payload.cpse_id} does not exist",
            )

    temporary_password = generate_password()

    new_user = User(
        email=email,
        password_hash=hash_password(temporary_password),
        full_name=payload.full_name,
        role=payload.role,
        cpse_id=payload.cpse_id,
        is_active=True,
        must_change_password=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return UserCreatedResponse(
        **UserResponse.from_orm_object(new_user).model_dump(),
        temporary_password=temporary_password,
    )


@router.post("/{user_id}/reset-password", response_model=PasswordResetResponse)
def reset_password(
    user_id: int,
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    """Issue a fresh temporary password and force a change on next login (Admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    temporary_password = generate_password()
    user.password_hash = hash_password(temporary_password)
    user.must_change_password = True
    db.commit()
    db.refresh(user)

    return PasswordResetResponse(
        user=UserResponse.from_orm_object(user),
        temporary_password=temporary_password,
    )


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get single user profile (Admin or self)."""
    if current_user.role != ROLE_ADMIN and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view profile of other users",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    return UserResponse.from_orm_object(user)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update user attributes (Admin or self)."""
    if current_user.role != ROLE_ADMIN and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot update other users",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    if payload.full_name is not None:
        user.full_name = payload.full_name

    # Only admin can change role, cpse_id, or active status
    if current_user.role == ROLE_ADMIN:
        if payload.role is not None:
            user.role = payload.role
        if "cpse_id" in payload.model_fields_set:
            user.cpse_id = payload.cpse_id
        elif payload.cpse_id is not None:
            user.cpse_id = payload.cpse_id
        if payload.is_active is not None:
            user.is_active = payload.is_active

        _validate_cpse_assignment(user.role, user.cpse_id)

    db.commit()
    db.refresh(user)
    return UserResponse.from_orm_object(user)


@router.delete("/{user_id}", response_model=UserResponse)
def deactivate_user(
    user_id: int,
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    """Deactivate a user account (Admin only)."""
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own administrator account",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    user.is_active = False
    db.commit()
    db.refresh(user)
    return UserResponse.from_orm_object(user)