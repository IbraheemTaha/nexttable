from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .models import WorkerProfile


def user_is_staff_or_manager(user):
    if not user.is_authenticated:
        return False

    try:
        return user.worker_profile.role in {
            WorkerProfile.Role.STAFF,
            WorkerProfile.Role.MANAGER,
        }
    except WorkerProfile.DoesNotExist:
        return False


def user_is_manager(user):
    if not user.is_authenticated:
        return False

    try:
        return user.worker_profile.role == WorkerProfile.Role.MANAGER
    except WorkerProfile.DoesNotExist:
        return False


def staff_or_manager_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)

        if not user_is_staff_or_manager(request.user):
            raise PermissionDenied

        return view_func(request, *args, **kwargs)

    return wrapper


def manager_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)

        if not user_is_manager(request.user):
            raise PermissionDenied

        return view_func(request, *args, **kwargs)

    return wrapper
