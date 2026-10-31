# Reproducible integrated demo

Use README commands with `config.demo_settings`, loopback 8004 and disposable
`test_subscription_demo`. All credentials are generated into ignored
`.local/demo-browser.json`; inspect them privately on your computer. Do not paste
that file into chat, Git or a report. No real password is hardcoded. There are an
application admin, staff, customer A and customer B.

## Seeded reference workflow

`seed_subscription_demo --complete-workflow --browser-credentials` creates an Odoo
service at INR 1,000, Enterprise variant **+560**, monthly fee **100**, product tax
18%, an offer template and two customers' subscriptions. The service starts on
the first of the month two months before the current UTC date; six service periods
are agreed. It issues, accepts and activates quotes through the real services,
then bills the first two completed periods at their controlled due boundaries.
Zero-day payment terms make each invoice due on issue.

Every undiscounted invoice has product 1,560 + tax 280.80 + fee 100 = **1,940.80**.
Customer A's first invoice is fully paid; its second has a 500 payment. Customer
B's first invoice is cancelled unpaid; its second is confirmed unpaid.

Expected global summary in this otherwise empty demo DB:

| Metric | Expected |
|---|---:|
| Active subscriptions | 2 |
| Billed revenue (confirmed + paid) | INR 5,822.40 |
| Payments collected | INR 2,440.80 |
| Outstanding confirmed balance | INR 3,381.60 |
| Customer A's invoices/payments | 2 / 2 |
| Customer B's invoices/payments | 2 / 0 |

Cancelled totals are excluded from billed revenue. Changing invoice-table filters
does not change the explicitly global summary. Overdue counts depend on the
current date; both unpaid confirmed invoices are overdue at the recorded run.
Rerunning the seed does not duplicate these subscriptions, invoices or payments.
Browser interactions remain unverified because the automation policy host could
not establish Chrome's URL. Real HTTP/session/API checks did verify these totals.

## Create the workflow manually

1. Sign in as demo admin at `http://127.0.0.1:8004/login/`. Open
   `/manage/products/`, create a service with sale price 1,000 and internal
   cost/notes. Save; use `/manage/variants/` to add Enterprise with extra 560.
2. In `/manage/tax-rules/`, create an 18% example rule. Sign in as staff to
   demonstrate that tax writes are denied; application admins alone configure it.
3. In `/manage/plans/`, create a monthly plan, recurring fee 100, minimum product
   quantity 1. Enable customer quotation acceptance, pause, renewal and early
   closure for this demonstration. Use dates encompassing the service start.
4. Create a template at `/manage/quotation-templates/`, validity 14 days, with
   that plan, product/variant, quantity 1 and tax. A blank base price uses the
   catalog 1,000; the server snapshots final unit price 1,560.
5. In `/manage/subscriptions/`, create a draft for customer A from the template.
   Choose a start on the first of the preceding month and expiry at a later
   monthly boundary; payment terms 0. Select the template to use its frozen
   product lines. Save, view and click **quote**.
6. Sign in as customer A at `/portal/`, select Subscriptions, inspect the quote
   and click **confirm**. Staff then opens subscription detail and **activate**.
   Catalog edits cannot change the agreement. Invalid transitions return errors.
7. Staff opens `/manage/invoices/` and **Generate due invoices**. Because billing
   is in arrears, the preceding completed period is now due; a start today would
   have no due invoice until its first period ends. Review itemized snapshots and
   use **confirm**, **Print invoice** and **Record payment**.
8. On `/manage/payments/`, record 500 with a date/method/reference, inspect the
   invoice's remaining 1,440.80, then pay that balance. An overpayment or
   cancellation after receiving funds is rejected. Invoice becomes paid.
9. Refresh `/dashboard/` and customer A's `/portal/`; the summary and balances
   come from the same records. Customer B's login cannot view A's subscription,
   invoice or print URL, nor change its owner or prices. Direct URL tests return
   404; global staff list requests return 403 for customers.
10. For policy examples use a second finite subscription: pause, show that due
    billing skips it, resume and inspect the shifted unbilled end; renew before
    expiry without moving billing dates; use early closure after settling arrears.
    Date-boundary and expired-quote cases are covered by controlled automated
    tests; API clients cannot choose their own effective action date.

Generated demo accounts are restricted to the isolated database. Do not copy
demo settings or credentials into a public deployment. SMTP delivery and a
scheduler must be configured and independently verified before claiming either.
