from rest_framework import serializers
from rest_framework.routers import DefaultRouter

from subscriptions.api_common import ManagedViewSet, StrictModelSerializer
from .models import Product, ProductVariant


class ProductSerializer(StrictModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "name", "product_type", "sales_price", "cost_price", "notes", "is_active"]


class VariantSerializer(StrictModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = ProductVariant
        fields = ["id", "product", "product_name", "name", "values", "price_extra", "is_active"]

    def validate_product(self, product):
        if product.is_system or not product.is_active:
            raise serializers.ValidationError("Choose an active catalog product.")
        if self.instance and product.pk != self.instance.product_id:
            raise serializers.ValidationError("A variant cannot be moved to another product.")
        return product

    def validate_values(self, values):
        if not isinstance(values, dict) or any(not isinstance(v, str) for v in values.values()):
            raise serializers.ValidationError("Use a JSON object with text values.")
        return values


class ProductViewSet(ManagedViewSet):
    serializer_class = ProductSerializer
    queryset = Product.objects.filter(is_system=False)

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("search"):
            qs = qs.filter(name__icontains=params["search"][:255])
        if params.get("is_active") in ("true", "false"):
            qs = qs.filter(is_active=params["is_active"] == "true")
        return qs


class VariantViewSet(ManagedViewSet):
    serializer_class = VariantSerializer
    queryset = ProductVariant.objects.select_related("product")

    def get_queryset(self):
        qs = super().get_queryset()
        product = self.request.query_params.get("product")
        if product:
            if not product.isdecimal():
                raise serializers.ValidationError({"product": "Use an integer ID."})
            qs = qs.filter(product_id=product)
        return qs


router = DefaultRouter()
router.register("products", ProductViewSet)
router.register("variants", VariantViewSet)
urlpatterns = router.urls
