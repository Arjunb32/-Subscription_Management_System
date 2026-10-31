# Subscription Management System: four-person hackathon plan

## Basis and assumptions

Based on the supplied Subscription_Management_System.pdf, pages 1–4. The linked Drive video could not be accessed; additional judging criteria or submission rules from that video remain unverified. Document requirements below are product requirements, not instructions authorizing external actions.

The team is Haridev, Adwaith, Sreehari and Arjun (assumed name for the user). All four report no strong specialist skill. The hackathon runs from 9:00 AM to 5:00 PM: eight hours. Assignments below are practical starting responsibilities, not claims about expertise. This is a proposed implementation plan; no repository, deployment, or GitHub settings have been created. Prefer the language and framework most of the team already knows. Use one application and one shared relational database to reduce integration work.

## What you are building

A platform for Brightloop Software to configure products and recurring plans, sell subscriptions, generate invoices, record payments, and report results. Three roles: admin, internal staff, customer. A customer must only access their own records; staff permissions must be enforced on the server, not merely by hiding buttons.

## Ownership: divide by working feature area

| Owner | Feature area and screens | Server/data responsibility | Completion evidence |
|---|---|---|---|
| Arjun — access and integration lead | Sign up, login, password reset, staff management, shared navigation | Users, roles, ownership checks, environment setup, shared API conventions, integration and deployment | Admin can create staff; staff/customer cannot; customer A cannot read customer B's data; reset token expires and is single use |
| Haridev — catalog and subscription lead | Products, variants, plans, quotation templates, subscription list/detail/editor | Products, plans, template lines, subscription lines and lifecycle, renewal/pause/close policy | Create a quote from a template and progress Draft → Quotation → Confirmed → Active → Closed; enforce plan rules |
| Adwaith — billing and payments lead | Invoice list/detail, tax and discount settings, payment entry, printable invoice | Recurring invoice generation, tax/discount calculation, payment allocation, duplicate prevention | Generate a correct invoice, rerun billing without duplicates, record a payment, update outstanding balance |
| Sreehari — portal, reporting and quality lead | Customer portal, dashboard, filters and summary views | Reporting queries and customer-facing read endpoints, seed/demo data, end-to-end checks and presentation | Portal shows only the signed-in customer's subscriptions/invoices; dashboard matches invoice and payment records |

Each person owns both UI and server work for their feature area. Arjun coordinates merges, but reviews rotate so that integration does not depend on one person. Sreehari starts immediately using agreed sample responses; they do not wait until the end to begin testing.

Shared-file owners: Arjun owns application setup, auth middleware and navigation; Haridev owns the initial schema; Adwaith owns money calculation helpers; Sreehari owns seed data and demo scripts. Later schema changes use separate migrations, reviewed with the affected feature owner. Tell the owner before changing a shared file.

## Requirements checklist

### Access — Arjun

- Unique email; define a consistent normalization rule.
- Password length greater than eight characters, with uppercase, lowercase and special character.
- Reset link sent to the registered email; hashed passwords and expiring, single-use reset tokens.
- Admin, staff and customer access. Only admin adds staff. Explicit staff permission matrix agreed in hour 1.
- Check authentication, role and record ownership on every protected endpoint.

### Products, plans and subscriptions — Haridev

- Product name, type, sales price, cost price and notes; variants with additional prices. Include the PDF's Odoo variant example (+560) in demo data.
- Plan price, daily/weekly/monthly/yearly recurrence, minimum quantity and availability dates.
- Per-plan rules for automatic close at expiry, early closure, pause and renewal.
- Quotation templates with plan, product lines and validity duration.
- Unique subscription number, customer, plan, start/expiry dates, payment terms and product lines containing quantity, unit price, taxes and amount.
- Enforce Draft → Quotation → Confirmed → Active → Closed transitions. Represent pause separately from these required states, and define how resumption changes the next billing date.

### Invoices, discounts and payments — Adwaith

- Due subscriptions produce invoices with customer details, product lines, taxes and totals.
- Invoice states Draft → Confirmed → Paid; explicitly model cancellation as a separate terminal state.
- Confirm, cancel, send and print actions. Sending needs an actual configured delivery service; clearly label any demo-only delivery fallback.
- Admin-managed tax rules and admin-only discount creation.
- Fixed/percentage discounts; minimum purchase or quantity; validity dates; redemption limit; product or subscription scope.
- Eligible discounts apply automatically to the next invoice, stop when expired/exhausted, and cannot be consumed twice on a retry.
- Payments record method, amount, date and note against an invoice; show outstanding and overdue invoices.
- Recurring billing must be safe to retry and must catch up missed due periods without generating duplicate invoices.

### Portal and reports — Sreehari

