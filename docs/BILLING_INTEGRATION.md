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
| `POST /invoices/generate/` | Staff/admin | Generate due invoices; optional `billing_date`. |
| `GET, POST /payments/` | Staff/admin | List or record a payment. Payments are partial; overpayment is rejected. |
| `GET /payments/{id}/` | Staff/admin | Payment detail. |
| `GET /discounts/` | Staff/admin | List discount rules. |
| `POST /discounts/` | Application admin | Create a discount. |
| `GET /discounts/{id}/` | Staff/admin | Discount detail. |
| `PUT, PATCH, DELETE /discounts/{id}/` | Application admin | Change or remove a discount. |
| `GET /dashboard/summary/` | Staff/admin | Global billing metrics. |
| `GET /my/invoices/`, `GET /my/payments/` | Customer | Customer's own records. |

Sreehari can consume `GET /api/billing/dashboard/summary/` for staff finance
metrics and the two `/my/` lists for customer billing history after the models
and settings integration are complete. The summary currently performs multiple
database queries; its response time has not been measured. `active_subscriptions`
is currently a global count. The response separates billed revenue, collected
payments and outstanding receivables, and excludes cancelled invoices where
appropriate.

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

`generate_invoices` is a management command, not a configured scheduler.
Invoice PDF/print output and invoice email delivery are not implemented. No
customer billing UI is included here. Payment refunds/voids are not modeled;
cancellation is rejected once a payment has been recorded.
