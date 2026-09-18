from __future__ import annotations

from typing import Callable, Set

from fastapi import Depends, HTTPException, status

from app.core.security import get_current_active_user
from app.models.user import User

# ---------------------------------------------------------------------- #
# Role definitions
# ---------------------------------------------------------------------- #
ROLE_ADMIN = "admin"
ROLE_DATA_STEWARD = "data_steward"
ROLE_REVIEWER = "reviewer"
ROLE_AUDITOR = "auditor"

ROLES: list[str] = [ROLE_ADMIN, ROLE_DATA_STEWARD, ROLE_REVIEWER, ROLE_AUDITOR]
ALL_ROLES: Set[str] = set(ROLES)

# Permission matrix: action -> set of roles allowed to perform it
PERMISSIONS: dict[str, Set[str]] = {
    # Materials / Ingestion
    "upload_data": {ROLE_ADMIN, ROLE_DATA_STEWARD},
    "view_materials": ALL_ROLES,
    "clear_materials": {ROLE_ADMIN, ROLE_DATA_STEWARD},
    # Matching
    "run_matching": {ROLE_ADMIN, ROLE_DATA_STEWARD},
    "view_matches": ALL_ROLES,
    # Review workflow
    "review_match": {ROLE_ADMIN, ROLE_REVIEWER},
    "view_review_queue": ALL_ROLES,
    # Mappings & Harmonization
    "create_mapping": {ROLE_ADMIN, ROLE_DATA_STEWARD},
    "view_mappings": ALL_ROLES,
    # Analytics & Dashboard
    "view_analytics": ALL_ROLES,
    # Audit & Governance
    "view_audit": {ROLE_ADMIN, ROLE_AUDITOR, ROLE_DATA_STEWARD},
    # User Management
    "manage_users": {ROLE_ADMIN},
}


def has_permission(role: str, action: str) -> bool:
    """True if role is permitted to perform action."""
    if action not in PERMISSIONS:
        return False
    return role in PERMISSIONS[action]


def check_permission(user: User, action: str) -> None:
    """Raise HTTP 403 if user lacks required permission."""
    if user.role not in ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unknown role: {user.role}",
        )
    if not has_permission(user.role, action):
        allowed = sorted(PERMISSIONS.get(action, set()))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{user.role}' is not authorized to perform '{action}'. Allowed roles: {allowed}",
        )


def require_permission(action: str) -> Callable[..., User]:
    """Dependency factory: Authorize active user for action."""

    def dependency(user: User = Depends(get_current_active_user)) -> User:
        check_permission(user, action)
        return user

    return dependency


def require_roles(*roles: str) -> Callable[..., User]:
    """Dependency factory: Authorize user belonging to explicit set of roles."""
    allowed = set(roles)

    def dependency(user: User = Depends(get_current_active_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not in allowed roles: {sorted(allowed)}",
            )
        return user

    return dependency
