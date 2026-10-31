# Subscription Management System

Python 3.11, Django/DRF, PostgreSQL and same-origin Django templates/CSS/JavaScript.
The local `codex/integration` branch contains authentication, production catalog,
quotations/subscriptions, Adwaith's billing and Sreehari's dashboard/customer
portal. It has not been pushed or merged into main. Browser desktop/mobile QA,
live inbox delivery and deployed scheduling remain open.

Arjun owns authentication, shared setup/integration and the products, plans,
quotations and subscriptions takeover. Adwaith owns billing/payments and finance;
Sreehari owns dashboard/portal presentation. Their reports are preserved in
[BILLING_PROJECT_REPORT.md](docs/BILLING_PROJECT_REPORT.md) and
[DASHBOARD_PROJECT_REPORT.md](docs/DASHBOARD_PROJECT_REPORT.md).

## Setup and compatible upgrade (PowerShell)

Use a reviewed local branch or clone, preserving existing work. Do not copy
another developer's `.env` or reset an existing database. Python 3.11 and
PostgreSQL 14+ are required; this run used Python 3.11.16/PostgreSQL 18.6.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/create_env.py
```

`create_env.py` never overwrites an existing `.env`. Configure your own existing
DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT locally; use a dedicated application
role and a database created by its administrator. Arjun's existing working
server uses port **7129**, not the default 5432. Optionally enter credentials
without printing the password using `scripts/configure_database.py`.

Inspect compatibility and migration history before applying changes:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py check_database
.\.venv\Scripts\python.exe manage.py showmigrations
.\.venv\Scripts\python.exe manage.py migrate --plan
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py create_initial_admin
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Only run `migrate` when the diagnostic and plan match the database. The new
additive migrations are products → subscriptions → billing `0001_initial`, with
the existing swappable `accounts.User` dependency. No authentication migration,
user model or applied history is replaced. Never fake migrations or load the
old billing fixture apps as production dependencies. Bootstrap an admin only if
one is not already present; the command prompts privately and refuses duplicates.
Application roles are independent of Django's `is_staff`/`is_superuser` flags.

## Pages and contracts

- `/login/`, `/signup/`, `/account/`, `/password-reset/`, `/reset-password/`.
- Staff `/manage/`: products, variants, plans, admin-managed taxes, quotation
  templates, subscription editor/detail/actions, invoices, payments and discounts.
- Staff `/dashboard/`: real, global finance summaries and paginated live tables.
- Customer `/portal/`: own subscriptions, permitted actions, invoices and payments.

See [SUBSCRIPTIONS_API.md](docs/SUBSCRIPTIONS_API.md) for actual endpoint URLs,
schemas, role/ownership checks, decimal/date conventions, pricing and lifecycle
policies. [AUTHENTICATION.md](docs/AUTHENTICATION.md) describes session/CSRF and
password reset. [BILLING_INTEGRATION.md](docs/BILLING_INTEGRATION.md) describes the
real-model billing changes. APIs and pages use the same origin; no CORS, separate
frontend server or Node dependency is needed to run the application.

Currency is INR. Each subscription has one recurring plan fee plus its product
lines; the +560 variant adjustment is added once before tax. Prices/tax rates and
plan policies are snapshotted. Billing remains **in arrears** at
`current_period_end`; it is also the sole next-billing date. Financial totals
come from the billing engine, not JavaScript calculations.

## Isolated verification

The helper uses an ignored, password-protected test cluster on loopback **7130**,
separate from the working server. Set PG_BIN if PostgreSQL binaries are elsewhere.
It preserves existing named test databases and never resets the working DB.

```powershell
.\.venv\Scripts\python.exe scripts/test_postgres.py start
.\.venv\Scripts\python.exe scripts/test_postgres.py run test --settings=config.integration_settings --keepdb --noinput
.\.venv\Scripts\python.exe scripts/test_postgres.py run makemigrations --check --dry-run --settings=config.integration_settings
```

Integration settings install the actual production apps and execute their
migrations. Only the auth permission-example fixtures remain test-only. For an
independently provisioned test server, configure dedicated `TEST_DB_*` values
and run `manage.py test --settings=config.integration_settings --keepdb --noinput`.
The test DB name must start with `test_` and differ from the working DB name.

An optional Node runtime can execute `node scripts/test_frontend.mjs` to verify
live dashboard/portal pagination, error behavior and management module loading.
This uses a DOM adapter; it is not browser rendering. Python checks and HTTP
checks do not replace the outstanding desktop/mobile browser QA.

## Reproducible demonstration

```powershell
.\.venv\Scripts\python.exe scripts/test_postgres.py run migrate --settings=config.demo_settings
.\.venv\Scripts\python.exe scripts/test_postgres.py run seed_subscription_demo --settings=config.demo_settings --complete-workflow --browser-credentials
.\.venv\Scripts\python.exe scripts/test_postgres.py run runserver 127.0.0.1:8004 --noreload --settings=config.demo_settings
```

Only the named disposable `test_subscription_demo` is accepted by the seed
command. Generated passwords are in ignored `.local/demo-browser.json`, never
hardcoded or printed. Without `--browser-credentials`, new accounts have unusable
passwords. Reruns preserve existing records. Omit `--complete-workflow` for drafts
you can progress through the UI. See [DEMO.md](docs/DEMO.md) for manual steps and
known expected totals.

For the isolated 5,000-subscription performance dataset:

```powershell
.\.venv\Scripts\python.exe scripts/test_postgres.py run migrate --settings=config.performance_settings
.\.venv\Scripts\python.exe scripts/test_postgres.py run benchmark_subscriptions --settings=config.performance_settings
```

The benchmark refuses other DB names. Results go to ignored
`.local/subscription-performance.json`; measured results and their limits are
recorded in [INTEGRATION_VERIFICATION.md](docs/INTEGRATION_VERIFICATION.md).

## Deployment and remaining external work

`generate_invoices` is a management command, not a configured scheduler. Configure
and monitor an external schedule; repeat catch-up runs when more than 36 periods
per subscription are due. Configure SMTP and verify inbox delivery. Console
email delivers nothing. Invoice printing is HTML; PDF attachments and delivery
audit/retries remain billing follow-up work. No external payment gateway or
refund workflow is claimed.

Before deployment configure HTTPS, exact allowed hosts, DEBUG=False, a trusted
proxy and static serving after `collectstatic`, then run deployment-specific
checks. Never publish `.env`, `.local`, generated credentials or test DB files.
See [HANDOFF.md](docs/HANDOFF.md) for ownership, limitations and draft PR text.
