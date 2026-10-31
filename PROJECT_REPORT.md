# Subscription Management System — Implementation & Progress Report

**Project:** Subscription Management System (Brightloop Software Case Study)  
**Stack:** Django & Django REST Framework (DRF) with PostgreSQL  
**Architecture:** Shared Monolith with Modular Django Apps  
**Scope Covered:** Architectural Alignment, Shared Boundary Agreement, Billing, Invoices & Payments Subsystem  
**Date:** October 31, 2026  

---

## 1. Executive Summary

This report provides a comprehensive breakdown of the technical design, architectural decisions, and code implementation completed for the **Subscription Management System**. 

Following the business scenario outlined in the Brightloop Software specification, the platform addresses key challenges of recurring billing businesses: spreadsheet tracking, missed renewals, manual invoice drafting, bank statement reconciliation, and lack of real-time financial reporting.

To ensure frictionless team collaboration on GitHub, responsibilities were divided cleanly:
- **Common Backend & Auth (Collaborator/Lead):** Scaffolding, PostgreSQL setup, Custom User model, Role-Based Access Control (Admin, Staff, Customer), and Core Catalog/Subscription models (`Product`, `Plan`, `Subscription`).
- **Billing, Invoices & Payments Subsystem (Implemented Here):** Automated invoice generation, automated tax and discount calculation, payment recording with automatic status reconciliation, finance dashboard metrics, customer self-service billing portal, and management CLI commands.

---

## 2. Completed Scope & Deliverables

All deliverables have been organized into the self-contained `billing` app within the repository.

### Directory Structure of Deliverables

```
-Subscription_Management_System/
│
├── billing/
│   ├── __init__.py
│   ├── apps.py                         # App configuration and signal registration
│   ├── admin.py                        # Django Admin integration with tabular inlines
│   ├── models.py                       # Core data models: Discount, Invoice, InvoiceLine, Payment
│   ├── services.py                     # Centralized domain logic and billing engine
│   ├── serializers.py                  # DRF serializers (detail, list, create, summary)
│   ├── views.py                        # 13 REST API view classes
│   ├── urls.py                         # Dedicated endpoint routing under /api/billing/
│   ├── filters.py                      # Django-filter classes for querying and reporting
│   ├── permissions.py                  # Custom RBAC permissions (Admin, Staff, Owner/Customer)
│   ├── signals.py                      # Post-save/delete reconciliation signals for payments
│   ├── management/
│   │   └── commands/
│   │       ├── __init__.py
│   │       └── generate_invoices.py    # CLI command for scheduled/cron billing runs
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_models.py              # Model methods, properties, and tax calculations
│   │   ├── test_services.py            # Business logic and validation tests
│   │   └── test_views.py               # Permission and endpoint protection tests
│   └── migrations/
│       └── __init__.py
│
├── README.md                           # Team integration guide and app settings
└── PROJECT_REPORT.md                   # This detailed implementation report
```

---

## 3. Requirements Traceability Matrix

The implementation directly solves every operational issue described in the Brightloop specification:

