# Subscription Management System

Shared Python/Django + Django REST Framework backend for the four-person team.
PostgreSQL database: `subscription_management`. Business modules remain owned by
the subscription, billing/payments, and reporting/customer-portal teammates.

## Current repository and boundaries

Inspected both `main` and `feature/authentication`: both contained only the initial
README. The local `HACKATHON_PLAN.md` is preserved. The team confirmed this is a
new project. Authentication pages now use Django templates, CSS and JavaScript
served by this same backend; no Node/frontend framework is required.

## First setup (each teammate, PowerShell)

Install Python 3.11 or newer and PostgreSQL 14 or newer first. Run these commands
from this repository's root after obtaining the reviewed changes:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/create_env.py
notepad .env
```

To enter the database username and password without displaying the password or
placing it in command history, optionally run:

```powershell
.\.venv\Scripts\python.exe scripts/configure_database.py
```

If `python` is unavailable but the Windows launcher is installed, use
`py -3.11 -m venv .venv`. Activation is optional; the explicit executable avoids
PowerShell execution-policy changes. `create_env.py` generates a random Django
key without printing it and never overwrites an existing `.env`.

Configure `DB_NAME=subscription_management`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`,
and `DB_PORT` locally. PostgreSQL normally uses 5432; **Arjun's existing instance
uses 7129**. Do not put secrets in chat, Git, migrations, or shared examples.
Use a local application database role, not the PostgreSQL superuser. Existing
databases and accounts should be reused after their owner verifies access.

Only when the database and application role do not already exist, a database
administrator can run the following from `psql` (the password is prompted):

```sql
CREATE ROLE subscription_app LOGIN;
\password subscription_app
CREATE DATABASE subscription_management OWNER subscription_app;
```

These are optional first-time provisioning statements, not a reset script. If
the database already exists, coordinate privileges with its owner instead.

Then check compatibility **before** applying migrations:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py check_database
.\.venv\Scripts\python.exe manage.py showmigrations
.\.venv\Scripts\python.exe manage.py migrate --plan
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open `http://127.0.0.1:8000/`. Pages: `/login/`, `/signup/`,
`/password-reset/`, `/reset-password/`, and the signed-in `/account/` view.
Application admins also get a staff-creation form on their account page.
These pages and `/api/` run at the **same origin**; no proxy or CORS configuration
is needed. Set PASSWORD_RESET_URL to your local server's exact `/reset-password/`
URL; use the same hostname throughout.

Stop if `check_database` reports existing/incompatible authentication tables or
history. Do not delete tables, reset the database, fake migrations, or switch the
user model in an existing schema without an agreed migration strategy.

## Shared model and migration conventions

The `accounts.User` model uses email login and the application roles `admin`,
`staff`, and `customer`. Application roles do not use Django's `is_staff` or
`is_superuser` flags. The Django admin site is not enabled in this starter.

Reference the user with `settings.AUTH_USER_MODEL` in model foreign keys and
`get_user_model()` in application code. Customer-owned models should have a
`customer` foreign key to that user. Use integer IDs consistently. Store aware
timestamps in UTC. Each feature owner creates migrations for their own models,
commits those migrations with the model changes, and teammates run `migrate`.
Do not regenerate or edit another owner's applied migrations.

```powershell
# Feature owner only, after adding/changing their model:
.\.venv\Scripts\python.exe manage.py makemigrations <their_app>
```

## Separate PostgreSQL tests

Never point tests at the working database. `config.test_settings` requires a
dedicated `TEST_DB_USER` and a `TEST_DB_NAME` starting with `test_` and different
from `DB_NAME`. A test role needs permission to create the test database; no
application-table privileges on the working database are required.

With independently configured `TEST_DB_*` environment settings:

```powershell
.\.venv\Scripts\python.exe manage.py test --settings=config.test_settings --keepdb --noinput
```

Alternatively, use the optional isolated server below. It initializes an ignored
test cluster in `.local/auth-test-postgres`, with a generated local password,
listens only on `127.0.0.1:7130`, and never connects to the working server. Set
`PG_BIN` if your PostgreSQL binaries are not in PATH or the default Windows
PostgreSQL 18 folder. This cluster is for development tests only.

```powershell
.\.venv\Scripts\python.exe scripts/test_postgres.py start
.\.venv\Scripts\python.exe scripts/test_postgres.py run check_database
.\.venv\Scripts\python.exe scripts/test_postgres.py run migrate
.\.venv\Scripts\python.exe scripts/test_postgres.py run test --keepdb --noinput
.\.venv\Scripts\python.exe scripts/test_postgres.py stop
```

Tests preserve the test database with `--keepdb`, but still create/remove their
own test records. Test data is disposable; working data is not.

## Delivery stages

1. Foundation: shared configuration, locked dependencies, custom user model,
   migrations, database diagnostic, and this setup guide.
2. Authentication: DRF endpoints, role/ownership helpers, initial-admin command,
   password reset and attempt limiting.
3. Integration: Django authentication pages, JavaScript client and team docs.

Work stays on `feat/auth-roles`. No automatic push or merge is performed.

## Authentication handoff

The authentication implementation and JavaScript examples are documented in
[docs/AUTHENTICATION.md](docs/AUTHENTICATION.md). After migrating, create your
local application admin interactively:

```powershell
.\.venv\Scripts\python.exe manage.py create_initial_admin
```

No credentials are supplied by this repository. Login uses sessions and CSRF;
role and customer ownership checks run on the server. Console reset emails are
development output, not actual delivery. Business features are not included.

## Optional browser API verification

After starting the isolated PostgreSQL server, run:

```powershell
.\.venv\Scripts\python.exe scripts/test_postgres.py run migrate --settings=config.browser_settings
.\.venv\Scripts\python.exe scripts/test_postgres.py run runserver 127.0.0.1:8001 --noreload --settings=config.browser_settings
```

Open `http://127.0.0.1:8001/__verification__/` in a browser. The test-only harness
imports the shipped JavaScript client and checks signup, login/session persistence,
CSRF rejection, role rejection, logout and generic reset acknowledgement. It uses
generated disposable credentials in the isolated test database and prints no
passwords. It is not a replacement product screen. These routes are absent from
the default application configuration. HTTP/browser checks use `test_auth_http`,
separate from the unit suite's `test_subscription_management`, so manual test
accounts do not contaminate unit tests. Stop Django with Ctrl+C, then stop the
isolated PostgreSQL server using the command above.

The implementation session's automated browser check was blocked by the browser
tool's inability to verify Chrome's current URL. See
[docs/VERIFICATION.md](docs/VERIFICATION.md) for checks that actually ran.

While the isolated verification server runs, a repeatable HTTP check is:

```powershell
.\.venv\Scripts\python.exe scripts/http_smoke.py
```

It verifies pages, assets, cookie sessions and API behavior over HTTP. It is not
a browser-rendering check and refuses servers without the isolated-test marker.
