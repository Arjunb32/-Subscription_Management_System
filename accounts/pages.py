from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@require_GET
@never_cache
def home(request):
    return redirect("account-page" if request.user.is_authenticated else "login-page")


@require_GET
@never_cache
def authentication_page(request, page):
    if page in {"login", "signup"} and request.user.is_authenticated:
        return redirect("account-page")
    return render(request, f"accounts/{page}.html", {
        "page": page,
        "console_email": settings.DEBUG and settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend",
    })


@require_GET
@never_cache
@login_required(login_url="/login/")
def account(request):
    return render(request, "accounts/account.html", {"page": "account"})
