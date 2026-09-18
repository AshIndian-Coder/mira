from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rbac import ROLE_ADMIN, require_permission, require_roles
from app.core.security import get_current_active_user, hash_password
from app.models.cpse import Cpse
from app.models.user import User
from app.schemas.user import CpseOption, UserCreate, UserListResponse, UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"])


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


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    current_user: User = Depends(require_permission("manage_users")),
    db: Session = Depends(get_db),
):
    """Create a new user (Admin only)."""
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{payload.email}' already exists",
        )

    new_user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        cpse_id=payload.cpse_id,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return UserResponse.from_orm_object(new_user)


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
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)

    # Only admin can change role, cpse_id, or active status
    if current_user.role == ROLE_ADMIN:
        if payload.role is not None:
            user.role = payload.role
        if payload.cpse_id is not None:
            user.cpse_id = payload.cpse_id
        if payload.is_active is not None:
            user.is_active = payload.is_active

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
