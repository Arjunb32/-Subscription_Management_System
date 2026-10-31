# Subscription Management System

## Project Structure

```
├── billing/                    # Billing, Invoices & Payments app
│   ├── models.py               # Discount, Invoice, InvoiceLine, Payment
│   ├── services.py             # Business logic (invoice generation, discounts, payments)
│   ├── serializers.py          # DRF serializers
│   ├── views.py                # API views (staff + customer portal)
│   ├── urls.py                 # /api/billing/...
│   ├── filters.py              # django-filter filtersets
│   ├── permissions.py          # IsAdminUser, IsStaffOrAdmin, IsStaffOrOwner
│   ├── signals.py              # Payment → Invoice reconciliation
│   ├── admin.py                # Django admin registration
│   ├── management/
│   │   └── commands/
│   │       └── generate_invoices.py   # `python manage.py generate_invoices`
│   ├── tests/
│   │   ├── test_models.py
│   │   ├── test_services.py
│   │   └── test_views.py
│   └── migrations/
├── README.md
```

## Billing App — Integration Guide

### 1. Add to `INSTALLED_APPS`

```python
INSTALLED_APPS = [
    ...
    "rest_framework",
    "django_filters",
    "subscriptions",      # your app
    "products",           # your app
    "billing",            # this app
]
```

### 2. REST Framework config

```python
REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}
```

### 3. Include URLs

```python
# project/urls.py
from django.urls import path, include

urlpatterns = [
    ...
    path("api/billing/", include("billing.urls")),
]
```

### 4. pip dependencies

```
djangorestframework
django-filter
python-dateutil
```

### 5. Cross-app model dependencies

The billing app references these models via string-based ForeignKeys:

| Reference                        | Expected fields                                                                                               |
|----------------------------------|---------------------------------------------------------------------------------------------------------------|
| `subscriptions.Subscription`     | `customer` (FK→User), `plan` (FK→Plan), `status`, `current_period_start`, `current_period_end`, `payment_terms_days`, `lines` (reverse FK) |
| `subscriptions.SubscriptionLine` | `product`, `product_variant` (nullable), `quantity`, `unit_price`, `tax_rule` (nullable)                       |
| `subscriptions.TaxRule`          | `name`, `rate` (Decimal, percentage), `is_active`                                                             |
| `products.Product`               | Standard model with `__str__`                                                                                 |
| `products.ProductVariant`        | Standard model with `__str__`                                                                                 |
| `Plan` (via Subscription)        | `billing_interval` (choices: `daily`, `weekly`, `monthly`, `yearly`)                                          |

> **If your app labels differ**, update the FK strings in `billing/models.py`.

### 6. Run migrations

```bash
python manage.py makemigrations billing
python manage.py migrate
```

### 7. Billing-day invoice generation

```bash
# Via management command (for cron / scheduled tasks)
python manage.py generate_invoices
python manage.py generate_invoices --date 2026-10-31

# Via API
POST /api/billing/invoices/generate/
{"billing_date": "2026-10-31"}   # optional, defaults to today
```
