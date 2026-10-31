# Dashboard and Customer Portal Progress Report

**Owner:** SreeHari

**Updated:** 31 October 2026

**Branch:** `feature/dashboard-portal`

**Status:** Django pages and billing API integration are implemented against Adwaith's fetched branch contract. Haridev's subscription list API, the billing branch merge, executable test environment, and end-to-end checks remain outstanding.

## 1. Scope and team ownership

This contribution owns the dashboard and customer-facing portal pages. Arjun owns shared Django/DRF authentication, roles, and backend setup; that foundation is present on `main`. Haridev owns products, plans, and subscriptions. Adwaith owns invoices, payments, and billing summary APIs. This report does not count API descriptions or the dashboard's demo data as completed billing backend work.

## 2. What existed before this work

The checkout originally held a standalone React/Vite prototype in `dashboard-portal/` and the user-edited `dashboard-portal/PROGRESS_REPORT.md`. It did not use the team's intended Django templates/session architecture. Those files were preserved and are still untracked; they are not part of the new Django implementation. The report at `dashboard-portal/PROGRESS_REPORT.md` is retained as historical prototype notes and should not be treated as current status.

I fetched the latest visible `origin/main` and fast-forwarded `feature/dashboard-portal` to the merged authentication foundation at `be770bbd7618de9198fb492e1a85051353b1e6ed`. The latest refresh found `origin/feat/billing` at `3a7660b`; that commit only adds final newlines to six billing test-fixture files. No remote `products`, `subscriptions`, or integration branch is present. PR #2 remains a draft and documents that billing has no production product/subscription models or migrations. Neither billing nor its code has been merged into this feature branch.

## 3. Actual files and their purpose

```text
config/settings.py                         Registers the dashboard Django app
config/urls.py                            Mounts dashboard page URLs
dashboard/
  apps.py                                 Django app configuration
  page_urls.py                            /dashboard/ and /portal/ routes
  pages.py                                Session-required, role-checked page views
  tests.py                                Page access, role, cache and demo-label tests
  templates/dashboard/
    base.html                             Shared dashboard shell and navigation
    overview.html                         Admin dashboard cards, filters and tables
    portal.html                           Customer subscription/invoice/payment tabs
  static/dashboard/
    dashboard.css                        Responsive page and table styling
    dashboard.js                         Shared session check, billing API requests,
                                          demo fallback, states, filters and pagination
DASHBOARD_PORTAL_REPORT.md                This dashboard and portal report
```

The merged shared foundation used by these pages includes `accounts/static/accounts/auth-client.js` and `docs/AUTHENTICATION.md`. The dashboard JavaScript imports `currentUser`, `ApiError`, and `logout` from that existing helper. It does not create another login mechanism, store credentials in local storage, or bypass same-origin cookies/CSRF. The views use Django `login_required`; authorization is checked against `request.user.role` on the server before rendering.

## 4. Screens, routes, and API reality

| Screen | Actual route | Server-side access | Current content |
|---|---|---|---|
| Staff dashboard | `GET /dashboard/` | Authenticated application staff or admin | Metric cards, date/customer/status controls, subscription and invoice tables, pagination, loading/error/empty/session states. In DEBUG, fallback data is clearly labeled as demo fixtures. |
| Customer portal | `GET /portal/` | Authenticated customer role only | Subscription, invoice, and payment tabs. DEBUG examples clearly state that they are generic and not linked to the signed-in customer's account. |

`origin/main` contains the shared authentication API only. The fetched `origin/feat/billing` branch defines these billing endpoints, and the dashboard now calls them through the shared `apiRequest` helper when available:

| Route | What the page uses | Access/scoping documented in `feat/billing` |
|---|---|---|
| `GET /api/billing/dashboard/summary/` | Summary fields `active_subscriptions`, `billed_revenue`, `payments_collected`, `total_outstanding`, `overdue_invoices` (plus monthly/status breakdown fields not currently displayed) | Staff/admin global totals |
| `GET /api/billing/invoices/` | `invoice_number`, `customer`, `customer_email`, `issue_date`, `due_date`, `amount_due`, `status` | Staff/admin; supports `status`, `customer`, inclusive `issue_date_from`, inclusive `due_date_to`, and `overdue=1` |
| `GET /api/billing/my/invoices/` | Customer invoice history | Customer role, queryset scoped to signed-in owner |
| `GET /api/billing/my/payments/` | Payment `id`, `invoice_number`, `payment_date`, `amount`, `payment_method` | Customer role, payments scoped through owning invoice |

