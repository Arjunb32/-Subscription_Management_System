# Catalog and subscription API contract

All URLs have trailing slashes. JSON requests and responses, integer IDs, ISO
`YYYY-MM-DD` dates, UTC date boundaries, exact decimal strings with two decimal
places. Currency is **INR** throughout this application; there is no conversion
or multi-currency accounting. Reuse `/static/accounts/auth-client.js`: session
cookies and `X-CSRFToken` on writes, refreshed after login. No browser-supplied
customer ID establishes access to a customer endpoint.

## Permissions and routes

| Resource | Collection URL | Methods and permission |
|---|---|---|
| Products | `/api/catalog/products/` | Staff/admin GET, POST; GET, PUT, PATCH, DELETE at `{id}/` |
| Variants | `/api/catalog/variants/` | Staff/admin, same methods |
| Plans | `/api/plans/` | Staff/admin, same methods |
| Tax rules | `/api/tax-rules/` | Staff/admin read; **application admin only** creates, edits, deletes |
| Quotation templates | `/api/quotation-templates/` | Staff/admin, same methods; nested lines replace atomically |
| Subscriptions | `/api/subscriptions/` | Staff/admin GET, POST; GET, PUT, PATCH at `{id}/`; drafts alone can be edited; no DELETE |
| Current customer's subscriptions | `/api/my/subscriptions/` | Customer role only GET; own `{id}/` GET and permitted actions |
| Active customer choices | `/api/customers/` | Staff/admin GET, including `{id}/`; only ID/email/display names |

Subscription detail at `/api/subscriptions/{id}/` also permits its customer to
read it. The global collection remains staff/admin only. The `/my/` collection
and detail filter by the session owner before filtering, counting or pagination;
staff/admin use the global endpoints. Customers cannot create, edit, reassign
or delete subscriptions, choose other related IDs, set prices or configure tax.
No internal product costs/notes are in subscription responses. Invoice notes and
staff payment notes/identity are omitted from customer JSON responses.

All collections return `{ "count": 42, "next": "http://.../?page=2",
"previous": null, "results": [...] }`. Default `page_size=20`, maximum 100,
`page=1` based. Follow next/previous links through the same-origin client. Invalid
pages return 404. Stable ordering uses IDs to break catalog name ties and newest
subscription ID first. Related objects and lines are loaded in bounded queries.

Filters:

- Catalog resources: `search` by name, `is_active=true|false`.
- Variants additionally: `product=<integer ID>`; variants cannot move products.
- Customers: `search` by email; only active customer accounts are choices.
- Subscriptions: `status`, `customer`, `plan`, `search` (number/customer email/
  plan name), `start_date_from`, `start_date_to` inclusive. Customer filters can
  narrow their own scope but never expand it.
- Billing lists now use the same pagination envelope. Invoice filters: `status`,
  `customer`, `subscription`, `search` (invoice/customer), `issue_date_from`,
  `due_date_to`, `overdue=true|1`. Payment filters: `invoice`, `payment_method`,
  `date_from`, `date_to`, `search` by invoice number. Billing customer lists are
  scoped before pagination. The financial summary remains global/unfiltered.

## Pricing and snapshots

Plan `price` is a separate recurring fee, added **once** using one automatically
maintained `SubscriptionLine.is_plan_fee=true`, quantity 1. Its system product is
excluded from editable product lists. All other lines are product charges.
The plan fee has zero tax by default. Product-line taxes come from their selected
tax rule; configure a separate taxed catalog service if required by the agreed
business arrangement. This is a demo accounting policy, not jurisdiction-specific
tax advice. Plan minimum quantity is the **sum of product-line quantities**;
the fee does not satisfy it. Positive fractional quantities are supported.
The fee also does not satisfy discount minimum product-quantity thresholds.

For line input, omit `base_unit_price` to use product `sales_price`, or provide a
staff-negotiated base. Server adds the selected variant's `price_extra` once.
Output `unit_price` **already includes the variant adjustment and excludes tax**.
Do not submit `unit_price`, `tax_rate`, `description`, IDs, amounts or fee flags
as editable line fields. Unit price and quantity have two decimal places.
`ROUND_HALF_UP` rounds each extended line and tax to INR 0.01. The supported
per-period gross is at most INR 99,999,999.99; quotation issue rejects overflow.

