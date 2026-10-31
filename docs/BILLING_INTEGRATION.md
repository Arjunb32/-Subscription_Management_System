# Billing integration contract

## Status

The billing implementation lives on `feat/billing`. The latest fetched
`origin/main` contains Arjun's merged authentication foundation, which this
branch now includes. The repository has no production `products` or
`subscriptions` app, so billing is not in default `INSTALLED_APPS` and has no
production migration. Test-only fixture apps must not be deployed or used to
generate one.

The current billing branch expects the contracts below. The project report's
earlier text called these agreed fields, but the actual Haridev models were not
available to verify. Haridev should compare every item and confirm the final
contract before integration.

## Required models and fields

| Model | Billing access and expected shape |
|---|---|
| `products.Product` | Model with a useful `__str__`; `InvoiceLine.product` FK uses `PROTECT`; product IDs are exposed in billing lines and product-scoped discounts. `sales_price` is not read by billing (subscription line `unit_price` is the billed snapshot). |
| `products.ProductVariant` | Model with a useful `__str__`; nullable variant FK on subscription and invoice lines. |
| `subscriptions.Plan` | `billing_interval` with `daily`, `weekly`, `monthly`, or `yearly`. |
| `subscriptions.Subscription` | `customer` FK to `settings.AUTH_USER_MODEL`, `plan` FK, `status`, `current_period_start` and `current_period_end` (`DateField`s), optional `expiry_date`, optional `payment_terms_days`, and reverse `lines` relation. Billing only processes status `active`; it skips `paused` and `closed`. Expiry currently closes when the period reaches/passes the expiry date. |
| `subscriptions.SubscriptionLine` | FK to subscription with `related_name="lines"`; product FK; nullable `product_variant`; `quantity`, `unit_price` as decimal values; nullable `tax_rule`. |
| `subscriptions.TaxRule` | Expected owner: subscriptions/catalog feature, pending Haridev confirmation. Billing reads `rate` as a percentage and `__str__`; a nullable FK is snapshotted to the invoice line. |

The exact migration dependencies must name the real products and subscriptions
migrations and the accounts user migration. Do not invent those names in a
billing migration. `TaxRule` ownership and whether `unit_price` already
includes variant pricing/tax are unresolved integration decisions.

## Authentication and ownership

Billing uses `settings.AUTH_USER_MODEL`, `user.role`, DRF's existing
`SessionAuthentication`, and the ownership helpers from
`accounts.permissions`. Application roles (`admin`, `staff`, `customer`) are
distinct from Django's `is_staff` and `is_superuser`. Customer invoice and
payment endpoints scope querysets by owner; staff/admin billing lists and
financial summary are global. The dashboard summary is not a customer-scoped
endpoint. Writes to discount rules require the application admin role.

## API code currently present

The paths below are defined under `/api/billing/` and are mounted only when
`billing` is installed. The default shared configuration does not mount them
until the dependent apps are integrated.

| Method and path | Access | Purpose |
|---|---|---|
| `GET /invoices/` | Staff/admin | List and filter invoices. |
| `POST /invoices/` | Staff/admin | Create an invoice record. |
| `GET /invoices/{id}/` | Owner, staff/admin | Invoice details and lines. |
| `POST /invoices/{id}/confirm/` | Staff/admin | Confirm a draft invoice. |
| `POST /invoices/{id}/cancel/` | Staff/admin | Cancel an unpaid draft/confirmed invoice. |
| `POST /invoices/{id}/send/` | Staff/admin | Send a confirmed or paid invoice to the customer email. |
| `GET /invoices/{id}/print/` | Owner, staff/admin | Print-ready HTML invoice. |
| `POST /invoices/generate/` | Staff/admin | Generate due invoices; optional `billing_date`. |
| `GET, POST /payments/` | Staff/admin | List or record a payment. Payments are partial; overpayment is rejected. |
| `GET /payments/{id}/` | Staff/admin | Payment detail. |
| `GET /discounts/` | Staff/admin | List discount rules. |
| `POST /discounts/` | Application admin | Create a discount. |
| `GET /discounts/{id}/` | Staff/admin | Discount detail. |
| `PUT, PATCH, DELETE /discounts/{id}/` | Application admin | Change or remove a discount. |
| `GET /dashboard/summary/` | Staff/admin | Global billing metrics. |
| `GET /my/invoices/`, `GET /my/payments/` | Customer | Customer's own records. |