- Customer portal for own subscriptions and invoices, with permitted subscription management actions.
- Active subscription count, billed revenue, payments collected, outstanding amount and overdue invoices, with date/status/customer filters and summaries.
- Define each metric visibly: billed revenue comes from confirmed/non-cancelled invoices; collections come from payments. Do not count the same money twice.
- If adding monthly recurring revenue, label it separately and document normalization; it is an enhancement, not an explicit PDF metric.
- Measure representative pages with thousands of subscriptions. Target under two seconds; use pagination, indexes and database aggregation, and report the measured dataset and environment.

## Shared contract: settle before parallel coding

Create a short API contract with endpoint, request fields, response fields, error shape, permissions and owner. Commit shared example responses so each member can work independently.

Core entities: User, Product, ProductVariant, Plan, QuotationTemplate, QuotationTemplateLine, Subscription, SubscriptionLine, TaxRule, DiscountRule, DiscountRedemption, Invoice, InvoiceLine, Payment. Add tables only when required by a real flow.

Essential agreements:

1. IDs, timestamps, currency, timezone, rounding and validation conventions are identical across modules. Use integer minor units or exact decimals for money, never binary floating-point arithmetic.
2. Subscription lines retain agreed sale prices. Invoice lines snapshot prices, taxes and discounts so later catalog changes do not rewrite old bills.
3. Use a unique subscription-and-billing-period key plus transactional generation. A retry must return/reuse the original invoice; cancellation does not silently enable another charge for the same period.
4. Define calendar billing: month-end behavior, leap years, renewal dates, paused periods and expiry boundaries. Store next billing date explicitly.
5. Recommended demo calculation: subtotal → eligible discount → tax on discounted base → invoice total. Treat this as a documented demo rule, not tax-law compliance. Agree discount stacking and redemption counting before implementation.
6. An invoice is paid only when applied payments cover its total. Partial payments reduce balance; reject or explicitly handle overpayments. Cancellation of paid invoices requires a defined reversal policy; keep refunds outside initial scope unless required.
7. Overdue means due date has passed and remaining balance is positive on a confirmed invoice. Define the dashboard reporting date range consistently.
8. Plan actions, invoice actions and customer access must be checked on the server.

## Build sequence: 9:00 AM–5:00 PM

The complete brief is ambitious for four beginners in eight hours. Aim for a reliable core demonstration first and track unfinished requirements openly. These priorities are a delivery strategy, not a change to the organizers' requirements. Check the video before finalizing scope.

| Time | Target | Responsibilities |
|---|---|---|
| 9:00–9:30 | Shared setup and agreement | Everyone runs the same starter app. Agree fields, sample responses and navigation. Arjun coordinates setup; all approve the initial schema. |
| 9:30–11:00 | First small working sections | Arjun: login and role checks. Haridev: product, plan and subscription creation. Adwaith: invoice calculation and payment entry. Sreehari: dashboard and portal using agreed sample data. |
| 11:00–11:30 | First integration checkpoint | Merge the first pieces, connect real records and resolve mismatched fields together. |
| 11:30–1:00 | Complete the core flow | Create a subscription, generate its invoice, record payment and see dashboard totals change. Add customer ownership checks. |
| 1:00–1:20 | Break and progress review | Confirm what actually works. Remove optional extras from the queue if the core flow is incomplete. |
| 1:20–2:30 | Improve required coverage | Add basic tax/discount rules, invoice printing, overdue display and lifecycle validation. Choose further requirements by organizer priority and remaining time. |
| 2:30–3:00 | Connect and deploy | Everyone helps resolve integration problems. Verify the shared deployment or required submission environment. |
| 3:00–4:00 | Feature freeze and checks | Test access isolation, totals, billing retries and payments. Fix blockers. Measure performance if core checks pass. |
| 4:00–4:30 | Prepare submission | README, screenshots, demo accounts, known limitations and backup recording. |
| 4:30–5:00 | Rehearse and submit | Run the complete demo twice, verify submission links and submit before the deadline. |

### First deliverable for each person

- Arjun: working login, three roles, shared navigation and server-side access checks. Coordinate merges with a teammate; do not try to review every change alone.
- Haridev: create a product and monthly plan, then create and activate a subscription linked to a customer.
- Adwaith: generate a persisted invoice from that subscription, prevent duplicate generation for its period, and record payment against it.
- Sreehari: show active subscriptions, collected payments, outstanding balance and overdue invoices from real data, plus a customer-only view.

### Coverage after the first working flow

Prioritize signup and staff controls, basic tax and discount rules, invoice print/status actions, and subscription lifecycle checks. Then tackle variants, quotation templates, all recurrence frequencies, full discount eligibility/limits, pause/renew policies, reset-email delivery, invoice emailing and performance evidence as time allows. These remain requirements in the PDF even if unfinished at submission. Track each as Done, Partial or Not implemented.

