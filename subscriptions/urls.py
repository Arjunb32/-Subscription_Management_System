from rest_framework.routers import DefaultRouter
from .views import PlanViewSet, TaxViewSet, TemplateViewSet, SubscriptionViewSet, MySubscriptionViewSet, CustomerViewSet

router = DefaultRouter()
router.register("plans", PlanViewSet)
router.register("tax-rules", TaxViewSet)
router.register("quotation-templates", TemplateViewSet)
router.register("subscriptions", SubscriptionViewSet)
router.register("my/subscriptions", MySubscriptionViewSet, basename="my-subscriptions")
router.register("customers", CustomerViewSet, basename="customers")
urlpatterns = router.urls
