from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Product(models.Model):
    name = models.CharField(max_length=255)
    product_type = models.CharField(max_length=50, default="service")
    sales_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_system = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [models.CheckConstraint(condition=models.Q(sales_price__gte=0, cost_price__gte=0), name="product_nonnegative_prices")]

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="variants")
    name = models.CharField(max_length=255)
    values = models.JSONField(default=dict, blank=True)
    price_extra = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["product_id", "name", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["product", "name"], name="variant_product_name_unique"),
            models.CheckConstraint(condition=models.Q(price_extra__gte=0), name="variant_nonnegative_price"),
        ]

    def __str__(self):
        return f"{self.product} ({self.name})"
