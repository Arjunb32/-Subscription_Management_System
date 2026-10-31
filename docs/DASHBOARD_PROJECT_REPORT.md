# Dashboard and Customer Portal Progress Report

**Owner:** SreeHari

**Updated:** 31 October 2026

**Branch:** `feature/dashboard-portal`

**Status:** Django pages and billing API integration are implemented against Adwaith's fetched branch contract. Haridev's subscription list API, the billing branch merge, executable test environment, and end-to-end checks remain outstanding.

## 1. Scope and team ownership

This contribution owns the dashboard and customer-facing portal pages. Arjun owns shared Django/DRF authentication, roles, and backend setup; that foundation is present on `main`. Haridev owns products, plans, and subscriptions. Adwaith owns invoices, payments, and billing summary APIs. This report does not count API descriptions or the dashboard's demo data as completed billing backend work.

## 2. What existed before this work

The checkout originally held a standalone React/Vite prototype in `dashboard-portal/` and the user-edited `dashboard-portal/PROGRESS_REPORT.md`. It did not use the team's intended Django templates/session architecture. Those files were preserved and are still untracked; they are not part of the new Django implementation. The report at `dashboard-portal/PROGRESS_REPORT.md` is retained as historical prototype notes and should not be treated as current status.

I fetched the latest visible `origin/main` and fast-forwarded `feature/dashboard-portal` to the merged authentication foundation at `be770bbd7618de9198fb492e1a85051353b1e6ed`. A later remote refresh also found `origin/feat/billing` at `a13cafd` and its `docs/BILLING_INTEGRATION.md`. Existing prototype/report changes were stashed before updating and then restored. Neither the billing branch nor its code has been merged into this feature branch; it is used as the documented integration target only.

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
PROJECT_REPORT.md                         This current progress report
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

| Card | Proposed definition to confirm |
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
| Route and role behavior | `dashboard.tests.DashboardPageTests`: redirects, admin/customer/staff boundaries, demo/production templates, GET-only, and `Cache-Control: no-store`; included in the 57 passing tests. |
| Shared auth helper and session | Page JS uses existing `currentUser`, `apiRequest`, and `logout`; HTTP smoke confirmed anonymous dashboard/portal requests redirect to `/login/`. Authenticated browser behavior was not visually checked. |
| Filters/pagination/loading/error/empty states | UI calls the billing summary and invoice list APIs with the documented filters; portal calls both `/my/` APIs. Local pagination and loading/error/retry/empty/session states are implemented. Browser/API interaction was not verified. Subscription list and server-side pagination remain unavailable. |
| Partial/cancelled invoice reconciliation | The fetched billing branch contains a summary test with a $50 partial payment, a cancelled $999 invoice excluded, and expected billed $330, collected $50, outstanding $280, overdue 2. This is useful fixture evidence from the teammate branch, not a test run or known-data reconciliation on this dashboard branch. |
| Customer A vs Customer B isolation | The fetched billing branch includes API tests asserting customer A cannot see customer B invoices/payments. The portal uses those customer-only endpoints without submitting a customer ID. Tests were not run here; live isolation is not yet independently verified. |
| Browser/responsive checks | HTTP smoke returned 302 for protected dashboard/portal pages, 200 for `/login/`, CSS and JS assets. Computer Use browser capture failed twice (`FrameArrived timed out`, then `window capture timed out`); no screenshot or visual responsive check is claimed. |
| Performance with thousands of subscriptions | Not measured. Current demo list is small and uses client-side pagination; this cannot stand in for an API/database benchmark. |
| Secret and unrelated-file review | Staged changes contain only dashboard/report/settings files; common credential-pattern scan and `git diff --cached --check` passed. The preserved React prototype/report remain unstaged. |
| Syntax/whitespace checks | Python source compilation, `node --check`, and `git diff --check` passed. Django system check and 57 tests passed. |

## 8. Next integration steps / blockers

1. Haridev publishes/confirms production subscription list and customer subscription endpoints, statuses, fields, pagination, and permitted actions. The billing branch's production migration dependencies are explicitly pending those models.
2. Merge/integrate Adwaith's `feat/billing` branch and its dependencies into the team integration branch; billing endpoints are conditional and absent from current `main`.
3. Confirm pagination and currency with Adwaith. The current billing contract has no server pagination or currency field; this UI currently paginates returned records locally and formats decimal values without a symbol.
4. Run the billing branch's isolated tests after its APIs are merged; compare dashboard-rendered values to its partial/cancelled fixtures and real known invoice/payment records.
5. Browser-check role navigation, filter submission/reset, tabs, pagination, session expiry, narrow layout, and accessible status/empty feedback. Capture screenshots.
6. Benchmark the actual API/page with a documented environment and at least thousands of records; report dataset and timings. Do not infer API performance from the current demo fixture.
7. Commit and publish this branch and open a draft PR while subscription-model integration is blocked. Never push to `main`, force-push, or merge automatically.

## 9. Commit and remote publication status

The latest remote information was fetched and `feature/dashboard-portal` was fast-forwarded to the verified `origin/main` auth foundation. A subsequent fetch found `origin/feat/billing` at `a13cafd`; that feature branch was inspected but not merged. Commits `1a07ba4` (Django dashboard/portal pages) and `b316be3` (billing API wiring, staff-role correction, and contract/report updates) are pushed to `origin/feature/dashboard-portal`. The earlier React prototype and user-edited prototype report remain untracked and unstaged.

