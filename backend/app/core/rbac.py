"""Role-Based Access Control.

``require_permission("review_match")`` returns a FastAPI dependency that
loads the current user and rejects with 403 unless the user's role is in
the permission matrix for that action (see app.utils.constants.PERMISSIONS).
"""
from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException, status

from app.core.security import get_current_active_user
from app.models.user import User
from app.utils.constants import PERMISSIONS, ROLES


def has_permission(role: str, action: str) -> bool:
    """True when ``role`` may perform ``action``."""
    if action not in PERMISSIONS:
        # Unknown actions are denied by default (fail closed).
        return False
    return role in PERMISSIONS[action]


def check_permission(user: User, action: str) -> None:
    """Raise 403 when the user's role lacks the permission (fail closed)."""
    if user.role not in ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unknown role: {user.role}",
        )
    if not has_permission(user.role, action):
        allowed = sorted(PERMISSIONS.get(action, set()))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Role '{user.role}' is not allowed to perform '{action}'. "
                f"Allowed roles: {allowed}"
            ),
        )


def require_permission(action: str) -> Callable[..., User]:
    """Dependency factory: authorize the current user for ``action``."""

    def dependency(
        user: User = Depends(get_current_active_user),
    ) -> User:
        check_permission(user, action)
        return user

    return dependency


def require_roles(*roles: str) -> Callable[..., User]:
    """Dependency factory: allow only the given roles (explicit list)."""
    allowed = set(roles)

    def dependency(
        user: User = Depends(get_current_active_user),
    ) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not in the allowed roles: {sorted(allowed)}",
            )
        return user

    return dependency

