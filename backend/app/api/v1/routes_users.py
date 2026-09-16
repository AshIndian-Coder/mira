"""User management endpoints (UserManagement page, admin only).

    GET    /api/v1/users              List users
    POST   /api/v1/users              Create user
    PUT    /api/v1/users/{user_id}    Update user (role, cpse, password, ...)
    DELETE /api/v1/users/{user_id}    Deactivate user (soft delete)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.rbac import require_permission
from app.core.security import hash_password
from app.db.postgres import get_db
from app.models.cpse import Cpse
from app.models.user import User
from app.schemas.user_schema import (
    DeactivateUserResponse,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from app.services.audit.audit_service import log_action
from app.utils.constants import (
    AUDIT_CREATE_USER,
    AUDIT_DEACTIVATE_USER,
    AUDIT_UPDATE_USER,
    ROLES,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserListResponse)
def list_users(
    role: str = Query(default=None),
    cpse_id: int = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_users")),
):
    """List all users (optional role / CPSE filters)."""
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    if cpse_id:
        query = query.filter(User.cpse_id == cpse_id)
    total = query.count()
    items = (
        query.order_by(desc(User.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return UserListResponse(
        items=[UserResponse.from_orm_object(u) for u in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=UserResponse, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_users")),
):
    """Create a new user (admin only)."""
    if payload.cpse_id is not None:
        cpse = db.query(Cpse).filter(Cpse.id == payload.cpse_id).first()
        if cpse is None:
            raise HTTPException(status_code=404, detail="CPSE not found")
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        cpse_id=payload.cpse_id,
        is_active=True,
    )
    db.add(user)
    db.flush()
    log_action(
        db,
        current_user,
        AUDIT_CREATE_USER,
        entity_type="user",
        entity_id=user.id,
        changes={"email": user.email, "role": user.role, "cpse_id": user.cpse_id},
        commit=True,
    )
    return UserResponse.from_orm_object(user)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_users")),
):
    """Update role / CPSE / name / password / active flag (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.role is not None:
        if payload.role not in ROLES:
            raise HTTPException(status_code=400, detail=f"role must be one of: {', '.join(ROLES)}")
    if payload.cpse_id is not None:
        cpse = db.query(Cpse).filter(Cpse.id == payload.cpse_id).first()
        if cpse is None:
            raise HTTPException(status_code=404, detail="CPSE not found")

    changes = {}
    if payload.full_name is not None:
        changes["full_name"] = {"old": user.full_name, "new": payload.full_name}
        user.full_name = payload.full_name
    if payload.role is not None:
        changes["role"] = {"old": user.role, "new": payload.role}
        user.role = payload.role
    if payload.cpse_id is not None:
        changes["cpse_id"] = {"old": user.cpse_id, "new": payload.cpse_id}
        user.cpse_id = payload.cpse_id
    if payload.password is not None:
        changes["password"] = {"old": "***", "new": "***"}
        user.password_hash = hash_password(payload.password)
    if payload.is_active is not None:
        changes["is_active"] = {"old": user.is_active, "new": payload.is_active}
        user.is_active = payload.is_active
    if not changes:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    log_action(
        db,
        current_user,
        AUDIT_UPDATE_USER,
        entity_type="user",
        entity_id=user.id,
        changes=changes,
        commit=True,
    )
    return UserResponse.from_orm_object(user)


@router.delete("/{user_id}", response_model=DeactivateUserResponse)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_users")),
):
    """Soft-delete: deactivate the account (audit rows stay intact)."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    user.is_active = False
    log_action(
        db,
        current_user,
        AUDIT_DEACTIVATE_USER,
        entity_type="user",
        entity_id=user.id,
        changes={"email": user.email},
        commit=True,
    )
    return DeactivateUserResponse(
        message="User deactivated", user=UserResponse.from_orm_object(user)
    )