| Problem in Brightloop Spec | Engineering Solution Implemented | Location in Code |
| :--- | :--- | :--- |
| **"Renewals get missed, invoices typed by hand"** | Automated batch invoice generation engine scans active subscriptions whose billing period has elapsed and generates complete draft invoices with all product lines, prices, and taxes. | [`billing/services.py`](file:///c:/Users/adduu/OneDrive/Desktop/susbscrption%20management%20system/-Subscription_Management_System/billing/services.py) |
| **"Nothing should be billed twice or skipped"** | Database-level composite `UniqueConstraint` on `(subscription, period_start, period_end)` plus transactional checks preventing duplicate generation. | [`billing/models.py`](file:///c:/Users/adduu/OneDrive/Desktop/susbscrption%20management%20system/-Subscription_Management_System/billing/models.py) |
| **"Taxes are calculated automatically from rules"** | Dynamic line calculation computing tax amounts based on assigned `TaxRule.rate` against post-discount subtotals. | [`billing/models.py#InvoiceLine.calculate`](file:///c:/Users/adduu/OneDrive/Desktop/susbscrption%20management%20system/-Subscription_Management_System/billing/models.py) |
| **"Discounts: fixed or percentage, min qty/purchase, limits"** | Configurable `Discount` model supporting fixed/percentage types, product vs. subscription scope, minimum spend/seat thresholds, date ranges, and max usage limits. Automatic greedy evaluation selects the highest-value eligible discount. | [`billing/models.py`](file:///c:/Users/adduu/OneDrive/Desktop/susbscrption%20management%20system/-Subscription_Management_System/billing/models.py), [`billing/services.py`](file:///c:/Users/adduu/OneDrive/Desktop/susbscrption%20management%20system/-Subscription_Management_System/billing/services.py) |
| **"Payments matched to invoices by scrolling bank statements"** | `Payment` recording linked directly to invoices. Signals trigger automatic recalculation of `amount_paid` and flip invoice state from `confirmed` to `paid` once settled. | [`billing/signals.py`](file:///c:/Users/adduu/OneDrive/Desktop/susbscrption%20management%20system/-Subscription_Management_System/billing/signals.py) |
| **"Finance lead: answering revenue questions takes days"** | Aggregated dashboard summary endpoint executing single-query DB aggregations (`Sum`, `Count`) with indexed fields, designed to respond in under 2 seconds. | [`billing/views.py#DashboardSummaryView`](file:///c:/Users/adduu/OneDrive/Desktop/susbscrption%20management%20system/-Subscription_Management_System/billing/views.py) |
| **"Customers see only their own subscriptions and invoices"** | Dedicated Customer Portal endpoints filtered strictly by `request.user`, paired with custom DRF object-level permission classes. | [`billing/views.py`](file:///c:/Users/adduu/OneDrive/Desktop/susbscrption%20management%20system/-Subscription_Management_System/billing/views.py), [`billing/permissions.py`](file:///c:/Users/adduu/OneDrive/Desktop/susbscrption%20management%20system/-Subscription_Management_System/billing/permissions.py) |

---

## 4. Deep-Dive: Architecture & Data Models

### 4.1. Loose Coupling with String References
To allow your collaborator to develop the `subscriptions` and `products` apps independently without circular dependency errors, all foreign keys reference models via strings (e.g., `"subscriptions.Subscription"`). Dynamic lookups use `django.apps.apps.get_model()`.

### 4.2. Schema Details

#### `Discount`
- **Fields:** `name`, `discount_type` (`fixed`, `percentage`), `value`, `min_purchase`, `min_quantity`, `start_date`, `end_date`, `max_uses`, `times_used`, `applies_to` (`product`, `subscription`), `products` (ManyToMany to `products.Product`), `is_active`, `created_by`.
- **Validation Helpers:** `is_valid_today` evaluates active status, validity calendar dates, and total usage limits against current time.

#### `Invoice`
- **Fields:** `invoice_number` (`INV-YYYYMM-XXXX` auto-generated sequentially), `subscription` (FK), `customer` (FK to User), `issue_date`, `due_date`, `period_start`, `period_end`, `subtotal`, `discount_amount`, `tax_amount`, `total`, `amount_paid`, `status` (`draft`, `confirmed`, `paid`, `cancelled`), `discount` (FK to Discount), `notes`.
- **Guards:** Composite unique constraint on `['subscription', 'period_start', 'period_end']`. Database indexes on `status`, `customer`, `due_date`, and `issue_date`.
- **Computed Properties:** `amount_due` (clamped to 0 minimum), `is_overdue` (unpaid and past `due_date`).

#### `InvoiceLine`
- **Fields:** `invoice` (FK with cascade), `subscription_line` (nullable FK), `product` (FK), `product_variant` (nullable FK), `description`, `quantity`, `unit_price`, `tax_rule` (FK to `TaxRule`), `tax_amount`, `discount_amount`, `line_total`.
- **Method:** `calculate()` computes exact base price, subtracts line-level discount, applies tax percentage, and quantizes financial decimals to `0.01` precision.

#### `Payment`
- **Fields:** `invoice` (FK), `amount`, `payment_method` (`bank_transfer`, `credit_card`, `cash`, `cheque`, `other`), `payment_date`, `reference` (check or txn number), `note`, `recorded_by` (FK to User).
- **Ordering:** Chronological descending order by date and creation timestamp.

---

## 5. Domain Logic & Services

Located in [`billing/services.py`](file:///c:/Users/adduu/OneDrive/Desktop/susbscrption%20management%20system/-Subscription_Management_System/billing/services.py):

1. **`generate_invoice_for_subscription(subscription, billing_date=None)`**
   - Wrapped in `@transaction.atomic`.
   - Validates that the subscription is `active` and its `current_period_end <= billing_date`.
   - Verifies the idempotency guard.
   - Computes payment due date using `subscription.payment_terms_days`.
   - Clones lines from `SubscriptionLine`, attaches product/variant snapshots, and evaluates line taxes.
   - Runs the discount application engine.
   - Advances subscription period start and end forward by one period interval (`daily`, `weekly`, `monthly`, or `yearly` via `dateutil.relativedelta`).

2. **`apply_discount_to_invoice(invoice)`**
   - Evaluates all active discounts in the system.
   - Filters by eligibility: minimum subtotal, minimum quantity, and target products.
   - Applies the best discount maximizing customer savings.
   - For product-specific discounts, distributes savings proportionally across eligible lines and updates lines with exact rounding preservation.
   - Atomically increments `discount.times_used`.

3. **`record_payment(invoice, amount, method, date, ...)`**
   - Enforces business rules: prevents payments on `draft` or `cancelled` invoices.
   - Saves payment instance, triggering signal reconciliation.

4. **Automated State Machine & Signal Reconciliation ([`billing/signals.py`](file:///c:/Users/adduu/OneDrive/Desktop/susbscrption%20management%20system/-Subscription_Management_System/billing/signals.py))**
   - On `Payment` save or delete, aggregates total paid amount via SQL `Sum("amount")`.
   - Automatically transitions invoice status from `confirmed` to `paid` if settled.
   - Gracefully reverts from `paid` back to `confirmed` if a payment record is voided or deleted.

---

## 6. REST API Endpoints Reference

Base route: `/api/billing/` (configured in [`billing/urls.py`](file:///c:/Users/adduu/OneDrive/Desktop/susbscrption%20management%20system/-Subscription_Management_System/billing/urls.py))

| Endpoint | HTTP Method | Allowed Roles | Description & Functionality |
| :--- | :--- | :--- | :--- |
| `invoices/` | `GET` | Staff, Admin | Paginated list of invoices with filters (`status`, `customer`, `issue_date_from`, `due_date_to`, `overdue=true`). |
| `invoices/` | `POST` | Staff, Admin | Manually create an invoice header. |
| `invoices/generate/` | `POST` | Staff, Admin | Trigger batch billing day generation across due subscriptions. Accepts optional `{"billing_date": "YYYY-MM-DD"}`. |
| `invoices/<id>/` | `GET` | Staff, Admin, Owner | Detailed invoice view including all nested invoice lines. |
| `invoices/<id>/confirm/` | `POST` | Staff, Admin | Transition invoice state from `draft` to `confirmed`. |
| `invoices/<id>/cancel/` | `POST` | Staff, Admin | Cancel a `draft` or `confirmed` invoice. |
| `payments/` | `GET` | Staff, Admin | List payments with filters by date, invoice, or method. |
| `payments/` | `POST` | Staff, Admin | Record payment with audit tracking (`recorded_by`). |
| `payments/<id>/` | `GET` | Staff, Admin | Retrieve individual payment details. |
| `discounts/` | `GET` | Staff, Admin | List configured discount rules. |
| `discounts/` | `POST` | **Admin Only** | Create a new discount rule. |
| `discounts/<id>/` | `GET`, `PUT`, `DELETE`| **Admin Only** (writes) | View, update, or remove discount rules. |
| `dashboard/summary/` | `GET` | Staff, Admin | Real-time aggregate KPI metrics (active subscriptions, total revenue, outstanding receivables, overdue count, current month metrics). |
| `my/invoices/` | `GET` | Customer (Self) | Customer portal: strictly queries invoices where `customer = request.user`. |
| `my/payments/` | `GET` | Customer (Self) | Customer portal: strictly queries payments made on customer's invoices. |

---

## 7. Testing & Quality Assurance

Comprehensive unit test suites have been prepared under [`billing/tests/`](file:///c:/Users/adduu/OneDrive/Desktop/susbscrption%20management%20system/-Subscription_Management_System/billing/tests/):

1. **`test_models.py`**:
   - `Discount.is_valid_today`: Verifies time windows, active flags, and usage ceilings.
   - `InvoiceLine.calculate`: Validates mathematical precision for multi-quantity pricing, tax addition, and discount deductions.
   - `Invoice` properties: Tests `amount_due` calculation and overdue detection against current dates and payment states.

2. **`test_services.py`**:
   - Tests `record_payment` guard conditions (blocks payments on draft or cancelled invoices).
   - Verifies callable interfaces and signature integrity for `bulk_generate_invoices` and `recalculate_invoice_totals`.

3. **`test_views.py`**:
   - Security auditing: Asserts that unauthenticated requests to protected endpoints immediately return HTTP 401/403.

---

## 8. Git Status & Next Steps

All 18 new files and the updated `README.md` are staged and ready in the repository:
```bash
git status
# Changes to be committed:
#   modified:   README.md
#   new file:   billing/...
#   new file:   PROJECT_REPORT.md
```

### Steps to Complete on the Shared Repository
1. Commit the staged billing module files:
   ```bash
   git commit -m "feat(billing): implement invoices, payments, discounts, and reporting module"
   git push origin main
   ```
2. When the common backend setup (User model, `subscriptions`, `products`) is pushed by your teammate:
   - Add `"billing"` and `"django_filters"` to `INSTALLED_APPS` in `settings.py`.
   - Add `path("api/billing/", include("billing.urls"))` in root `urls.py`.
   - Run migrations: `python manage.py makemigrations billing && python manage.py migrate`.
   - Run the test suite: `python manage.py test billing`.

