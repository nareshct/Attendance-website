from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """Staff/superuser accounts only — the two CEOs."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class IsTrainer(BasePermission):
    """Accounts with a linked Trainer profile only."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and hasattr(request.user, 'trainer'))


class IsAdminOrTrainer(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or hasattr(request.user, 'trainer'))
        )


class IsClient(BasePermission):
    """Accounts with a linked Client profile only."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and hasattr(request.user, 'client'))