Template lines snapshot price, description and tax rate when saved. A subscription
created from a template copies those line values. The draft snapshots the chosen
plan's price, recurrence, minimum and policy flags when saved. Saving a draft
again refreshes its plan snapshot; explicitly replacing product lines reprices
those lines. Once issued as a quotation, customer, dates, lines, plan pricing and
policies cannot be generically edited. Subsequent catalog/plan/tax/template edits
do not change the agreement or invoice values. Plan display names remain the
current catalog name; fee and product descriptions preserve their quoted text.

`subtotal` includes the fee plus product extensions before tax. `price` adds the
snapshotted product tax, before invoice discounts. Actual invoice discounts and
totals are calculated only by billing. These are per-service-period amounts,
not a prediction of discounted revenue or an MRR calculation.

## Requests and responses

Staff creates a product and variant:

```json
POST /api/catalog/products/
{"name":"Odoo license","product_type":"service","sales_price":"1000.00","cost_price":"400.00","notes":"Internal note","is_active":true}

POST /api/catalog/variants/
{"product":1,"name":"Enterprise","values":{"edition":"Enterprise"},"price_extra":"560.00","is_active":true}
```

Admin tax and staff plan/template (IDs are illustrative):

```json
POST /api/tax-rules/
{"name":"GST example","rate":"18.00","is_active":true}

POST /api/plans/
{"name":"Monthly support","price":"100.00","billing_interval":"monthly","min_quantity":"1.00","available_from":null,"available_until":null,"allow_customer_accept":true,"allow_pause":true,"allow_renewal":true,"allow_early_close":true,"auto_close":true,"is_active":true}

POST /api/quotation-templates/
{"name":"Enterprise offer","plan":1,"validity_days":14,"is_active":true,"lines":[{"product":1,"product_variant":1,"quantity":"1.00","tax_rule":1}]}

POST /api/subscriptions/
{"customer":3,"template":1,"start_date":"2026-10-01","expiry_date":"2027-01-01","payment_terms_days":0}
```

Alternatively create a draft with `plan`, `lines`, `validity_days`; do not combine
custom lines with a template. A plan or template and an active customer/start date
are required. Payment terms range from 0 to 365 days (zero means due on issue).
Quotation/template validity is 1–365 days, default 14. Product quantities default
to `1.00` if omitted. Up to 100 product lines per request. `PATCH` may omit scalar
fields; supplying `lines` replaces the whole product-line list, not individual
line IDs. Deleting referenced catalog records returns 400; archive using
`{"is_active":false}`. Archived selections cannot be used for new lines/plans.

Successful subscription create returns 201; detail/update/action returns 200:

```json
{
  "id":12,"subscription_number":"SUB-<32 uppercase hex characters>",
  "customer":3,"customer_email":"customer@example.test",
  "customer_display":"customer@example.test","plan":1,"plan_name":"Monthly support",
  "template":1,"status":"draft","start_date":"2026-10-01","expiry_date":"2027-01-01",
  "current_period_start":"2026-10-01","current_period_end":"2026-11-01",
  "renewal_date":"2026-11-01","payment_terms_days":0,"validity_days":14,
  "quotation_valid_until":null,"plan_price":"100.00","billing_interval":"monthly",
  "paused_on":null,"pause_reason":"","currency":"INR","subtotal":"1660.00",
  "price":"1940.80","permitted_actions":["quote"],
  "lines":[
    {"id":21,"product":1,"product_variant":1,"quantity":"1.00","unit_price":"1560.00","tax_rule":1,"tax_rate":"18.00","description":"Odoo license (Enterprise)","amount":"1560.00","tax_amount":"280.80","is_plan_fee":false},
    {"id":22,"product":2,"product_variant":null,"quantity":"1.00","unit_price":"100.00","tax_rule":null,"tax_rate":"0.00","description":"Plan fee: Monthly support","amount":"100.00","tax_amount":"0.00","is_plan_fee":true}
  ]
}
```

