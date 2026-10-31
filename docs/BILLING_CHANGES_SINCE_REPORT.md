> Historical report retained from published billing commit `3a7660b`.
> Its statements about publication and missing production models are superseded
> by [BILLING_INTEGRATION.md](BILLING_INTEGRATION.md) and the current verification
> record. The branch was fetched and integrated locally; no new push was made.

# Billing changes since the original report

**Baseline report commit:** `3060e80` (31 October 2026, 12:43 IST)
**Current local branch:** `feat/billing` with uncommitted follow-up changes
**Scope:** Changes made after the original billing report was committed.

## GitHub status

No billing branch, billing commit, or billing pull request exists on GitHub.
The remote currently has only `main`, `feat/auth-roles`, and
`feature/authentication`. The attempted push of `feat/billing` did not succeed:
the local Git client has no write credentials, and the connected GitHub
integration returned HTTP 403 for repository writes.

GitHub did merge `feat/auth-roles` into `main` as commit `be770bb`. That
upstream change was fetched and merged into the local billing branch in local
merge commit `3670524`; it has not been published as part of `feat/billing`.

## Local commits after the report

| Commit | Time (IST) | Change |
|---|---:|---|
| `3670524` | 12:59 | Merged the fetched `origin/main`, including the merged authentication foundation. |
| `37c3253` | 13:06 | Hardened billing behavior, added concurrency/permission tests, and replaced the earlier optimistic report text with an evidence-based integration record. |
| `d2279c2` | 13:10 | Recorded the GitHub publication failure in the project report. |

## Code changes

### Billing correctness and concurrency

- Invoice-number retries now run inside a database savepoint. A unique-number
  collision no longer leaves the surrounding invoice-generation transaction
  unusable.
- Discount application rechecks eligibility and calculated savings after it
  locks the discount row. This prevents a stale candidate from consuming a
  discount after its validity or usage state changes.
- `Payment.save()` now validates direct model writes as well as API/service
  writes: it rejects non-positive payments, payments on draft/cancelled
  invoices, overpayments, and moving an existing payment to a different
  invoice. It locks the invoice during validation.
- Payment create, update, and delete now reconcile `Invoice.amount_paid` and
  invoice status through signals. Reconciliation locks the invoice row while
  summing its payments.

### Configuration and integration safety

- Billing routes are now included only when `billing` is present in
  `INSTALLED_APPS`. This restores a passing default Django system check while
  the real `products` and `subscriptions` apps are absent.
- Added [BILLING_INTEGRATION.md](BILLING_INTEGRATION.md), documenting the
  actual required model fields, TaxRule ownership question, API surface,
  dashboard semantics, and the steps needed before a production billing
  migration can be generated.

### Follow-up API and delivery work

- Customer-only `/my/invoices/` and `/my/payments/` endpoints now reject staff
  and admin roles. The existing ownership mixin remains responsible for
  customer query scoping.
- Manual invoice creation now rejects a customer ID that does not belong to the
  selected subscription and only permits a new manual invoice as a draft.
- Added staff/admin invoice email sending for confirmed or paid invoices and a
  print-ready HTML endpoint for an invoice owner or staff/admin. Email delivery
  has no delivery audit, retry mechanism, sent timestamp, or PDF attachment.
- Expanded `BILLING_INTEGRATION.md` with Srihari's exact dashboard and
  customer-billing endpoint contracts, filters, response shape, and metric
  definitions. The dashboard remains the single source for these aggregates.

### Test coverage added

- Added PostgreSQL threaded concurrency tests for duplicate invoice generation,
  concurrent final-discount use, and competing payments that would otherwise
  overdraw an invoice.
- Added tests for invoice-number collision recovery, locked discount
  revalidation, direct payment overpayment rejection, and payment delete
  reconciliation.
- Expanded API permission tests for customer A/customer B payment isolation,
  customer writes using another customer's related IDs, staff-only dashboard
  access, application-role separation from Django's `is_staff`, admin-only
  discount edits, invalid related IDs, customer-only portal access, manual
  invoice ownership validation, invoice email sending, and print access.

## Documentation changes

- `PROJECT_REPORT.md` was rewritten to distinguish fixture-based verification
  from real integration, list checks that actually ran, and state the missing
  production migrations, product/subscription models, scheduler, PDFs, invoice
  delivery, refunds/voids, and UI work.
- `README.md` now states that billing is not enabled in the shared default
  settings and links to the integration contract.

## Verification after the changes

- Isolated PostgreSQL test suite: **81 tests passed**.
- Focused billing suite: **29 tests passed**.
- Default `manage.py check`: passed.
- Test-settings `makemigrations --check --dry-run`: no changes detected.
- Dependency check: no broken requirements.

These checks use the test fixture products/subscriptions models. They do not
prove compatibility with Haridev's production models and do not constitute a
production migration check.

## Local-only working-tree edits

Six test-fixture files are staged and contain only one added blank line at EOF.
They are outside the billing work and will not be included in the billing
commit:

- `billing/tests/fixtures/products/__init__.py`
- `billing/tests/fixtures/products/apps.py`
- `billing/tests/fixtures/products/models.py`
- `billing/tests/fixtures/subscriptions/__init__.py`
- `billing/tests/fixtures/subscriptions/apps.py`
- `billing/tests/fixtures/subscriptions/models.py`
