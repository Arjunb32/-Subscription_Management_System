# Shared repository and team workflow

Updated 31 October 2026 (India time).

## Consolidated application

`main` is the shared application branch. Integration PR #4 combines the existing
authentication foundation, production products/subscriptions, billing, management
screens, dashboard and customer portal. It includes dashboard loading fix
`dbbe2b3` and Sreehari's latest handoff through `7b601bd` (PR #5), including customer
action progress/success feedback and his recorded verification.

The original billing and dashboard snapshots were imported into the integration
implementation before this cleanup. Their histories are now also recorded as
merge parents, retaining the integrated files rather than restoring the earlier
fixture-only billing setup or mock dashboard. Original reports/commits remain
available in Git history; the two feature reports are retained separately under
`docs/`. No unique original feature history needs an extra permanent branch.

## Branches

- `main`: current combined application and default branch.
- `feat/billing`: retained because Adwaith is actively finishing recurring
  scheduling. The older billing PR is superseded by integration; a new PR should
  contain only his subsequent work.
- Completed auth, old dashboard, dashboard handoff and integration branches are
  removed after their histories are reachable from main.

Use one short-lived branch per new piece of work. Open a PR into main and remove
that branch after merging. Avoid separate permanent integration/develop branches
for this project. Preserve local edits before switching or updating branches.

Adwaith should fetch current main and merge it into his existing billing branch
before publishing the scheduling changes. He should preserve/commit local work
first, resolve any affected integration differences, and submit the scheduling
delta as a new PR into main. He must not reset his branch or discard local work.
Sreehari's completed dashboard work is already consolidated; subsequent UI work
starts from current main.

## Running the app

Follow README's environment/database compatibility steps and apply the committed
migrations. The normal local application runs through Django; the isolated demo
uses `config.demo_settings` and its separate seeded database as described in
[DEMO.md](DEMO.md). Neither deleting branches nor merging code resets a database.

Local credentials, demo passwords, database files and local configuration remain
ignored. They are not part of the published application.

## Remaining completion work

- Adwaith: configure/monitor actual recurring scheduling and document its runtime.
- Arjun: configure real email delivery for password reset/invoices and prepare the
  intended deployment or local submission environment.
- Team: prepare final demonstration/submission and record any remaining gaps.

The user requested skipping further testing during consolidation; no new test
suite is claimed for this cleanup. Earlier automated evidence and Sreehari's
reported browser results remain in the verification/report documents. Live email,
external scheduling and public deployment must not be described as complete just
because the code and branch histories have been consolidated.
