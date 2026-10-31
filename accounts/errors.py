from django.http import JsonResponse
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler as default_handler


def exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(getattr(exc, "message_dict", exc.messages))
    return default_handler(exc, context)


def csrf_failure(request, reason=""):
    return JsonResponse({"detail": "CSRF verification failed. Refresh the CSRF token and retry."}, status=403)
