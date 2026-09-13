from rest_framework.permissions import BasePermission

from ..auth import user_is_manager, user_is_staff_or_manager


class IsStaffOrManager(BasePermission):
    def has_permission(self, request, view):
        return user_is_staff_or_manager(request.user)


class IsManager(BasePermission):
    def has_permission(self, request, view):
        return user_is_manager(request.user)
