from django.db.models import Q, Prefetch
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from accounts.models import User
from accounts.permissions import IsApplicationAdmin, scope_customer_queryset
from .api_common import ManagedViewSet, Pagination, StaffPermission, domain_error
from .models import Plan, TaxRule, QuotationTemplate, Subscription, SubscriptionLine
from .serializers import PlanSerializer, TaxSerializer, TemplateSerializer, SubscriptionWriteSerializer, SubscriptionSerializer
from .services import transition


class PlanViewSet(ManagedViewSet):
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer


class TaxViewSet(ManagedViewSet):
    queryset = TaxRule.objects.all()
    serializer_class = TaxSerializer

    def get_permissions(self):
        return [StaffPermission() if self.request.method in ("GET", "HEAD", "OPTIONS") else IsApplicationAdmin()]


class TemplateViewSet(ManagedViewSet):
    queryset = QuotationTemplate.objects.select_related("plan").prefetch_related("lines__product", "lines__product_variant", "lines__tax_rule")
    serializer_class = TemplateSerializer


class SubscriptionViewSet(ManagedViewSet):
    queryset = Subscription.objects.select_related("customer", "plan").prefetch_related(Prefetch("lines", queryset=SubscriptionLine.objects.select_related("product", "product_variant", "tax_rule")))
    http_method_names = ["get", "post", "patch", "put", "head", "options"]

    def get_permissions(self):
        if self.action in ("retrieve", "lifecycle"):
            return [IsAuthenticated()]
        return [StaffPermission()]

    def get_queryset(self):
        qs = scope_customer_queryset(super().get_queryset(), self.request.user, allow_staff=True)
        params = self.request.query_params
        for key in ("customer", "plan"):
            if params.get(key):
                if not params[key].isdecimal() or len(params[key]) > 18:
                    raise serializers.ValidationError({key: "Use an integer ID."})
                qs = qs.filter(**{f"{key}_id": params[key]})
        if params.get("status"):
            if params["status"] not in Subscription.Status.values:
                raise serializers.ValidationError({"status": "Unknown subscription status."})
            qs = qs.filter(status=params["status"])
        for key, lookup in (("start_date_from", "start_date__gte"), ("start_date_to", "start_date__lte")):
            if params.get(key):
                value = serializers.DateField().run_validation(params[key])
                qs = qs.filter(**{lookup: value})
        if params.get("search"):
            qs = qs.filter(Q(subscription_number__icontains=params["search"][:100]) | Q(customer__email__icontains=params["search"][:100]) | Q(plan__name__icontains=params["search"][:100]))
        return qs

    def get_serializer_class(self):
        return SubscriptionWriteSerializer if self.action in ("create", "update", "partial_update") else SubscriptionSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sub = serializer.save()
        return Response(SubscriptionSerializer(self.get_queryset().get(pk=sub.pk), context={"request": request}).data, status=201)

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        sub = serializer.save()
        return Response(SubscriptionSerializer(self.get_queryset().get(pk=sub.pk), context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path=r"actions/(?P<operation>quote|confirm|activate|pause|resume|renew|close)")
    def lifecycle(self, request, pk=None, operation=None):
        if request.data:
            raise serializers.ValidationError({"detail": "Actions accept an empty JSON object; dates are server controlled."})
        sub = self.get_object()
        try:
            transition(sub.pk, operation, request.user)
        except Exception as exc:
            domain_error(exc)
        return Response(SubscriptionSerializer(self.get_queryset().get(pk=sub.pk), context={"request": request}).data)


class MySubscriptionViewSet(SubscriptionViewSet):
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        if not self.request.user.is_authenticated or self.request.user.role != "customer":
            raise PermissionDenied("This endpoint is for the current customer only.")
        if self.action not in ("list", "retrieve", "lifecycle"):
            raise PermissionDenied("Customers can read and use permitted actions only.")
        return [IsAuthenticated()]


class CustomerViewSet(ReadOnlyModelViewSet):
    class CustomerSerializer(serializers.ModelSerializer):
        class Meta:
            model = User
            fields = ["id", "email", "first_name", "last_name"]
    permission_classes = [StaffPermission]
    pagination_class = Pagination
    serializer_class = CustomerSerializer
    queryset = User.objects.filter(role="customer", is_active=True).order_by("email", "pk")

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("search"):
            qs = qs.filter(email__icontains=self.request.query_params["search"][:254])
        return qs
