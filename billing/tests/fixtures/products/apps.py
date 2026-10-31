from django.apps import AppConfig


class ProductsFixtureConfig(AppConfig):
    name = "billing.tests.fixtures.products"
    label = "products"
    verbose_name = "Products Test Fixtures"
