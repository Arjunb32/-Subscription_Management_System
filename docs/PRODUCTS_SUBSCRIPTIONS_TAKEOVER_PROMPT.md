# Implementation prompt: Arjun's products and subscriptions takeover

Copy the prompt below into an AI coding chat with this repository open. This is an implementation assignment, not evidence that implementation or integration has passed.

---

Implement the complete products, plans, quotations and subscriptions section of our existing Subscription Management System, then integrate it with the team's existing billing and dashboard work. Inspect the repository first, preserve existing work, and carry the implementation through meaningful verification. Do not stop at a plan, backend skeleton, mock screens or a list of instructions for me to implement.

## Context and ownership

I am Arjun. Haridev cannot work because he has no electricity or internet access. I am taking over his entire section now; do not wait for his branch, confirmation or contribution.

- Arjun: existing authentication, roles, shared Django setup and integration, PLUS products, variants, recurring plans, quotation templates, subscriptions, lifecycle policies, related APIs, migrations and management screens.
- Adwaith: existing billing, invoices, discounts, payments and financial summary calculations.
- Sreehari: existing dashboard, customer portal and presentation of real data.

Complete my expanded section and the changes necessary to integrate it. Reuse Adwaith's and Sreehari's implementations; do not replace them with separate applications or duplicate financial logic. Other teammates remain owners of their sections. Identify remaining work for them explicitly.

Repository: https://github.com/Arjunb32/-Subscription_Management_System

Local repository: C:\Users\arjun\OneDrive\Attachments\Desktop\-Subscription_Management_System

Existing stack: Python, Django, Django REST Framework, PostgreSQL, Django templates, CSS and JavaScript. Use the existing same-origin session authentication and CSRF client. Do not introduce another frontend framework, authentication system or database.

Latest verified baseline, which you must refresh before relying on it:

- `origin/main`: `be770bb`, merged authentication foundation.
- `origin/feat/auth-roles`: `1115af6`, authentication plus planning/report additions.
- `origin/feat/billing`: `3a7660b`, Adwaith's published billing; draft PR #2.
- `origin/feature/dashboard-portal`: `c272eba`, Sreehari's published dashboard; draft PR #3.
- No production `products` or `subscriptions` apps were published in that review.
- Billing is disabled in default settings and has no production initial migration. Its tests currently use substitute apps labeled `products` and `subscriptions`, with migrations disabled. Passing those tests does not prove real integration.

## 1. Inspect sources and preserve work

Read applicable repository instructions and inspect current branch, working changes, remote branches and commits. Fetch current refs when available. If network access fails, continue useful local implementation from available refs and record the limitation.

Read these sources, using `git show origin/BRANCH:PATH` for files absent from the checkout:

- `README.md`, `HACKATHON_PLAN.md`, `PROJECT_COMPLETION_CHECKLIST.md`.
- `docs/AUTHENTICATION.md`, `docs/VERIFICATION.md`.
- `accounts/models.py`, `accounts/permissions.py`, existing serializers/views and auth tests.
- `accounts/static/accounts/auth-client.js` and the current page templates/styles.
- `config/settings.py`, `config/urls.py`, test settings and `scripts/test_postgres.py`.
- On the billing branch: `docs/BILLING_INTEGRATION.md`, `docs/BILLING_CHANGES_SINCE_REPORT.md`, billing models, services, serializers, views, URLs, tests and fixture apps.
- On the dashboard branch: `dashboard/pages.py`, `dashboard/page_urls.py`, templates, `dashboard/static/dashboard/dashboard.js` and tests.
- The original requirements PDF if it is available. The expectation video was not verified; do not invent requirements from it.

Preserve local changes. The last checkout contained a deleted Word report and an untracked completion checklist; takeover planning documents may also be modified. Do not restore the deletion, discard changes or blindly stage everything. Prefer an isolated worktree/checkout within the permitted workspace when needed.

Work on `codex/products-subscriptions` from reviewed current main, or continue an appropriate existing branch after inspection. Use `codex/integration` for combined verification if the team has not already established an integration branch. Do not commit business code to the old auth branch or merge directly into main. Prepare local commits and a reviewable result; do not push, publish, retarget PRs or change repository settings without an explicit request to do so.

## 2. Establish the real model contract

Implement production Django apps with app labels `products` and `subscriptions`. Billing expects:

| Model | Required compatibility |
|---|---|
| `products.Product` | Useful string representation; stable identity for invoice lines and product-scoped discounts. |
| `products.ProductVariant` | Belongs to a product; useful string representation; nullable references from subscription/invoice lines. |
| `subscriptions.Plan` | `billing_interval` values exactly `daily`, `weekly`, `monthly`, `yearly`. |
| `subscriptions.Subscription` | `customer` FK to `settings.AUTH_USER_MODEL`; `plan` FK; `status`; `current_period_start`, `current_period_end` as dates; optional `expiry_date`; `payment_terms_days`; reverse relation `lines`. |
| `subscriptions.SubscriptionLine` | Subscription FK with `related_name="lines"`; `product`; nullable `product_variant`; decimal `quantity`, `unit_price`; nullable `tax_rule`. |
| `subscriptions.TaxRule` | Percentage `rate` and useful string representation. Keep this model in subscriptions to satisfy existing billing references. |

