from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages


def material_manager_required(view_func):
    """教材管理者権限が必要なビューのデコレータ"""
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        if not hasattr(request.user, 'profile') or not request.user.profile.is_material_manager:
            messages.error(request, '教材の管理には管理者権限が必要です。')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def check_material_manager_permission(user):
    """ユーザーが教材管理者かどうかをチェック"""
    if not user.is_authenticated:
        return False
    if not hasattr(user, 'profile'):
        return False
    return user.profile.is_material_manager
