from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.http import require_GET


@require_GET
def demo_marker(request):
    return JsonResponse({"isolated_demo": "test_subscription_demo"})


urlpatterns = [path("__demo__/", demo_marker), path("", include("config.urls"))]