Inspect actual code, not only this summary. Keep these compatibility names unless a demonstrated issue requires a coordinated change. Create real `AppConfig` classes and committed migrations. Never deploy the test substitutes or generate production migrations against them.

## 3. Complete catalog, plans and quotations

Implement backend validation, APIs and usable management screens for:

- Products: name, type, sales price, cost price and notes; sensible active/archive behavior.
- Product variants: product relationship, descriptive values and additional price. Demonstrate a variant adding 560 to the base price. Reject variants attached to another product.
- Plans: name, price, recurrence, minimum quantity, availability dates and flags controlling pause, early closure, renewal and automatic closure at expiry.
- Admin-managed tax rules with percentage validation. Staff must not gain tax-management access through direct API requests.
- Quotation templates: plan, product/variant lines, quantities, prices, tax selection and validity duration. Create a quotation/subscription from a template and enforce quotation validity at acceptance.

Use exact decimals for money, explicit rounding and non-negative price validation; require positive quantities and enforce the plan minimum. Record the chosen single currency and expose it consistently. Decide and document how plan price relates to product-line prices so it is neither ignored nor charged twice. Subscription `unit_price` must include the selected variant adjustment exactly once and exclude tax for compatibility with billing's tax calculation.

Reject invalid date ranges and unavailable plans on the server. Protect referenced records from destructive deletion; archive where appropriate. Do not expose internal cost prices/notes to customers unless justified by the product requirements.

## 4. Complete subscriptions and lifecycle rules

Implement unique subscription numbers, customer, plan, start/expiry dates, payment terms and item lines with quantity, unit-price snapshots, taxes and amounts. Use transactions and database constraints where appropriate. Validate that the owner is an active customer. Preserve agreed prices when catalog prices change.

Enforce Draft -> Quotation -> Confirmed -> Active -> Closed through explicit server actions. Reject skipped/invalid transitions, empty or invalid activation, expired quotation acceptance and unauthorized field edits. Do not permit arbitrary status changes through a generic update endpoint.

Implement pause/resume, renewal, permitted early closure and expiry behavior. The existing billing engine processes only `status="active"` and skips `paused`/`closed`; preserve that behavior. Represent paused as a documented auxiliary status with a valid return to active, or coordinate any alternate representation with billing and tests.

Document who can invoke each action and how plan flags restrict it. Staff/admin manage subscriptions. Customers see their own subscriptions and can perform only explicitly allowed self-service lifecycle actions; they cannot change ownership, prices, taxes, status or plan policies through arbitrary writes. Use conservative documented defaults for decisions the brief leaves open, and implement them without waiting for the unavailable teammate.

Agree one period/renewal source of truth with billing. Do not add an independent next-billing field that drifts from `current_period_end`. Define and test billing periods, month ends, leap years, expiry boundaries, pause/resume dates, missed periods and renewal dates. Do not bill paused time accidentally, advance dates twice or retroactively alter invoiced periods.

Billing currently generates invoices when `current_period_end <= billing_date`, then advances the period. Respect and document this billing-in-arrears convention unless a requirement needs a coordinated change. Test final-period/expiry behavior and automatic-close flags; avoid inventing advanced proration. Reuse or extract shared recurrence helpers without circular imports.

## 5. Publish a usable API contract and management UI

Provide staff/admin catalog, plan, quotation and subscription list/detail/create/update APIs, explicit lifecycle action endpoints, and a customer-scoped subscription list/detail API. Define the actual URLs in `docs/SUBSCRIPTIONS_API.md`; include example requests/responses, roles, filters, errors, currency, decimal/date formats and pagination.

Prefer URLs consistent with the current `/api/` structure. Provide separate staff/global and `/my/` customer lists rather than relying on a browser-supplied customer ID. Include stable IDs, subscription number, customer display information where authorized, plan name, status, dates, price and allowed actions so Sreehari can connect his screens.

Implement server-side pagination and appropriate filtering/search/order for large lists, with bounded page sizes. Scope querysets before pagination and aggregation. Use `select_related`/`prefetch_related` and appropriate indexes to avoid per-row query growth.

Build functioning Django pages for products/variants, plans, taxes, quotation templates and subscription list/detail/editor/actions. Add navigation to the existing account/dashboard shell. Reuse shared authentication, CSRF and visual conventions. Include validation messages, loading/empty/error states, session-expiry handling and layouts usable on desktop and mobile.

