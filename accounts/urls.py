from django.urls import path
from . import views

urlpatterns = [
    path("auth/csrf/", views.CsrfView.as_view(), name="auth-csrf"),
    path("auth/signup/", views.SignupView.as_view(), name="auth-signup"),
    path("auth/login/", views.LoginView.as_view(), name="auth-login"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", views.MeView.as_view(), name="auth-me"),
    path("admin/staff/", views.StaffCreateView.as_view(), name="auth-staff"),
    path("auth/password-reset/", views.PasswordResetView.as_view(), name="auth-reset"),
    path("auth/password-reset/confirm/", views.PasswordResetConfirmView.as_view(), name="auth-reset-confirm"),
]
