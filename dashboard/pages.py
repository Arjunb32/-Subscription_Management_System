from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from accounts.models import User


def _page_context(request, page):
    today = timezone.localdate()
    return {
        "page": page,
        "demo_mode": settings.DEBUG,
        "period_from": today.replace(day=1).isoformat(),
        "period_to": today.isoformat(),
    }


@require_GET
@never_cache
@login_required(login_url="/login/")
def overview(request):
    if not request.user.is_active or request.user.role != User.Role.ADMIN:
        raise PermissionDenied("The dashboard is available to application admins only.")
    return render(request, "dashboard/overview.html", _page_context(request, "overview"))


@require_GET
@never_cache
@login_required(login_url="/login/")
def customer_portal(request):
    if not request.user.is_active or request.user.role != User.Role.CUSTOMER:
        raise PermissionDenied("The customer portal is available to customer accounts only.")
    return render(request, "dashboard/portal.html", _page_context(request, "portal"))
