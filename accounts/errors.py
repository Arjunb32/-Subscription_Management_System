from django.http import JsonResponse
from rest_framework.views import exception_handler as default_handler


def exception_handler(exc, context):
    return default_handler(exc, context)


def csrf_failure(request, reason=""):
    return JsonResponse({"detail": "CSRF verification failed. Refresh the CSRF token and retry."}, status=403)
