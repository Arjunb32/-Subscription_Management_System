from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.urls import path
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@require_GET
@never_cache
@login_required(login_url="/login/")
def management(request, section="subscriptions"):
    if not request.user.is_active or request.user.role not in ("admin", "staff"):
        raise PermissionDenied("Application staff access is required.")
    return render(request, "subscriptions/manage.html", {"section": section, "sections": ["subscriptions", "products", "variants", "plans", "tax-rules", "quotation-templates", "invoices", "payments", "discounts"]})


urlpatterns = [path("manage/", management, name="subscription-management")]
urlpatterns += [path(f"manage/{section}/", management, {"section": section}, name=f"manage-{section}") for section in ("subscriptions", "products", "variants", "plans", "tax-rules", "quotation-templates", "invoices", "payments", "discounts")]
