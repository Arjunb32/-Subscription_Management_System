import { ApiError, apiRequest, currentUser, logout } from '/static/accounts/auth-client.js';

const root = document.querySelector('[data-feature-page]');
if (root) {
  const demoAllowed = document.body.dataset.demoMode === 'true';
  const isPortal = root.dataset.featurePage === 'portal';
  const $ = (id) => document.getElementById(id);
  const hide = (id, value = true) => { const node = $(id); if (node) node.hidden = value; };
  const text = (id, value) => { const node = $(id); if (node) node.textContent = value ?? ''; };
  const money = (value) => new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value || 0));
  const date = (value) => value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(`${value}T00:00:00Z`)) : '—';
  const today = new Date().toISOString().slice(0, 10);
  const subscriptions = [
    { customer: 'Northstar Studio', plan: 'Growth', status: 'active', started: '2026-10-02', renewal: '2026-11-02', price: 60 },
    { customer: 'Willow & Co.', plan: 'Starter', status: 'active', started: '2026-10-09', renewal: '2026-11-09', price: 30 },
    { customer: 'Bluebird Labs', plan: 'Scale', status: 'past_due', started: '2026-10-14', renewal: '2026-11-14', price: 120 },
    { customer: 'Northstar Studio', plan: 'Starter', status: 'cancelled', started: '2026-10-19', renewal: '', price: 30 },
  ];
  const demoInvoices = [
    { invoice_number: 'INV-DEMO-1042', customer: 1, customer_email: 'northstar@example.test', issue_date: '2026-10-03', due_date: '2026-10-17', total: '100.00', amount_paid: '100.00', amount_due: '0.00', status: 'paid' },
    { invoice_number: 'INV-DEMO-1043', customer: 2, customer_email: 'bluebird@example.test', issue_date: '2026-10-08', due_date: '2026-10-22', total: '120.00', amount_paid: '50.00', amount_due: '70.00', status: 'confirmed' },
    { invoice_number: 'INV-DEMO-1044', customer: 3, customer_email: 'willow@example.test', issue_date: '2026-10-12', due_date: '2026-10-26', total: '90.00', amount_paid: '0.00', amount_due: '0.00', status: 'cancelled' },
    { invoice_number: 'INV-DEMO-1045', customer: 3, customer_email: 'willow@example.test', issue_date: '2026-10-20', due_date: '2026-11-03', total: '70.00', amount_paid: '0.00', amount_due: '70.00', status: 'confirmed' },
  ];
  const demoPayments = [
    { id: 'PAY-DEMO-508', invoice_number: 'INV-DEMO-1042', payment_date: '2026-10-04', amount: '100.00', payment_method: 'bank_transfer' },
    { id: 'PAY-DEMO-509', invoice_number: 'INV-DEMO-1043', payment_date: '2026-10-10', amount: '50.00', payment_method: 'credit_card' },
  ];
  let pageSubs = 1; let pageInvoices = 1; const pageSize = 8;

  function rowsFrom(payload) { return Array.isArray(payload) ? payload : (payload?.results || []); }
  function setRows(id, emptyId, rows, columns, emptyText) {
    const body = $(id); body.replaceChildren();
    rows.forEach((row) => {
      const tr = document.createElement('tr');
      columns.forEach((column) => {
        const td = document.createElement('td'); const value = row[column.key];
        if (column.key === 'status') {
          const badge = document.createElement('span');
          badge.className = `status status-${String(value).replaceAll('_', '-')}`;
          badge.textContent = String(value || 'unknown').replaceAll('_', ' '); td.append(badge);
        } else td.textContent = column.format ? column.format(value, row) : (value ?? '—');
        tr.append(td);
      });
      body.append(tr);
    });
    hide(emptyId, rows.length !== 0);
    const empty = $(emptyId); if (empty) empty.textContent = emptyText;
  }
  function paged(records, page, name) {
    const count = records.length; const pages = Math.max(1, Math.ceil(count / pageSize));
    const safePage = Math.min(page, pages);
    text(`${name}-page-label`, count ? `Page ${safePage} of ${pages} · ${count} records` : '');
    $(`${name}-prev`).disabled = safePage <= 1; $(`${name}-next`).disabled = safePage >= pages;
    return records.slice((safePage - 1) * pageSize, safePage * pageSize);
  }
  function fillCustomerOptions(invoices) {
    const select = $('filter-customer'); if (!select || select.options.length > 1) return;
    const people = new Map(invoices.map((row) => [String(row.customer), row.customer_email || `Customer ${row.customer}`]));
    people.forEach((email, id) => { const option = document.createElement('option'); option.value = id; option.textContent = email; select.append(option); });
  }
  function showDemoBanner(show) { hide('demo-banner', !show); }
  function renderDemoDashboard() {
    const from = $('filter-from').value; const to = $('filter-to').value;
    const customer = $('filter-customer').value; const status = $('filter-status').value;
    const subs = subscriptions.filter((r) => (!from || r.started >= from) && (!to || r.started <= to));
    const filteredInvoices = demoInvoices.filter((r) => (!customer || String(r.customer) === customer) && (!from || r.issue_date >= from) && (!to || r.due_date <= to) && (status === 'overdue' ? r.due_date < today && Number(r.amount_due) > 0 && r.status === 'confirmed' : status === 'confirmed' ? r.status === 'confirmed' : status ? r.status === status : r.status === 'confirmed' && Number(r.amount_due) > 0));
    const subPage = paged(subs, pageSubs, 'subscriptions'); const invoicePage = paged(filteredInvoices, pageInvoices, 'invoices');
    setRows('subscriptions-body', 'subscriptions-empty', subPage, [{ key: 'customer' }, { key: 'plan' }, { key: 'status' }, { key: 'started', format: date }, { key: 'renewal', format: date }], 'No subscriptions match these filters.');
    setRows('invoices-body', 'invoices-empty', invoicePage, [{ key: 'invoice_number' }, { key: 'customer_email' }, { key: 'issue_date', format: date }, { key: 'due_date', format: date }, { key: 'amount_due', format: money }, { key: 'status' }], 'No invoices match these filters.');
    hide('subscriptions-integration'); hide('dashboard-content', false); hide('loading-state');
    text('metric-active', '2'); text('metric-billed', money(290)); text('metric-collected', money(150)); text('metric-outstanding', money(140)); text('metric-overdue', '1');
    text('subscriptions-count', `${subs.length} sample subscriptions`); text('invoices-count', `${filteredInvoices.length} sample invoices`);
    text('performance-note', 'Development fixtures only. No live API or performance claim.'); showDemoBanner(true);
  }
  function renderLiveDashboard(summary, invoices) {
    const rows = rowsFrom(invoices); fillCustomerOptions(rows);
    const visible = paged(rows, pageInvoices, 'invoices');
    setRows('invoices-body', 'invoices-empty', visible, [
      { key: 'invoice_number' }, { key: 'customer_email' }, { key: 'issue_date', format: date }, { key: 'due_date', format: date }, { key: 'amount_due', format: money }, { key: 'status' },
    ], 'No invoices match these filters.');
    setRows('subscriptions-body', 'subscriptions-empty', [], [{ key: 'customer' }], 'No subscriptions are available from the connected API.');
    $('subscriptions-prev').disabled = true; $('subscriptions-next').disabled = true;
    hide('subscriptions-integration', false); hide('dashboard-content', false); hide('loading-state'); showDemoBanner(false);
    text('metric-active', summary.active_subscriptions); text('metric-billed', money(summary.billed_revenue));
    text('metric-collected', money(summary.payments_collected)); text('metric-outstanding', money(summary.total_outstanding)); text('metric-overdue', summary.overdue_invoices);
    text('subscriptions-count', 'Subscription list awaiting Haridev API'); text('invoices-count', `${rows.length} invoices returned by billing API`);
    text('performance-note', 'Invoice pagination in this screen is currently client-side; the billing API contract does not document server-side pagination.');
  }
  function renderDemoPortal() {
    const mine = subscriptions.filter((r) => r.customer === 'Northstar Studio');
    setRows('portal-subscriptions-body', 'portal-subscriptions-empty', mine, [{ key: 'plan' }, { key: 'status' }, { key: 'started', format: date }, { key: 'renewal', format: date }, { key: 'price', format: money }], 'No subscriptions to show.');
    const mineInvoices = demoInvoices.filter((r) => r.customer_email === 'northstar@example.test');
    setRows('portal-invoices-body', 'portal-invoices-empty', mineInvoices, [{ key: 'invoice_number' }, { key: 'issue_date', format: date }, { key: 'total', format: money }, { key: 'amount_paid', format: money }, { key: 'amount_due', format: money }, { key: 'status' }], 'No invoices to show.');
    setRows('portal-payments-body', 'portal-payments-empty', demoPayments.filter((r) => r.invoice_number === 'INV-DEMO-1042'), [{ key: 'id' }, { key: 'payment_date', format: date }, { key: 'invoice_number' }, { key: 'amount', format: money }, { key: 'payment_method' }], 'No payments to show.');
    text('portal-customer-name', 'Example customer'); text('portal-customer-email', 'Not linked to your signed-in account');
    hide('portal-subscriptions-integration'); hide('portal-content', false); hide('loading-state'); showDemoBanner(true);
  }
  function renderLivePortal(user, invoicePayload, paymentPayload) {
    const invoices = rowsFrom(invoicePayload); const payments = rowsFrom(paymentPayload);
    setRows('portal-invoices-body', 'portal-invoices-empty', invoices, [{ key: 'invoice_number' }, { key: 'issue_date', format: date }, { key: 'total', format: money }, { key: 'amount_paid', format: money }, { key: 'amount_due', format: money }, { key: 'status' }], 'No invoices to show.');
    setRows('portal-payments-body', 'portal-payments-empty', payments, [{ key: 'id' }, { key: 'payment_date', format: date }, { key: 'invoice_number' }, { key: 'amount', format: money }, { key: 'payment_method' }], 'No payments to show.');
    setRows('portal-subscriptions-body', 'portal-subscriptions-empty', [], [{ key: 'plan' }], 'No subscriptions are available from the connected API.');
    text('portal-customer-name', 'My account'); text('portal-customer-email', user.email);
    hide('portal-subscriptions-integration', false); hide('portal-content', false); hide('loading-state'); showDemoBanner(false);
  }
  function showError(error) {
    hide('loading-state'); hide(isPortal ? 'portal-content' : 'dashboard-content');
    text('error-message', error.message || 'Could not load the page.'); hide('error-state', false);
  }
  function queryInvoiceUrl() {
    const params = new URLSearchParams(); const status = $('filter-status').value;
    const customer = $('filter-customer').value; const from = $('filter-from').value; const to = $('filter-to').value;
    if (customer) params.set('customer', customer);
    if (from) params.set('issue_date_from', from);
    if (to) params.set('due_date_to', to);
    if (status === 'overdue') params.set('overdue', '1'); else if (status) params.set('status', status);
    return `${root.dataset.invoicesUrl}?${params}`;
  }
  async function load() {
    hide('error-state'); hide('integration-state'); hide(isPortal ? 'portal-content' : 'dashboard-content', true); hide('loading-state', false);
    try {
      const user = await currentUser();
      if (user.role !== (isPortal ? 'customer' : 'admin')) throw new Error('This account does not have access to this page.');
      if (isPortal) {
        const [invoices, payments] = await Promise.all([apiRequest(root.dataset.invoicesUrl), apiRequest(root.dataset.paymentsUrl)]);
        renderLivePortal(user, invoices, payments);
      } else {
        const [summary, invoices] = await Promise.all([apiRequest(root.dataset.summaryUrl), apiRequest(queryInvoiceUrl())]);
        renderLiveDashboard(summary, invoices);
      }
    } catch (error) {
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        text('session-message', 'Your session has expired or does not have access. Sign in again to continue.'); hide('session-message', false); hide('loading-state');
      } else if (demoAllowed) {
        isPortal ? renderDemoPortal() : renderDemoDashboard();
        text('integration-state', 'Billing APIs are not available in this development checkout. Showing labeled sample data instead.'); hide('integration-state', false);
      } else if (error instanceof ApiError && error.status === 404) {
        hide('loading-state'); text('integration-state', 'Billing APIs are not available. No sample totals or customer records are being shown.'); hide('integration-state', false);
      } else {
        showError(error);
      }
    }
  }
  $('retry-button')?.addEventListener('click', load);
  $('sign-out')?.addEventListener('click', async () => { try { await logout(); } finally { window.location.assign('/login/'); } });
  if (!isPortal) {
    $('dashboard-filters').addEventListener('submit', async (event) => { event.preventDefault(); pageSubs = 1; pageInvoices = 1; await load(); });
    $('reset-filters').addEventListener('click', async () => { $('dashboard-filters').reset(); pageSubs = 1; pageInvoices = 1; await load(); });
    $('subscriptions-prev').addEventListener('click', () => { pageSubs = Math.max(1, pageSubs - 1); renderDemoDashboard(); });
    $('subscriptions-next').addEventListener('click', () => { pageSubs += 1; renderDemoDashboard(); });
    $('invoices-prev').addEventListener('click', async () => { pageInvoices = Math.max(1, pageInvoices - 1); await load(); });
    $('invoices-next').addEventListener('click', async () => { pageInvoices += 1; await load(); });
  } else {
    document.querySelectorAll('[role="tab"]').forEach((tab) => tab.addEventListener('click', () => {
      document.querySelectorAll('[role="tab"]').forEach((item) => item.setAttribute('aria-selected', String(item === tab)));
      document.querySelectorAll('.portal-tab-panel').forEach((panel) => { panel.hidden = panel.id !== tab.getAttribute('aria-controls'); });
    }));
  }
  load();
}
