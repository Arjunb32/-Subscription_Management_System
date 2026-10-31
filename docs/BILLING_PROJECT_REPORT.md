# Billing implementation and verification report

**Owner:** Adwaith
**Branch:** feat/billing
**Target:** main
**Status:** Draft integration; production model dependencies and migration are missing
**Updated:** 31 October 2026

## Current integration state

The branch has been updated with the fetched origin/main, which contains Arjun's
merged authentication foundation. Billing references the shared
settings.AUTH_USER_MODEL, user.role and existing session/CSRF authentication.
Customer invoice and payment lists use the documented customer-scoping mixin;
application roles remain independent of Django admin flags.

The repository does not contain production products or subscriptions apps.
Only test fixture models exist under billing/tests/fixtures. Billing is absent
from default INSTALLED_APPS; the billing URL is conditional so the default shared
foundation can start without importing uninstalled billing models. Under
config.test_settings, the fixture apps and billing are enabled for API tests.
No production billing migration has been created. Generating a migration or
claiming end-to-end integration before Haridev's actual models land would invent
a schema contract.

Billing currently accesses Subscription.customer, plan.billing_interval,
status, current_period_start/current_period_end, expiry_date,
payment_terms_days, and the reverse lines relation. Each line must provide
product, optional product_variant, quantity, unit_price and optional tax_rule.
TaxRule ownership is expected to be subscriptions/catalog based on the draft
contract; Haridev must confirm ownership and fields. See
docs/BILLING_INTEGRATION.md for every model dependency and exact integration
steps.

## Checks actually run in this review

- Fetched origin and merged origin/main into feat/billing.
- Isolated PostgreSQL, using config.test_settings and the dedicated test cluster.
- Initial focused billing run before review fixes: 19 passed.
- After fixes: 29 billing tests passed on the isolated PostgreSQL database,
  including three threaded concurrency cases (duplicate invoice generation,
  final discount use, and competing payments), payment save/delete
  reconciliation, discount revalidation and invoice-number collision retry.
- Full isolated PostgreSQL suite: 81 tests passed, including the 52 shared
  accounts/auth regression tests.
- Default manage.py check: passed after making the billing URL mount
  conditional on billing being installed.
- Test-settings makemigrations --check --dry-run: no changes detected. Billing
  has no real migrations yet, so this is not evidence of production migration
  drift being checked.
- git diff --check was run; only local newline-only edits in six fixture files
  remain outside the feature changes and are intentionally unstaged.
- No production migration drift check or subscription-to-dashboard integration
  against real models is possible until those models and migration files exist.
- The working database was not migrated, reset or otherwise modified.
- Commit 37c3253 is present on the local feat/billing branch. Publication is
  blocked: the Git CLI has no write credentials (push reports it cannot prompt
  for a password), and the connected GitHub app rejected repository writes
  with HTTP 403. The remote feat/billing branch and PR do not exist yet.

## Implemented billing behavior and limits

The code includes period-idempotent invoice generation, calendar interval
arithmetic, catch-up for up to 36 periods per invocation, subscription status
checks, invoice line price/tax snapshots, discount date/eligibility/usage checks,
partial payments, overpayment rejection, invoice cancellation guards and a
staff finance summary. Database row locks protect subscription generation,
discount usage and payment recording. Invoice numbers have a unique constraint;
the retry path now uses savepoints so a number collision does not poison the
transaction.

These behaviors have fixture-based tests. Passing tests against fixtures do not
prove compatibility with Haridev's production models. The dashboard is global
for staff/admin, executes multiple queries, and has no measured latency. Its
billed revenue, collected payments and outstanding balance are distinct; canceled
invoices are excluded where appropriate.

The generate_invoices management command exists, but no scheduler is configured.
PDF/print output, invoice sending, SMTP delivery for invoices, refunds/voids and
customer billing UI are not implemented. Cancellation is rejected after money
has been recorded; refund/void handling needs a separately agreed payment
lifecycle.

## Remaining integration steps

1. Haridev supplies and pushes the real products/subscriptions models and
   migrations, and confirms the contract including TaxRule ownership, lifecycle
   values, expiry behavior and variant/tax pricing.
2. Add products, subscriptions and billing to INSTALLED_APPS together, and
   verify the mounted URLs against the actual app registry.
3. Generate billing migrations with dependencies on the real model migrations
   and accounts.User migration. Inspect migration operations and each existing
   database's state before applying; do not reset a working database.
4. Run billing tests plus the shared authentication regression suite against
   isolated PostgreSQL, check migration drift, and test subscription → invoice
   → payment → dashboard with the real models.
5. Keep this PR draft until those integration checks pass; then review and merge
   through main.
