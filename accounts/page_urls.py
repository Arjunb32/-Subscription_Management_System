from django.urls import path
from . import pages

urlpatterns = [
    path("", pages.home, name="home"),
    path("login/", pages.authentication_page, {"page": "login"}, name="login-page"),
    path("signup/", pages.authentication_page, {"page": "signup"}, name="signup-page"),
    path("password-reset/", pages.authentication_page, {"page": "password_reset"}, name="password-reset-page"),
    path("reset-password/", pages.authentication_page, {"page": "reset_password"}, name="reset-password-page"),
    path("account/", pages.account, name="account-page"),
]
