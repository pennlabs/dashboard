"""DRF permission classes for the dashboard."""

from rest_framework.permissions import BasePermission


class IsTeamLead(BasePermission):
    """Allow only signed-in Penn Labs team leads.

    This is the project-wide default (see `DEFAULT_PERMISSION_CLASSES` in
    settings/base.py), so every endpoint is closed unless it opts out with an
    explicit `@permission_classes([AllowAny])`.

    The `is_staff` flag is set from the user's Platform permissions on each
    login -- see `deployments.backends.DashboardUserBackend` for how a lead is
    identified.
    """

    message = "The dashboard is currently limited to Penn Labs team leads."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff)