## Lifecycle actions and dates

`POST /api/subscriptions/{id}/actions/{action}/` with `{}`. Customers may also use
`POST /api/my/subscriptions/{id}/actions/{action}/`. Actions reject extra fields;
effective dates come from the server. `permitted_actions` is the authoritative UI
contract and server authorization is repeated while locking the subscription.

| Action | From → to | Required policy/role |
|---|---|---|
| `quote` | draft → quotation | Staff/admin; valid lines, minimum, active/available plan and cycle dates |
| `confirm` | quotation → confirmed | Staff/admin or owner with snapshotted `allow_customer_accept`; quote not expired |
| `activate` | confirmed → active | Staff/admin; valid lines/dates; service started and not expired |
| `pause` | active → paused | `allow_pause`; staff/admin or owner |
| `resume` | manually paused → active | `allow_pause`; staff/admin or owner |
| `renew` | active/expiry-paused → active | `allow_renewal`, finite expiry, not manually paused; no retroactive renewal after expiry |
| `close` | active/paused → closed | `allow_early_close`; staff/admin or owner |

Closed is terminal; create a new quotation for later service. All optional
self-service/pause/renew/early-close policies default false. Automatic closure
defaults true. Quotations remain acceptable through `quotation_valid_until`
inclusive; acceptance after it is rejected. A confirmed agreement can activate
after the quotation's acceptance deadline if its service is still valid.

Start availability is inclusive; the plan availability window is checked when
issuing the quotation against its service start. Existing accepted agreements
honor snapshots even if the catalog plan is later archived. Initial expiry must
equal a repeated full recurrence boundary, at most 100 years out; no automatic
partial-period pricing is inferred. Monthly/yearly addition clamps the day:
Jan 31 → Feb 28 → Mar 28; leap years use Feb 29. This deliberately preserves the
published billing engine's clamping convention, not an independent billing date.

`current_period_end` is the only next billing boundary; `renewal_date` is a
read-only alias, **not a second schedule field**. Billing is in arrears: it
invoices `[current_period_start,current_period_end)` once the end is due, then
advances the dates exactly once. Renewal extends expiry by one recurrence,
without moving billing dates or repricing. At expiry, billing finishes the last
complete due period, then closes if `auto_close=true`; otherwise it sets
`paused`/`pause_reason="expiry"` and stops charging pending renewal. Run billing
at expiry to apply this policy; no deployed scheduler is implied.

Pause first settles completed due periods transactionally. A manual pause is an
auxiliary state that billing skips. Resume adds paused days to the unbilled end
date, and recomputes expiry from that boundary preserving the number of remaining
whole periods. The invoice range may span the pause, but the customer receives a
full period of active service for the unchanged charge; paused days do not add a
charge. Already invoiced dates never move. Early closure settles completed
periods and waives the unfinished period; no proration/refund is implemented.

Catch-up is limited to 36 periods per subscription per billing run. Repeat until
`remaining_due_subscriptions=0`. Pause/close refuse and roll back if more periods
must be settled; run catch-up first. Billing and actions lock the same parent row.

## Errors

400: field errors or invalid transition, e.g.
`{"product_variant":["Choose an active variant of the selected product."]}`;
unknown/read-only fields are rejected on catalog/subscription writes.
403: absent/expired session, CSRF failure or role denial (DRF session auth).
404: missing or another customer's object, invalid page. Financial/billing
validation follows the same error conventions. Data/network failures are shown
as failures; dashboard pagination never substitutes sample records or totals.

Management pages: `/manage/products/`, `/manage/variants/`, `/manage/plans/`,
`/manage/tax-rules/`, `/manage/quotation-templates/`, `/manage/subscriptions/`.
Invoice/payment/discount pages use `/manage/invoices/`, `/manage/payments/`,
`/manage/discounts/`. Staff overview `/dashboard/`; customer workspace `/portal/`.
