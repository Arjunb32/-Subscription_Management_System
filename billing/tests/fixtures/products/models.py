from decimal import Decimal
from django.db import models


class Product(models.Model):
    name = models.CharField(max_length=255)
    product_type = models.CharField(max_length=50, default="service")
    sales_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    name = models.CharField(max_length=255)
    price_extra = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    def __str__(self):
        return f"{self.product.name} ({self.name})"