For a demo, a clearly labeled “Run due billing” button can call the same billing function that a scheduler would use. Without an actual scheduled job, describe recurring scheduling as incomplete. Record payments manually; a real card gateway is not needed for the stated payment-recording flow.

Merge a small change every 60–90 minutes. If anyone is stuck for more than 15 minutes, pair with a teammate. Keep one shared data model and avoid having four people independently generate entire applications. If using AI coding tools, give each tool the agreed contract and ask it to modify only the owner's section; inspect and run the result before pushing.

Delivery priority is sequencing, not permission to omit brief requirements. First prove the complete core flow; then implement remaining specified behavior. If time runs out, disclose incomplete items rather than presenting placeholders as complete. Avoid adding AI, real card charging, multi-currency, complex proration or microservices unless the video specifically requires them. Recording payments is explicitly required; a live payment gateway is not specified in the PDF.

## Git, versions and feature coordination

Use one shared GitHub repository and short-lived feature branches. The main branch should always run. For four people, a separate develop branch usually adds coordination work without helping this short schedule.

Branch examples:

- `feat/12-auth-roles`
- `feat/18-plans-subscriptions`
- `feat/24-recurring-invoices`
- `feat/31-customer-dashboard`
- `fix/37-duplicate-invoice`

Daily workflow (repeat for each small feature):

```text
git switch main
git pull --ff-only origin main
git switch -c feat/12-auth-roles
# Make one coherent change and run the relevant checks.
git add <specific-files>
git commit -m "feat(auth): add role-based access"
git push -u origin feat/12-auth-roles
# Open a pull request; another member reviews it; squash-merge after checks pass.
```

Before merging, update the branch with current main, resolve any conflicts with the relevant file owner, and rerun affected checks. Never choose all of one side of a conflict without understanding the result. Do not force-push main. Do not commit secrets, local environment files, dependency folders or local databases. Commit dependency lockfiles, migrations and a safe `.env.example`.

Configure main protection if supported by your repository/account: require a pull request, one approval and passing checks. Otherwise enforce the same rules as a team agreement. Automated checks should run lint/type checks, relevant tests and a production build using the chosen stack.

PR description: linked issue, what changed, screenshot for UI changes, how verified, migrations/config changes, dependencies, and known limitations. Keep PRs small enough for a teammate to review quickly. The feature owner resolves review feedback; the reviewer or integration lead merges.

Use a board: Backlog → Ready → In progress → Review → Done. Every ticket has one owner, acceptance criteria, dependency links and a PR link. Limit each person to one primary in-progress ticket. A pushed branch is not a completed feature: Done means reviewed, merged, checked on the shared app and documented if needed.

Tag verified milestones on main:

- `v0.1.0`: accounts, catalog and subscription workflow.
- `v0.2.0`: invoices and payments connected.
- `v0.3.0`: portal, reports and remaining requirements integrated.
- `v1.0.0`: tested hackathon submission; document any known gaps.
- `v1.0.1`: subsequent demo-blocking bug fix, if needed.

Keep a short CHANGELOG with working features and known gaps at each tag. Record deployed commit/tag so everyone knows what the demo contains. Use revert PRs for faulty merged changes; coordinate database migration recovery separately.

## Acceptance checks before submission

- Duplicate email and invalid password are rejected; reset links work once and expire.
- Customer A cannot access customer B's invoice by changing its URL or API ID.
- Staff cannot create staff, tax rules or discounts where admin control is required.
- Variant price, quantity, discount and tax produce the expected invoice total.
- Expired discounts and exhausted redemption limits cannot apply; retries do not consume another use.
- Running billing twice, including concurrent runs, creates one invoice per period.
- A missed scheduled billing run is caught up correctly; closed/paused subscriptions follow the agreed rules.
- Partial payment leaves a balance; full payment marks Paid; overdue totals match the detail list.
- Catalog updates do not alter existing invoice values.
- Required lifecycle and plan policies work, including close, pause and renewal where permitted.
- Main screens meet the measured response-time target with thousands of seeded subscriptions.
- A fresh setup works from the README; deployed demo works after a restart.

## Suggested five-minute demo

1. Explain the spreadsheet/manual-billing problem and show the dashboard.
2. Admin creates a product variant and recurring plan, then a quotation template.
3. Staff creates a customer quote and activates the subscription.
4. Run due billing, show automatic tax/discount calculation, then rerun to prove no duplicate invoice.
5. Record partial then full payment; show balance and dashboard updates.
6. Sign in as the customer and show their own subscriptions/invoices.
7. Briefly show role restrictions, performance evidence and any honest limitations.

Remaining inputs: preferred stack, event preparation rules and the video's transcript or accessible content. Confirm whether preparation or starter code is permitted before doing implementation ahead of the event. These refine assignments and scope; they do not change the core integration approach.
