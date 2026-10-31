# Integrated verification - 31 October 2026

## Follow-up: dashboard stuck loading

An actual browser run found `dashboard.js` failing while binding the missing
`subscription-status` select. Added the status filter to the overview template
with responsive styling. Updated the frontend harness to obtain element IDs from
the shipped templates and return null for missing controls; it previously created
any requested element, masking this mismatch. The stricter check reproduced the
same exception before the template fix and passed afterward, including initial
load, status filtering, reset, pagination and existing customer action checks.

Restarted the isolated port-8004 demo to discard cached templates. Verified in
the signed-in browser that loading ends and the live dashboard shows 2 active
subscriptions, INR 5,822.40 billed, INR 2,440.80 collected and INR 3,381.60
outstanding. Selecting paused shows zero subscriptions without changing global
totals; Reset restores both subscriptions. This verifies the dashboard loading
fix and those interactions only; the original full desktop/mobile QA and external
service limitations below remain. The follow-up changes are local until published.

## Actual final checks

| Check | Result |
|---|---|
| Remote refresh | PASS; main be770bb, auth 1115af6, billing 3a7660b, dashboard c272eba |
| Production models/migration graph | PASS; real products/subscriptions/billing apps, real 0001 dependencies and existing swappable accounts user |
| Combined isolated PostgreSQL suite | **127 passed**, final complete run 19.211 seconds |
| Fresh installation | PASS; new test_subscription_demo and test_subscription_perf databases migrated from empty |
| Compatible working upgrade | PASS; auth history preserved; 3 additive migrations, 10 to 24 tables; zero pending afterward |
| System and migration drift checks | PASS; no issues or model changes detected |
| Dependency/Python checks | PASS; pip check and compileall |
| Static collection | PASS; 34 total discoverable/collected assets, 4 new copied in this run |
| Frontend module checks | PASS; live staff/customer pagination, unchanged global metrics on pagination/failure, own-action routing, management syntax/initial list |
| Real HTTP demo sessions/data | PASS; known summary totals, management/dashboard/assets, both customer histories, rejected writes and cross-customer detail/print access |
| Working-data server HTTP | PASS on 8003; login 200; protected pages redirect to login; anonymous subscriptions API 403 |
| Demo rerun | PASS; still 2 subscriptions and 4 invoices; no duplicates |
| Whitespace/auth schema review | PASS; git diff --check; accounts models/permissions/applied migrations unchanged |
| Desktop/mobile browser interaction | **BLOCKED**, no pass claimed |
| Inbox email/scheduled deployment | **NOT VERIFIED/NOT CONFIGURED** |

Reproduce from README, `docs/DEMO.md` and `scripts/integration_http_smoke.py`.
The HTTP script refuses a server without the named isolated demo marker and
uses generated local disposable credentials without printing them. The marker
exists only in `config.demo_settings`, not production routes. Test DBs use the
separate auth_test account on a loopback-only PostgreSQL cluster at port 7130;
the working server/role and `.env` were not replaced. No test or benchmark
records were inserted into the working database.

Integration tests cover the +560 variant exactly once and one plan fee; minimum
quantity/availability; template/quotation price, tax and policy snapshots;
expired acceptance; required/invalid transitions and write-field rejection;
manual pause, resumed boundaries, month ends/leap years, renewal, expiry flags,
early closure and missed/capped periods; admin-only taxes; owner reassignment
and related IDs; customer A/B list/detail/action/write/invoice isolation;
bounded pagination and query loading; decimal overflow/ROUND_HALF_UP; discounts,
payments, overpayment, cancellation and reconciliation; number retries and
numeric sequences above 9,999. PostgreSQL threads verify duplicate generation,
last discount use, competing payments, fully accepted-quote billing with a fee,
and pause racing generation. Authentication regressions and CSRF are retained.

The earlier intermediate runs (85 billing/auth and 29 subscription/dashboard)
are subsets, not additional independent tests to add to the final 127.

## Performance evidence

Final dataset: **5,000 subscriptions, 10,000 subscription lines, 10,000 invoices,
20,000 invoice lines, 10,000 payments, two customers**. This fixture builder is
restricted to `test_subscription_perf` and uses bulk inserts for synthetic
benchmark data; correctness of writes is covered separately by domain tests.

Environment: Windows 10 build 26300; Python 3.11.16; PostgreSQL 18.6; local loopback
PostgreSQL cluster. Django request/response clients exercised production query,
serialization, permission and template paths. Each target has one initial request
and five warm requests. No browser rendering or network latency is included.
All measured backend responses are under two seconds; **full browser page-load
performance is still unverified**. These local results are not a production
capacity or concurrency guarantee.

Reproduce:

```powershell
.\.venv\Scripts\python.exe scripts/test_postgres.py run migrate --settings=config.performance_settings
.\.venv\Scripts\python.exe scripts/test_postgres.py run benchmark_subscriptions --settings=config.performance_settings
```

| Target | Initial ms | Warm median ms | Warm max ms |
|---|---:|---:|---:|
| `/api/subscriptions/` | 19.07 | 8.81 | 9.81 |
| `/api/subscriptions/?page=200` | 11.26 | 12.06 | 13.10 |
| `/api/subscriptions/?customer=2` | 9.59 | 8.81 | 9.49 |
| `/api/billing/invoices/` | 37.36 | 21.01 | 21.17 |
| `/api/billing/payments/` | 20.07 | 15.84 | 17.62 |
| `/api/billing/dashboard/summary/` | 15.44 | 13.73 | 15.86 |
| `/dashboard/` | 15.98 | 1.64 | 2.40 |
| `/manage/subscriptions/` | 2.25 | 1.34 | 1.63 |
| `/api/my/subscriptions/` | 8.09 | 8.12 | 26.04 |
| `/api/billing/my/invoices/` | 13.74 | 13.96 | 14.66 |
| `/api/billing/my/payments/` | 12.30 | 12.91 | 13.82 |
| `/portal/` | 3.01 | 1.55 | 1.83 |

## Browser and external limits

Browser inventory reported "The browser access host is unavailable." Native
Chrome was selected through the computer-use skill. When opening a fresh tab,
Computer Use stopped because it could not determine the current Windows browser
URL confidently enough to enforce policy. UI automation ended at that point.
No screenshots, mobile viewport results or complete browser form interaction are
claimed. Module/DOM-adapter and HTTP checks are different evidence.

Live SMTP/inbox delivery and an externally installed scheduler were not
configured. Console email and unit-test outboxes are not inbox delivery. The
invoice command is not scheduling. Print-ready HTML exists; PDF attachment,
mail delivery audit/retries and gateway/refund behavior remain documented billing
follow-up. Deployment/HTTPS/static proxy checks remain environment-specific.
