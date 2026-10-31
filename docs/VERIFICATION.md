# Verification record — 31 October 2026

## Repository preservation

- Remote: `https://github.com/Arjunb32/-Subscription_Management_System.git`.
- Inspected `main` and `feature/authentication`; both were at `7313318` and
  contained only `README.md`. The team then confirmed this is a new project.
- Work is on local `feat/auth-roles`. No push or merge was performed.
- Original `HACKATHON_PLAN.md` remains untouched and untracked.
- Foundation commit: `d396366`; authentication/permissions commit: `1c29333`.

## Passed

- Project virtual environment created; exact installed dependencies pinned.
- `python -m pip check`: no broken requirements.
- `python manage.py check`: no issues.
- Existing PostgreSQL server readiness: `localhost:7129` accepts connections.
- Independent password-protected PostgreSQL 18 cluster initialized on
  `127.0.0.1:7130`, with the separate `test_subscription_management` database.
- Against that isolated database: `check_database`, `migrate --plan`, first
  `migrate`, repeat `migrate` (no further operations), and
  `makemigrations --check --dry-run` (no drift).
- `scripts/test_postgres.py run test --keepdb --noinput`: **52 tests passed**.
  Coverage includes signup/password hashing; password length and character rules;
  email normalization/duplicate protection; login/inactive accounts/logout;
  anonymous DRF 403; CSRF on public auth POSTs, stale token and untrusted origin;
  application-admin staff creation; internal-flag separation; customer list/detail/
  create/update/delete isolation and related-record ownership; staff opt-in;
  reset generic responses, trusted email link, inactive/unknown users, weak
  password rejection, expiry, reuse and old-session invalidation; rate limits and
  expiry; admin bootstrap; counter cleanup; schema diagnostics; and concurrent
  signup, rate-limit increments and reset-token reuse.
- Page tests cover rendered forms/CSRF/assets, anonymous account redirects,
  authenticated page/API session sharing, static discovery and exclusion of the
  verification harness from production routes. Diagnostic tests cover refusing
  legacy auth tables and suppressing connection details in errors.
- The development reset form labels console email explicitly; its label is
  tested separately from SMTP mode.
- During verification, manual HTTP accounts contaminated the original unit-test
  database and caused three failures. This was corrected by separating manual
  verification into `test_auth_http`; the unit suite then passed all 51 tests.
- Loopback Django verification server started on `127.0.0.1:8001`. An actual
  HTTP request to `/api/auth/me/` returned the expected **403**.
- `scripts/http_smoke.py`: **16 HTTP checks passed** against the isolated test
  server, including all four public pages, CSS/JS resources, signup, login,
  session persistence, role denial, CSRF denial, logout and generic reset output.
- Both actual JavaScript modules parsed/imported successfully using the Node
  runtime. This was a module syntax/load check, not browser rendering.
- `manage.py collectstatic --noinput`: 30 static files collected successfully.
- `git diff --check`: no whitespace errors.

## Not verified / remaining integration work

- Working database login/schema/migrations: Django now reads a non-empty password,
  but PostgreSQL rejects the configured username/password pair. Credential-presence
  checks did not display values. No migrations or data changes were made on the
  working server. Run the hidden local prompt `scripts/configure_database.py`
  with a valid PostgreSQL login, then retry `check_database`.
- Django-served frontend pages are implemented and covered by template/session
  tests and real HTTP checks. Visual layout and browser form interactions remain
  unverified by the blocked automated browser tool.
- Automated browser run: the Computer Use tool stopped because it could not
  verify Chrome's current URL. **No browser test is claimed as passed.**
- Live SMTP/inbox delivery: not configured or attempted. Tests used an in-memory
  outbox. Console email is development output only.
- Deployment/proxy/scheduler configuration and teammate business features were
  not performed. Public deployment needs the real frontend, HTTPS, tested mail,
  accurate proxy client identity, and deployment-specific checks.

Use the README's exact setup/migration/test commands. Review compatibility with
any existing schema before applying migrations to a teammate's local database.
