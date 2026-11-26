# app/billiard/utils/permissions.py
# Billiard permissions on top of the existing permission system (Role.permissions JSON +
# User.has_permission). Same idea as app/payments/utils/permissions.py, but per permission.
#
#   billiard.billing_review.view     list the sessions waiting for a billing decision
#   billiard.billing_review.resolve  assign a package / confirm normal pricing (implies view)
#
# Granted by default to admin, super admin and manager (no role entry needed). Anyone else,
# for example a trusted cashier, needs the permission in one of their roles' `permissions`.
# The board and the bill still SHOW that a session needs review to everybody (a cashier must
# be able to see why a payment is blocked); the permission is for the list and the decision.
from fastapi import Depends, HTTPException, status

from app.user.models.user import User
from app.user.utils.token import get_current_user

BILLING_REVIEW_VIEW = "billiard.billing_review.view"
BILLING_REVIEW_RESOLVE = "billiard.billing_review.resolve"

ALL_PERMISSIONS = (BILLING_REVIEW_VIEW, BILLING_REVIEW_RESOLVE)
_IMPLIED_BY = {BILLING_REVIEW_VIEW: (BILLING_REVIEW_RESOLVE,)}     # whoever may resolve may also view


def has_billiard_permission(user: User, permission: str) -> bool:
    if user.is_admin() or user.has_role("manager"):          # default grant (is_admin includes super admin)
        return True
    return any(user.has_permission(p) for p in (permission, *_IMPLIED_BY.get(permission, ())))


def require_billiard_permission(permission: str):
    """Dependency factory: 403 unless the user holds `permission` (see has_billiard_permission)."""
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
        if not has_billiard_permission(current_user, permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Permission '{permission}' required")
        return current_user
    return dependency
