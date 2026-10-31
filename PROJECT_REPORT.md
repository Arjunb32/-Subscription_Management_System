# Billing, Invoices & Payments Subsystem — Implementation & Verification Report

**Author:** Adwaith  
**Subsystem:** Billing, Invoices, Discounts & Payments (`billing` app)  
**Project:** Subscription Management System (Brightloop Software Case Study)  
**Branch:** `feat/billing`  
**Target:** `main`  
**Date:** October 31, 2026  
**Status:** **DRAFT PR / Ready for Review** (Pending upstream merge of `feat/auth-roles` and delivery of Haridev's `subscriptions`/`products` models)

---

## 1. Executive Summary & Status

This document provides a verified, evidence-backed report on the billing subsystem implementation for the shared Subscription Management System.

All core billing requirements—automated recurring invoice generation, dynamic tax/discount calculations, concurrency-safe row locking, idempotency guards, payment reconciliation state machine, customer portal endpoints, and finance dashboard metrics—have been fully implemented and verified against an isolated PostgreSQL 18 instance.

### Integration Status & Upstream Dependencies
- **Arjun (`feat/auth-roles`):** Shared Django/DRF foundation, custom `accounts.User` model, role-based access control (`admin`, `staff`, `customer`), session/CSRF authentication, and customer scoping mixins. Our branch has cleanly integrated these helpers.
- **Haridev (`products` & `subscriptions`):** Product catalog, variants, plans, and subscription lifecycle models. These models **have not yet been pushed to the shared repository**. Our subsystem connects to these models via string references and dynamic runtime resolution (`apps.get_model()`). For verification, test fixtures matching the agreed field contract were used.
- **Sreehari (Reporting & Dashboard Frontend):** The backend financial summary endpoint (`/api/billing/dashboard/summary/`) is fully implemented, verified, and documented for direct consumption by the frontend portal.

---

## 2. Verified Test Execution & Evidence

Testing was executed against an isolated PostgreSQL 18 instance running locally on port 7130 (`test_subscription_management`). The working database and production ports were untouched.

### Test Results

```
Ran 71 tests in 10.077s
OK
System check identified no issues (0 silenced).
```

### Breakdown of Executed Test Suites:
1. **Accounts & Authentication Regression Suite (52 tests - Arjun):**
   - User creation, password validation, role enforcement, attempt rate-limiting, session handling, CSRF protection, and reset tokens.
   - Result: **52/52 passed** (0 regressions introduced).

2. **Billing Domain & Model Suite (19 tests - Adwaith):**
   - `test_discount_validity_rules`: Verifies start/end validity dates, active flags, and max usage ceilings.
   - `test_invoice_number_generation_and_uniqueness`: Verifies sequential `INV-YYYYMM-XXXX` assignment under concurrency.
   - `test_period_idempotency_constraint`: Database-level composite `UniqueConstraint(subscription, period_start, period_end)` prevents duplicate billing.
   - `test_invoice_line_calculate`: Exact financial calculations with 18% tax and discount deductions.
   - `test_invoice_amount_due_and_overdue_flags`: Proper calculation of remaining balance and overdue status based on due dates.
   - `test_calendar_boundary_calculations`: Month-end clamping (Jan 31 $\rightarrow$ Feb 28), leap year calculations (Jan 31 2028 $\rightarrow$ Feb 29 2028, Feb 29 2028 $\rightarrow$ Feb 28 2029), weekly, and daily intervals using pure Python without external dependencies.
   - `test_generate_invoice_for_active_subscription`: Full invoice generation cycle, snapshotting prices and advancing subscription periods.
   - `test_idempotency_prevents_duplicate_billing`: Verifies retry and re-run calls return `None` and do not generate duplicate invoices.
   - `test_subscription_lifecycle_respect`: Paused, closed, and expired subscriptions are skipped and not billed. Reaching `expiry_date` transitions status to `closed`.
   - `test_multi_period_catch_up`: Multi-period catch-up generation accurately generates all missed periods sequentially when the system was offline or missed billing runs.
   - `test_price_and_tax_preservation_after_catalog_changes`: Altering catalog `Product.sales_price` or `TaxRule.rate` after issuance leaves historical invoice lines unchanged.
   - `test_discount_engine_and_usage_limit`: Verifies greedy highest-saving discount selection and strict enforcement of `max_uses`.
   - `test_payment_recording_partial_and_full_reconciliation`: Rejects non-positive amounts, rejects payments on draft/cancelled invoices, rejects overpayments exceeding balance, handles partial payments, and transitions status to `paid` upon settlement.
   - `test_cancellation_safety_with_payments`: Strictly prohibits cancelling invoices where money has already been received.
   - `test_anonymous_requests_rejected`: Unauthenticated requests to protected billing routes receive HTTP 403 under `SessionAuthentication`.
   - `test_customer_isolation_on_customer_portal`: Customer A can only query Customer A's invoices/payments via `/my/invoices/` and cannot inspect Customer B's records.
   - `test_staff_can_view_all_invoices`: Staff users have read access across all company invoices.
   - `test_admin_only_discount_mutations`: Staff cannot create or mutate discount rules (HTTP 403); only Application Admins can create discounts (HTTP 201).
   - `test_dashboard_summary_metrics`: Verifies accurate calculation of `billed_revenue`, `payments_collected`, `total_outstanding`, and `overdue_invoices`, with explicit exclusion of cancelled invoices.

---

## 3. Business Logic & Correctness Guarantees

### 3.1 Concurrency & Idempotency
- **Invoice Generation:** Wrapped in `@transaction.atomic` using `select_for_update()` on the `Subscription` record. If two billing jobs run simultaneously, only one obtains the lock; the second detects the updated period or existing invoice and returns `None`.
- **Database Unique Constraint:** `models.UniqueConstraint(fields=["subscription", "period_start", "period_end"])` enforces period idempotency at the database engine level.
- **Discount Usage Locks:** `select_for_update()` is acquired on `Discount` during application to guarantee that concurrent invoice generation cannot over-allocate a discount with a limited `max_uses`.
- **Rounding Drift Prevention:** When product-scoped discounts are distributed across lines, fractional rounding remains strictly balanced by allocating residual cents to the final line.

### 3.2 Payments & Reconciliation
- **Overpayment Guard:** `record_payment` locks the parent invoice, computes `remaining_due = total - amount_paid`, and rejects amounts greater than `remaining_due`.
- **Invalid State Guards:** Payments on `draft` or `cancelled` invoices are rejected with descriptive validation errors.
- **Cancellation Safety:** Invoices with `amount_paid > 0` cannot be cancelled. Any attempt raises a validation error requiring voiding or refunding payments first.
- **Automatic State Machine:** When `amount_paid >= total`, status transitions to `paid`. If a payment record is voided or deleted, `post_delete` signals automatically revert status to `confirmed`.

### 3.3 Zero External Package Additions
- To avoid dependency conflicts with the verified shared environment, interval arithmetic is implemented using standard Python `calendar` and `datetime.timedelta`.
- Queryset filtering is implemented directly inside DRF generic views, removing any requirement for `django-filter` or `python-dateutil`.

---

## 4. API Endpoints Reference for Teammates

All routes are mounted at `/api/billing/` (configured in [`config/urls.py`](file:///c:/Users/adduu/OneDrive/Desktop/susbscrption%20management%20system/-Subscription_Management_System/config/urls.py)).

| Method | Path | Allowed Roles | Purpose |
|---|---|---|---|
| `GET` | `/api/billing/invoices/` | Staff, Admin | List/filter all invoices (`status`, `customer`, `issue_date_from`, `due_date_to`, `overdue`). |
| `POST` | `/api/billing/invoices/` | Staff, Admin | Manually draft an invoice header. |
| `POST` | `/api/billing/invoices/generate/` | Staff, Admin | Trigger batch billing run. Payload: `{"billing_date": "YYYY-MM-DD"}` (optional). |
| `GET` | `/api/billing/invoices/{id}/` | Staff, Admin, Owner | Detailed invoice view with itemized lines. |
| `POST` | `/api/billing/invoices/{id}/confirm/` | Staff, Admin | Transition invoice from `draft` to `confirmed`. |
| `POST` | `/api/billing/invoices/{id}/cancel/` | Staff, Admin | Cancel invoice (blocked if payments exist). |
| `GET` | `/api/billing/payments/` | Staff, Admin | List/filter payments (`invoice`, `payment_method`, `date_from`, `date_to`). |
| `POST` | `/api/billing/payments/` | Staff, Admin | Record payment with audit tracking (`recorded_by`). |
| `GET` | `/api/billing/payments/{id}/` | Staff, Admin | View payment details. |
| `GET` | `/api/billing/discounts/` | Staff, Admin | List discount rules. |
| `POST` | `/api/billing/discounts/` | **Admin Only** | Create discount rule (`value`, `min_purchase`, `max_uses`, `applies_to`). |
| `GET/PUT/DELETE`| `/api/billing/discounts/{id}/`| **Admin Only** (writes) | Manage specific discount rule. |
| `GET` | `/api/billing/dashboard/summary/` | Staff, Admin | Single-query financial KPIs (see schema below). |
| `GET` | `/api/billing/my/invoices/` | Customer (Self) | Customer portal: invoices scoped to `request.user`. |
| `GET` | `/api/billing/my/payments/` | Customer (Self) | Customer portal: payments scoped to customer's invoices. |

### Dashboard Summary Schema (For Sreehari)
```json
{
  "active_subscriptions": 142,
  "billed_revenue": "28500.00",
  "payments_collected": "24100.00",
  "total_outstanding": "4400.00",
  "overdue_invoices": 3,
  "invoices_by_status": {
    "draft": 4,
    "confirmed": 12,
    "paid": 126,
    "cancelled": 2
  },
  "revenue_this_month": "6800.00",
  "payments_this_month": "5900.00"
}
```

---

## 5. Model Dependency Contract (For Haridev)

The `billing` module expects Haridev's models to satisfy the following field contracts:

1. **`subscriptions.Subscription`**:
   - `customer`: `ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)`
   - `plan`: `ForeignKey("subscriptions.Plan", on_delete=models.PROTECT)`
   - `status`: `CharField` with choices including `'draft'`, `'quotation'`, `'confirmed'`, `'active'`, `'paused'`, `'closed'`
   - `start_date`: `DateField`
   - `current_period_start`: `DateField`
   - `current_period_end`: `DateField`
   - `expiry_date`: `DateField(null=True, blank=True)`
   - `payment_terms_days`: `PositiveIntegerField(default=30)`
   - `lines`: Reverse relation for `SubscriptionLine`

2. **`subscriptions.SubscriptionLine`**:
   - `subscription`: `ForeignKey(Subscription, related_name='lines')`
   - `product`: `ForeignKey("products.Product", on_delete=models.PROTECT)`
   - `product_variant`: `ForeignKey("products.ProductVariant", null=True, blank=True)`
   - `quantity`: `DecimalField`
   - `unit_price`: `DecimalField`
   - `tax_rule`: `ForeignKey("subscriptions.TaxRule", null=True, blank=True)`

3. **`subscriptions.TaxRule`**:
   - `name`: `CharField`
   - `rate`: `DecimalField(max_digits=5, decimal_places=2)` (e.g. `18.00` = 18%)
   - `is_active`: `BooleanField(default=True)`

4. **`subscriptions.Plan`**:
   - `billing_interval`: `CharField` with choices `'daily'`, `'weekly'`, `'monthly'`, `'yearly'`

5. **`products.Product` & `ProductVariant`**:
   - Standard Django models with string representations.

---

## 6. Honest Audit of Remaining Work & Non-Goals

1. **Invoice PDF / Print Rendering & Email Delivery:**
   - The backend provides complete JSON line item details and state endpoints for printing/confirmation.
   - Generating binary PDF files (e.g., using Weasyprint or ReportLab) and triggering SMTP email dispatch to customers on billing day are frontend/task integrations that remain to be connected once email/SMTP configuration is active.

2. **Cron / Job Scheduler Daemon:**
   - The CLI command `python manage.py generate_invoices [--date YYYY-MM-DD]` is implemented and verified.
   - Setting up a background cron job (or Celery beat / Windows Task Scheduler) to invoke this daily at midnight is an infrastructure deployment step, not a code change.

3. **Production Migrations:**
   - Production migrations for `billing` should be generated (`python manage.py makemigrations billing`) once Haridev's actual models are present in the shared repository, ensuring foreign key dependencies are committed with accurate migration references.

---

## 7. Next Steps for Integration

1. **For Arjun:** Review and merge PR #1 (`feat/auth-roles`) into `main`.
2. **For Haridev:** Commit and push the `products` and `subscriptions` models following the contract outlined in Section 5.
3. **For Adwaith:**
   - Rebase `feat/billing` onto `main` following upstream merges.
   - Run `python manage.py makemigrations billing` to create the final production migration.
   - Remove Draft status from the billing PR and merge into `main`.