All API views use DRF session authentication. Browser writes require the normal
CSRF token. The `/my/` paths accept only an active application customer role;
staff and admins use the global staff paths. Invoice detail and print access
are scoped to the owning customer for customers and are global for staff/admin.

## Dashboard and customer-billing contract for Srihari

Srihari should use these endpoints after the real models, migrations and app
settings are integrated. The dashboard endpoint deliberately owns its metric
calculations; do not reproduce these aggregates in a screen or another API.

| Endpoint | Filters | Response/use |
|---|---|---|
| `GET /api/billing/dashboard/summary/` | None | Global staff/admin finance metrics. |
| `GET /api/billing/invoices/` | `status`, `customer`, `issue_date_from` (inclusive), `due_date_to` (inclusive), `overdue=true` or `1` | Global staff/admin invoice table. |
| `GET /api/billing/payments/` | `invoice`, `payment_method`, `date_from` (inclusive), `date_to` (inclusive) | Global staff/admin payment table. |
| `GET /api/billing/my/invoices/` | None | Current customer's invoice history only. |
| `GET /api/billing/my/payments/` | None | Current customer's payment history only. |
| `GET /api/billing/invoices/{id}/` | Path ID | Itemized invoice detail for its owner or staff/admin. |
| `GET /api/billing/invoices/{id}/print/` | Path ID | HTML suitable for the browser print dialog. |

Example dashboard response:

```json
{
  "active_subscriptions": 12,
  "billed_revenue": "330.00",
  "payments_collected": "50.00",
  "total_outstanding": "280.00",
  "overdue_invoices": 2,
  "invoices_by_status": {"draft": 1, "confirmed": 3, "paid": 4, "cancelled": 1},
  "revenue_this_month": "200.00",
  "payments_this_month": "50.00"
}
```

Metric definitions:

- `active_subscriptions`: count of subscriptions whose status is `active`.
- `billed_revenue`: sum of invoice `total` where status is `confirmed` or
  `paid`.
- `payments_collected`: sum of payments on invoices that are not cancelled.
- `total_outstanding`: sum of `total - amount_paid` for confirmed invoices
  with a remaining balance.
- `overdue_invoices`: count of confirmed invoices with a remaining balance and
  `due_date` before today.
- `invoices_by_status`: count of every invoice grouped by its current status.
- `revenue_this_month`: billed revenue for invoices issued on or after the
  first day of the current month.
- `payments_this_month`: collected payments dated on or after the first day of
  the current month, excluding payments on cancelled invoices.

The summary currently performs multiple database queries and has not received
a response-time measurement. `active_subscriptions` is global.

## Integration steps

1. Haridev provides the real products, plan, subscription, subscription-line
   and tax-rule models plus migrations. Confirm the contract above, including
   TaxRule ownership, lifecycle values, expiry semantics, currency precision
   and variant price inclusion.
2. Merge/update this branch from `main` after the shared dependencies land.
3. Add `products`, `subscriptions` and `billing` to `INSTALLED_APPS` together;
   the billing URL include in `config/urls.py` is conditional on billing being
   installed.
4. Run `makemigrations billing`; inspect the generated dependency graph and
   migration operations. Check existing database state and `migrate --plan`
   before applying anything. Do not reset a working database.
5. Run the isolated PostgreSQL billing suite, the accounts/auth regression
   suite, migration drift checks and an end-to-end subscription → invoice →
   payment → dashboard flow against the real models.
6. Only then remove draft status from the PR and merge through review.

## Remaining product/infrastructure work

`generate_invoices` is a management command, not a configured scheduler. A
deployment must configure and monitor an external scheduler before it can claim
automatic generation.

`POST /invoices/{id}/send/` sends a plain-text email through Django's configured
email backend for confirmed and paid invoices. It does not record delivery,
retries, or a sent timestamp, and it does not attach a PDF. The print route
renders print-ready HTML rather than a PDF. The billing management screens need
to surface send failures and invoke the browser print dialog. Payment
refunds/voids are not modeled; cancellation is rejected once a payment has
been recorded.