Those APIs are not on `main` and `billing` is not enabled in default settings. With `DEBUG=False`, missing/unavailable APIs produce an integration notice and no sample totals/records. In DEBUG only, API errors fall back to visibly labeled generic fixtures. Billing API responses have no currency field in the documented contract; this UI formats decimal values without inventing a currency symbol. The billing APIs do not provide a customer subscription list; that remains pending Haridev's contract.

## 5. Billing metric and filter contract found on `origin/feat/billing`

Adwaith's fetched `docs/BILLING_INTEGRATION.md` gives a concrete dashboard response and these metric definitions. The JavaScript displays those server-calculated totals without recalculating them. The API/contract still has to be merged and confirmed against Haridev's real subscription models.

| Card | Definition in the fetched branch contract (still awaiting production integration) |
|---|---|
| Active subscriptions | Global count whose status is `active` (not a selected-period count). |
| Billed revenue | Global sum of `confirmed` and `paid` invoice totals; excludes drafts and cancelled invoices. |
| Payments collected | Global sum of payments on invoices that are not cancelled. The branch does not model refunds/voids. |
| Outstanding balance | Remaining amount on `confirmed` invoices (`total - amount_paid`). Partial payments reduce the balance. |
| Overdue invoices | Count of `confirmed` invoices with a remaining balance and `due_date` before today. |

The dashboard summary API has no filters, so cards remain global as table filters change. The invoice list applies customer/status and inclusive issue-date-from/due-date-to filters; the overdue filter is sent as `overdue=1`. The documented API does not specify server-side pagination or a currency, so the current UI paginates the returned list locally and displays plain decimal amounts. These are visible integration limitations. The fetched branch document is the billing contract available in the repository; no direct confirmation conversation with Adwaith occurred during this session.

## 6. Customer portal permissions and actions

The portal route requires a signed-in user with the `customer` application role. The dashboard route requires the `staff` or `admin` role to match the billing summary/list APIs. Other roles receive HTTP 403. Billing's fetched branch uses customer-scoped querysets for `/my/invoices/` and `/my/payments/` before returning those records. Its tests include customer A/B invoice and payment isolation cases, but those tests have not been run in this checkout and the branch is not integrated into `main`.

The customer portal now calls the documented `/api/billing/my/...` endpoints, which are designed to scope records server-side; it never sends a customer ID for the server to trust. The current DEBUG examples remain generic, not tied to the session user, and must never be mistaken for verified isolation. No cancel, change-plan, or payment actions are exposed until Haridev confirms permitted workflows and corresponding server-side authorization. A customer-scoped subscription API has not been found.

## 7. Checks and known limits

Automated page tests in `dashboard/tests.py` cover anonymous redirects, role boundaries, DEBUG demo labels, production API configuration, GET-only behavior, and no-cache responses. I installed the pinned requirements in the ignored `.venv` using Python 3.14.8, started the repository's isolated PostgreSQL 18 test server on port 7130, and ran the tests against its separate test database. `manage.py check` reported no issues and **57 tests passed**. The normal working database was not used or modified.

| Requested check | Current evidence |
|---|---|
| Route and role behavior | `dashboard.tests.DashboardPageTests` covers redirects, admin/customer/staff boundaries, demo/production templates, GET-only, and `Cache-Control: no-store`. The complete 57-test suite passed in the earlier clean run. A repeat after browser checks hit stale test-database data; a fresh run then failed during database setup with `relation "accounts_user" does not exist`. Treat the repeat as blocked by local test-database state, not as a passing verification. |
| Shared auth helper and session | Page JS uses existing `currentUser`, `apiRequest`, and `logout`; HTTP smoke confirmed anonymous dashboard/portal requests redirect to `/login/`. An authenticated local browser session displayed the DEBUG dashboard. The backend APIs were unavailable, so this verified the labeled demo fallback only. |
| Filters/pagination/loading/error/empty states | UI calls the billing summary and invoice list APIs with the documented filters; portal calls both `/my/` APIs. Local pagination and loading/error/retry/empty/session states are implemented. Browser interaction verified the demo overdue status filter reduces the invoice table to its overdue sample record. Live API behavior was not verified. Subscription list and server-side pagination remain unavailable. |
| Partial/cancelled invoice reconciliation | The fetched billing branch contains a summary test with a $50 partial payment, a cancelled $999 invoice excluded, and expected billed $330, collected $50, outstanding $280, overdue 2. This is useful fixture evidence from the teammate branch, not a test run or known-data reconciliation on this dashboard branch. |
| Customer A vs Customer B isolation | The fetched billing branch includes API tests asserting customer A cannot see customer B invoices/payments. The portal uses those customer-only endpoints without submitting a customer ID. Tests were not run here; live isolation is not yet independently verified. |
| Browser/responsive checks | HTTP smoke returned 302 for protected dashboard/portal pages, 200 for `/login/`, CSS and JS assets. Desktop browser check confirmed the DEBUG banner, summary cards, sample invoice table and overdue filter. No mobile viewport check or screenshot was saved. |
| Performance with thousands of subscriptions | Not measured. Current demo list is small and uses client-side pagination; this cannot stand in for an API/database benchmark. |
| Secret and unrelated-file review | Staged changes contain only dashboard/report/settings files; common credential-pattern scan and `git diff --cached --check` passed. The preserved React prototype/report remain unstaged. |
| Syntax/whitespace checks | Python source compilation, `node --check`, `git diff --check`, and Django system check passed. The full test suite passed once before browser fixtures were added to the retained test database; subsequent reruns are blocked by test-database setup/state as described above. |

