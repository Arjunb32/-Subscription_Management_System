# Products/subscriptions integration handoff — 31 October 2026

## Local review state

Review **`codex/integration`**. No pushes, PR creation or merge into main were
performed. `codex/products-subscriptions` contains the initial catalog/workflow
commit `e8c6be5`; integrated fixes, billing-dependent lifecycle operations, UI,
tests and final documentation are on the integration branch. Main baseline was
incorporated locally by `cce8999`. Use `git log -3 --oneline` for the final review
commit recorded alongside this document in the handoff response.

Fetched remote heads remained main `be770bb`, auth `1115af6`, billing `3a7660b`,
dashboard `c272eba`. Billing/dashboard app files were imported with `git show`
from those exact commits, preserving their architecture, templates and tests;
shared configuration/URLs were integrated deliberately. Both different
PROJECT_REPORT files are retained under distinct names in `docs/`. The user's
Word-report deletion is retained. Their expanded plan, checklist and takeover
prompt are preserved; the plan was additionally backed up under ignored `.local`
and in a path-specific Git stash while incorporating main. No stash was dropped.

## Implemented

Production product/variant/plan/tax/template/subscription models and migrations;
validated, paginated staff/customer APIs; management screens; template snapshots;
explicit quotation/confirmation/activation/pause/resume/renew/close actions;
policy/ownership checks; protected archives; one recurring plan-fee line; +560
variant pricing; frozen taxes/prices/interval/policies; audit events; shared
calendar calculation and arrears billing boundaries.

Adwaith's engine generates real itemized invoices and handles discounts,
confirmation, cancellation, partial/full payments and reconciliation. Integration
fixes cover zero-day payment terms, automatic-close policies, frozen tax rates,
numeric invoice sequences beyond 9,999, before-tax discount allocation, manual
invoice safety, validation errors and bounded pagination. Subscription actions
and generation share transactional parent locks.

Sreehari's dashboard/portal use real subscription and billing endpoints,
server-side pagination and permitted action buttons. Live pagination cannot
replace records or totals with demo fixtures. Global finance summaries are
explicitly labeled; invoice/date filters and subscription-status filters are
separate. Invoice links open the existing itemized print route.

## Setup and actual local URLs

The three additive initial migrations were inspected and applied to the existing
working database, preserving accounts/auth migrations and local configuration.
Working DB diagnostic: 24 public tables, consistent history, zero pending
migrations. No working test accounts or sample business records were created.
Future clones use README's compatibility diagnostic and migration plan first.

At handoff the integrated working-data server is running at:

- `http://127.0.0.1:8003/login/`
- `http://127.0.0.1:8003/manage/` and `/manage/products/`, `/manage/variants/`,
  `/manage/plans/`, `/manage/tax-rules/`, `/manage/quotation-templates/`
- `http://127.0.0.1:8003/dashboard/` and `/portal/` (role-limited)

The earlier server on port 8000 was left available; verification uses 8003 to
avoid depending on its loaded code. To restart the integrated working server:
`python manage.py runserver 127.0.0.1:8003 --noreload` using the project's venv.
Use one hostname consistently and configure reset links to the chosen origin.

The isolated, seeded demonstration runs at `http://127.0.0.1:8004/login/` and the
same management/dashboard/portal paths. README/DEMO describe recreation using
`config.demo_settings`. Disposable generated credentials are stored locally in
ignored `.local/demo-browser.json`, never in this document or Git. The demo seed
is repeatable and refuses the working DB. Performance data uses a different DB.

## Evidence and limits

**127 tests passed** on isolated PostgreSQL with production app migrations,
including authentication/CSRF, A/B isolation, lifecycle/quotations/policies,
calendar boundaries, tax permissions, snapshots, catch-up limits, discounts,
payments/reconciliation and real-model threaded concurrency. Fresh demo and
performance DB migrations passed; working auth-only DB upgraded additively.
System checks, migration drift, dependency checks, Python compilation, static
collection and frontend module behavior checks passed. Real HTTP session/API
checks reconcile the known demo totals and deny cross-customer details/printing.

5,000 subscriptions/10,000 invoices/10,000 payments/20,000 invoice lines were
measured in the isolated performance DB. All measured backend responses were
below 38 ms on the final run; this excludes browser rendering and network
latency. Exact data, environment, command and timings are in
[INTEGRATION_VERIFICATION.md](INTEGRATION_VERIFICATION.md).

**Browser desktop/mobile validation remains blocked.** The browser connector's
host was unavailable. Native Computer Use stopped after it could not establish
Chrome's current URL confidently enough to enforce policy. UI automation ended;
no screenshot/layout/interactive browser pass is claimed. The responsive layouts
are implemented and template/module behavior is tested, but require manual QA.

Live SMTP inbox delivery, an externally configured/monitored billing scheduler,
public deployment and production capacity are not verified. Console email is
not delivery; a management command is not scheduling. Printing is HTML. Optional
PDF attachments, delivery audit/retries, refunds and a live payment gateway are
not implemented. No claim is made that the complete deployed application is done.

## Remaining owners

| Owner | Remaining action |
|---|---|
| Arjun | Review the integration commit and business policies; configure/test SMTP and reset origin; manually verify desktop/mobile forms and customer actions; publish/review branches only when requested; deploy and run deployment-specific checks. |
| Adwaith | Review coordinated finance changes (INR, pre-tax discounts, zero-day terms, fee line, expiry); configure/monitor scheduling; verify live invoice email; decide PDF/delivery audit/refund/gateway follow-up as needed. |
| Sreehari | Manually verify dashboard/portal loading/empty/error/session states and mobile layout; check complete browser workflow and page latency; polish presentation using the final contract; keep global summary labeling. |

For Sreehari: staff `GET /api/subscriptions/`, own-customer
`GET /api/my/subscriptions/`, details at `{id}/`, permitted POST
`{id}/actions/{action}/` with `{}`. List envelope is count/next/previous/results.
Rows include stable ID/number, authorized customer display/email, plan name,
status, dates, `renewal_date` alias, INR `price`/`subtotal` and `permitted_actions`.
Use `/api/billing/dashboard/summary/` for global finance totals and scoped billing
`/my/invoices/` and `/my/payments/` for customer history. Full schemas and policy
semantics are in [SUBSCRIPTIONS_API.md](SUBSCRIPTIONS_API.md). No teammate was
automatically messaged.

## Draft PR

**Title:** Integrate production catalog, quotations and subscription lifecycle with billing and portal

Customers can now receive a snapshotted quotation, accept it when allowed and
receive recurring itemized invoices through the existing billing engine. Adds
production models/migrations, staff management pages, policy-checked lifecycle
actions and customer-scoped APIs; connects the existing dashboard/portal to live
paginated records and preserves both teammate reports. Pricing includes one plan
fee plus product/variant lines, with frozen taxes and INR decimal rounding.

Validation: 127 isolated PostgreSQL tests; fresh migrations and additive working
DB upgrade; HTTP session/isolation/summary checks; frontend pagination/module
checks; 5,000-subscription backend benchmark. Browser desktop/mobile checks are
blocked by the Computer Use URL-policy host; live SMTP, scheduling and deployment
remain external follow-up. Review the documented pause/expiry/early-close policy.