The final staged-diff review found no common private-key, API-key, password, or configured Django-secret patterns; syntax and whitespace checks passed. Pull request [#3](https://github.com/Arjunb32/-Subscription_Management_System/pull/3) is open as a draft, from `feature/dashboard-portal` into `main`, with three commits and no merge conflicts. It has no CI checks yet and its description is blank. The draft state should remain until Haridev's subscription API and billing dependencies are integrated. No push authentication failure occurred.

## 10. Current dashboard and interface (visual summary)

The Django dashboard presents five server-calculated billing summary cards, invoice issue-date/due-date/customer/status filters, an invoice table, and a subscriptions table awaiting Haridev's API. The customer portal reads invoices and payments from the billing branch's customer-scoped APIs and awaits Haridev's subscription endpoint. Both pages include shared session navigation, responsive styling, loading/error/retry/empty/session states, and role-specific server routes. In DEBUG, only, unavailable APIs use clearly labeled fixture data. End-to-end behavior, browser checks, and performance remain unverified.

## 11. Follow-up on `codex/integration` (31 October 2026)

The integration branch now includes the production subscription and billing APIs. I checked this branch in a separate local worktree, using the documented `config.demo_settings` database on the isolated PostgreSQL test server; no team/working database was used. Empty demo migrations applied, and the documented seed produced two subscriptions and four invoices.

Desktop browser verification confirmed the dashboard loaded live seeded data and displayed the expected global totals: 2 active subscriptions, INR 5,822.40 billed, INR 2,440.80 collected, INR 3,381.60 outstanding, and 2 overdue invoices. Filtering to demo customer A narrowed both tables to that customer's records while the global summary stayed unchanged. The subscription status filter now exposes the backend's exact `draft`, `quotation`, `confirmed`, `active`, `paused`, and `closed` values. At 390 × 844, the dashboard and customer portal had no horizontal document overflow; the portal tables use their own horizontal scrolling area on narrow screens.

The authenticated demo-customer-A portal was checked in the browser on all three tabs. It showed one owned subscription, two owned invoices (one paid and one partially paid with INR 1,440.80 remaining), and two owned payments. Customer B's browser session showed only B's own one subscription, two invoices, and no payments. Customer B's pause and resume actions were also checked: the portal announced the in-progress action and success, refreshed the subscription status, and returned it to Active. The integrated `scripts/integration_http_smoke.py` also passed: exact staff summary reconciliation, page/static asset responses, customer A and B scoped lists, rejected unauthorized writes, and 404s for cross-customer subscription, invoice and print details. `node scripts/test_frontend.mjs`, JavaScript syntax, and Git whitespace checks passed.

This browser review found two integration presentation defects and fixes them on the local review branch `codex/dashboard-integration-polish`: the dashboard JavaScript expected a subscription-status control missing from its template, which stopped the page script; and at a 390 × 844 viewport the navigation was squeezed to 62 px. The template now includes the status selector, and the mobile header gives the navigation its own full-width row. After the fix, dashboard rendering and filters worked, the navigation occupied 339 px of the 375 px document, and the page had no horizontal document overflow. A mobile screenshot was captured in the review session.


## 12. Final dashboard handoff verification (31 October 2026)

The team integration branch advanced to `dbbe2b3`, which includes the dashboard startup/status-filter fix, responsive filter styling, mobile navigation fix, and stricter template-bound frontend checks. The handoff branch is based on that current integration head; it does not replay those shared changes. Customer subscription actions now announce progress, disable the selected button while the request runs, announce success, and refresh the row. A browser pause/resume check returned the demo subscription to Active.

The integrated Django suite was rerun on the isolated PostgreSQL database `test_integration_keep`: **127 tests passed in 53.105 seconds**, with no system-check issues. The template-bound frontend module check passed, covering dashboard startup, status-filter/reset, pagination, error handling, and customer-scoped action routing. `node --check` and `git diff --check` passed. Earlier browser and HTTP checks in section 11 verified customer A/B isolation, live billing totals, desktop/mobile layout, and denied cross-customer detail and write requests.

A fresh backend benchmark used the separately named `test_subscription_perf` database on the loopback PostgreSQL 18.6 test server. It contained 5,000 subscriptions, 10,000 subscription lines, 10,000 invoices, 20,000 invoice lines, 10,000 payments, and two customers. Environment: Windows 10 build 19045, Python 3.14.8, PostgreSQL 18.6. Each route had one cold request and five warm requests through Django's request/response client; measurements exclude network latency and browser rendering.

| Route | Cold ms | Warm median ms | Warm max ms |
|---|---:|---:|---:|
| `/api/subscriptions/` | 52.02 | 23.38 | 31.61 |
| `/api/subscriptions/?page=200` | 33.77 | 34.68 | 39.82 |
| `/api/subscriptions/?customer=2` | 29.85 | 30.65 | 31.87 |
| `/api/billing/invoices/` | 68.56 | 38.93 | 40.30 |
| `/api/billing/payments/` | 49.83 | 74.03 | 79.67 |
| `/api/billing/dashboard/summary/` | 42.22 | 34.76 | 38.32 |
| `/dashboard/` | 34.58 | 4.51 | 5.19 |
| `/manage/subscriptions/` | 6.04 | 4.31 | 5.76 |
| `/api/my/subscriptions/` | 37.10 | 34.58 | 36.39 |
| `/api/billing/my/invoices/` | 42.73 | 40.84 | 45.94 |
| `/api/billing/my/payments/` | 71.32 | 63.02 | 78.47 |
| `/portal/` | 13.70 | 4.35 | 5.35 |

All measured backend responses were under two seconds in this local synthetic-data run. This does not establish production capacity, concurrent-load performance, or full browser page-load timing. External email delivery, invoice scheduling, deployment, and production configuration remain outside these dashboard checks. The dashboard handoff is published on `origin/codex/dashboard-handoff` (head `0bbce25`) in draft [PR #5](https://github.com/Arjunb32/-Subscription_Management_System/pull/5), targeting `codex/integration`. It remains a draft for reviewer feedback before integration with `main`.