## 8. Next integration steps / blockers

1. **Haridev:** publish the real product/plan/subscription models and migrations, staff and customer subscription-list endpoints with response examples, exact status/date/renewal fields, pagination, and allowed actions. No such remote branch or API is currently visible.
2. **Adwaith:** confirm the dashboard report rename, and document server-side invoice pagination (query parameters and response shape) and the billing currency/code/precision. The current PR #2 contract has no currency or server-side pagination. A coordination comment could not be submitted because PR #2's comment controls were disabled in this session.
3. **Arjun:** identify or create the agreed integration branch and coordinate landing authentication, Haridev's models, and Adwaith's billing APIs/migrations together. Current `origin` has no integration branch, and billing is not enabled in `main`.
4. After those dependencies land, connect the subscription tables/actions to their real endpoints, switch the invoice table to server-side pagination, and run the relevant integrated tests against real models and migrations.
5. Verify known invoice/payment totals, partial/full/cancelled/overdue cases, and customer A/B access on the combined backend.
6. Run desktop/mobile browser checks, capture screenshots, and benchmark the real APIs/page with thousands of records. Do not infer performance from the small development fixture.
7. Keep PR #3 in draft until these integration and verification items pass; never push to `main`, force-push, or merge automatically.

## 9. Commit and remote publication status

The latest remote information was fetched: `origin/main` remains at the auth foundation and `origin/feat/billing` is `3a7660b`. Dashboard commits `1a07ba4` and `b316be3`, followed by report updates `9f397ec` and `c272eba`, are pushed to `origin/feature/dashboard-portal`. This follow-up renames the dashboard report to `DASHBOARD_PORTAL_REPORT.md` so it does not collide with the billing branch's root `PROJECT_REPORT.md`. The earlier React prototype/report remain preserved, untracked, and unstaged.

The staged-diff review found no common private-key, API-key, password, or configured Django-secret patterns; `git diff --cached --check` passed. The local follow-up commit renames the dashboard report to `DASHBOARD_PORTAL_REPORT.md` so it does not collide with the billing branch's root `PROJECT_REPORT.md`. Pull request [#3](https://github.com/Arjunb32/-Subscription_Management_System/pull/3) remains a draft from `feature/dashboard-portal` into `main`; the last page check showed no conflicts and no CI checks. The follow-up commit was created locally, but its push failed with Git for Windows `SEC_E_NO_CREDENTIALS`; the rename and demo-filter fix are not yet on GitHub. The PR description was updated to summarize the already-published implementation, verification limits, blockers, and the local follow-up awaiting publication. Keep it draft until Haridev's subscription API and billing dependencies are integrated.

## 10. Current dashboard and interface (visual summary)

The Django dashboard presents five server-calculated billing summary cards, invoice issue-date/due-date/customer/status filters, an invoice table, and a subscriptions table awaiting Haridev's API. The customer portal reads invoices and payments from the billing branch's customer-scoped APIs and awaits Haridev's subscription endpoint. Both pages include shared session navigation, responsive styling, loading/error/retry/empty/session states, and role-specific server routes. In DEBUG, unavailable APIs use clearly labeled fixture data. Desktop browser interaction of the DEBUG fallback was checked; real backend behavior, mobile layout, and performance remain unverified.