## 6. Integrate the existing billing implementation

Combine changes in dependency order: real products/subscriptions, existing billing, then existing dashboard. Preserve teammate code and resolve shared settings/URL conflicts deliberately. Both published feature branches contain different `PROJECT_REPORT.md` files; preserve them as distinct billing and dashboard reports rather than losing either.

Register real apps and enable billing only once dependencies exist. Generate and inspect production billing migrations using the actual models and dependency names. Keep the existing custom user model and applied auth migrations intact.

Verify real subscriptions produce correct invoice lines, tax, discount, totals and due dates. Confirm, partially pay and fully pay an invoice using existing services/APIs. Confirm balances and statuses reconcile. Test repeated/concurrent generation, missed periods, exhausted/expired discounts, overpayment rejection and cancellation with payments against real models.

Inspect compatibility bugs instead of assuming fixture tests guarantee correctness. For example, zero-day payment terms, finite catch-up limits, expiry flags and concurrent lifecycle changes must agree with the real model behavior. Make focused integration fixes with regression tests; preserve the teammate's billing architecture.

## 7. Connect Sreehari's existing dashboard and portal

Reuse the existing pages. Replace the missing subscription API placeholders with real staff/customer subscription requests and permitted action buttons. Wire actual endpoint URLs into templates and handle server pagination correctly. Do not download all customers' records and filter them in JavaScript.

Verify that subscription pagination stays in live-data mode; existing subscription pagination handlers call the demo renderer and require adjustment. A live response must never turn into sample customer records or sample financial totals after a click or error.

Reuse billing's financial summary API rather than calculating competing totals. Verify billed revenue, collected payments, outstanding and overdue values against known records, including partial payments and cancelled invoices. Make date/customer/status filter semantics explicit; global cards must be clearly labeled unless filtered summaries are implemented consistently. If billing pagination changes, update the corresponding frontend consumers in the same integration change.

Give Sreehari the final API contract and note any remaining presentation work. Do not send messages to teammates automatically.

## 8. Verify migrations, permissions and the complete workflow

Preserve the working PostgreSQL database and `.env`. Use the existing diagnostic and inspect `migrate --plan` before applying compatible additive migrations. Do not drop/reset databases, fake migration history or switch the user model. Never print secrets. Arjun's PostgreSQL port was documented as 7129; use current local configuration rather than hardcoding it.

Provide real-model PostgreSQL test settings that load production products/subscriptions/billing apps and run their migrations. Remove fixture label collisions and migration disabling from that integration path. Isolated fixture tests can remain separately runnable where useful. Use a dedicated test database and role; do not silently substitute SQLite or use the working database for tests.

Run meaningful checks for model/API validation, lifecycle transitions, minimum quantity, variant ownership/pricing, quotation expiry, recurrence boundaries, plan policies, tax permissions, ownership reassignment, cross-customer related IDs and unauthorized actions. Re-run authentication regressions and billing/dashboard suites against the combined app as appropriate. Include CSRF checks and customer A/B isolation for lists, details, writes, invoice/print access and aggregates.

Verify fresh database migration installation as well as the compatible upgrade path. Run Django checks, migration-drift checks and relevant static/JavaScript checks. Record actual commands/results; distinguish earlier recorded test counts from newly executed checks.

Create idempotent, clearly documented development/demo sample data without hardcoded real passwords. Demonstrate: staff creates product +560 variant and monthly plan -> template -> quotation -> confirmed/active subscription -> due invoice -> confirmation -> partial/full payment -> dashboard and customer portal update. Include a second customer and prove isolation. Use appropriate dates or a controlled billing date to demonstrate a due invoice under the existing arrears behavior.

Check browser interaction, desktop/mobile layouts and loading/empty/error cases. Measure representative response times with thousands of subscriptions in an isolated demo/test environment; the target is below two seconds. Record dataset size, environment and timings instead of asserting success without measurements.

Console email does not prove inbox delivery. A billing command does not prove automatic scheduling. Document remaining SMTP/deployment/scheduler work honestly; do not register live scheduled jobs or deploy publicly as a side effect of this assignment. Continue all independent work if an external service is unavailable.

## 9. Deliver a reviewable handoff

Update setup instructions, current ownership, API documentation, integration notes and the completion checklist. Separate implemented, actually tested and externally blocked items. Retain existing functionality and preserve historical test evidence accurately.

Finish with changed features and files, branch/commit information, migration instructions, actual test/browser/performance results, local page URLs, a reproducible demo sequence and exact remaining actions for Arjun, Adwaith and Sreehari. Prepare a concise draft PR description for review. Do not claim the application is fully complete unless the combined workflow and required checks have actually passed.

Start with inspection, then implement and verify. Make routine decisions using the existing code and written requirements. Ask me only about a genuine unresolved requirement or external dependency that prevents meaningful progress; keep completing independent work meanwhile.
