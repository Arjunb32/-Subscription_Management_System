import logging

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .attempts import limit_attempts, request_ip
from .models import User
from .permissions import IsApplicationAdmin
from .serializers import CreateAccountSerializer, EmailSerializer, LoginSerializer, ResetConfirmSerializer, UserSerializer

logger = logging.getLogger(__name__)


@method_decorator(never_cache, name="dispatch")
class AuthAPIView(APIView):
    """Authentication responses must not be stored by shared/browser caches."""


@method_decorator(csrf_protect, name="dispatch")
@method_decorator(sensitive_post_parameters("password", "new_password", "token"), name="dispatch")
class CsrfProtectedAPIView(AuthAPIView):
    """Enforce CSRF even for anonymous login/signup/reset requests."""


class CsrfView(AuthAPIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class SignupView(CsrfProtectedAPIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CreateAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        limit_attempts("signup", [(f"ip:{request_ip(request)}", 10, 3600)])
        return create_account(serializer.validated_data, User.Role.CUSTOMER)


@sensitive_variables()
def create_account(data, role):
    try:
        with transaction.atomic():
            user = User.objects.create_user(**data, role=role)
    except IntegrityError:
        raise ValidationError({"email": ["An account with this email already exists."]}) from None
    except DjangoValidationError as exc:
        raise ValidationError(getattr(exc, "message_dict", exc.messages)) from None
    return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(CsrfProtectedAPIView):
    permission_classes = [AllowAny]

    @sensitive_variables()
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        limit_attempts("login", [
            (f"email:{data['email']}", 5, 900),
            (f"ip:{request_ip(request)}", 30, 900),
        ])
        user = authenticate(request, email=data["email"], password=data["password"])
        if user is None:
            raise ValidationError({"detail": "Invalid email or password."})
        login(request, user)
        return Response(UserSerializer(user).data)


class LogoutView(CsrfProtectedAPIView):
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(AuthAPIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class StaffCreateView(CsrfProtectedAPIView):
    permission_classes = [IsApplicationAdmin]

    def post(self, request):
        serializer = CreateAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return create_account(serializer.validated_data, User.Role.STAFF)


class PasswordResetView(CsrfProtectedAPIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        limit_attempts("reset", [
            (f"email:{email}", 3, 3600), (f"ip:{request_ip(request)}", 10, 3600),
        ])
        form = PasswordResetForm({"email": email})
        if form.is_valid():
            try:
                form.save(
                    request=request,
                    email_template_name="accounts/password_reset_email.txt",
                    subject_template_name="accounts/password_reset_subject.txt",
                    extra_email_context={"reset_url": settings.PASSWORD_RESET_URL},
                )
            except Exception:
                # Never expose account existence, SMTP credentials, or tokens.
                logger.error("Password-reset email could not be delivered; check the configured mail service.")
        return Response({"detail": "If an eligible account exists, password reset instructions will be sent."}, status=202)


class PasswordResetConfirmView(CsrfProtectedAPIView):
    permission_classes = [AllowAny]

    @sensitive_variables()
    def post(self, request):
        limit_attempts("reset-confirm", [(f"ip:{request_ip(request)}", 20, 3600)])
        serializer = ResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            uid = int(force_str(urlsafe_base64_decode(data["uid"])))
            if uid < 1 or uid > 9223372036854775807:
                raise ValueError
        except (ValueError, TypeError, UnicodeDecodeError, OverflowError):
            raise ValidationError({"detail": "Invalid or expired reset link."}) from None
        with transaction.atomic():
            user = User.objects.select_for_update().filter(pk=uid, is_active=True).first()
            if user is None or not user.has_usable_password() or not default_token_generator.check_token(user, data["token"]):
                raise ValidationError({"detail": "Invalid or expired reset link."})
            try:
                validate_password(data["new_password"], user)
            except DjangoValidationError as exc:
                raise ValidationError({"new_password": exc.messages}) from None
            user.set_password(data["new_password"])
            user.save(update_fields=["password"])
        return Response({"detail": "Password changed. Sign in with your new password."})
