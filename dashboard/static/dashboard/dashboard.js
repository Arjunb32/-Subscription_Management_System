import { apiRequest, currentUser, logout } from '/static/accounts/auth-client.js';

const root=document.querySelector('[data-feature-page]');
if(root) {
  const portal=root.dataset.featurePage==='portal';
  const $=id=>document.getElementById(id);
  const text=(id,value)=>{if($(id))$(id).textContent=value??'';};
  const hide=(id,value=true)=>{if($(id))$(id).hidden=value;};
  const money=value=>new Intl.NumberFormat(undefined,{style:'currency',currency:'INR'}).format(Number(value||0));
  const date=value=>value?new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeZone:'UTC'}).format(new Date(`${value}T00:00:00Z`)):'—';
  const make=(tag,value,props={})=>{const node=document.createElement(tag);if(value!==undefined)node.textContent=value;Object.assign(node,props);return node;};
  const state={};
  function error(error) {
    hide('loading-state');
    if(error.status===401||error.status===403) {text('session-message','Your session expired or access was denied. Sign in at /login/ to continue.');hide('session-message',false);}
    else {text('error-message',error.errors?JSON.stringify(error.errors):error.message||'Could not load live data.');hide('error-state',false);}
  }
  function renderTable(id,rows,columns,actions) {
    const body=$(id);body.replaceChildren();
    for(const row of rows) {
      const tr=make('tr');
      for(const [key,format]of columns) {
        const td=make('td');
        if(key==='plan_name') {
          const button=make('button',row.plan_name,{type:'button',className:'text-button'});
          button.addEventListener('click',()=>details(row));td.append(button);
        } else if(key==='invoice_number') {
          const link=make('a',row.invoice_number,{href:`/api/billing/invoices/${row.id}/print/`,target:'_blank',rel:'noopener'});td.append(link);
        } else if(key==='status')td.append(make('span',row.status,{className:`status status-${row.status}`}));
        else td.textContent=format?format(row[key]):row[key]??'—';
        tr.append(td);
      }
      if(actions) {
        const td=make('td');
        for(const action of row.permitted_actions) {
          const button=make('button',action,{type:'button',className:'text-button'});
          button.addEventListener('click',async()=>{const label=button.textContent;button.disabled=true;button.textContent='Working…';if(portal){text('portal-action-status',`Updating subscription (${action})…`);hide('portal-action-status',false);}try{await apiRequest(`${root.dataset.subscriptionsUrl}${row.id}/actions/${action}/`,{method:'POST',data:{}});if(portal)text('portal-action-status',`Subscription updated successfully (${action}).`);await load();}catch(exc){if(portal)hide('portal-action-status');error(exc);button.disabled=false;button.textContent=label;}});td.append(button);
        }tr.append(td);
      }body.append(tr);
    }
  }
  function details(row) {
    let box=$('subscription-detail');
    if(!box){box=make('section',undefined,{id:'subscription-detail',className:'panel'});$(portal?'portal-content':'dashboard-content').append(box);}
    box.replaceChildren(make('h2',row.subscription_number),make('p',`${row.plan_name} · ${row.status} · ${money(row.price)} per period · billing in arrears`));
    const list=make('ul');row.lines.forEach(line=>list.append(make('li',`${line.description}: ${line.quantity} × ${money(line.unit_price)} + ${line.tax_rate}% tax`)));box.append(list);
    if(!portal)box.append(make('a','Manage subscription',{href:`/manage/subscriptions/?id=${row.id}`}));
    box.scrollIntoView({behavior:'smooth'});
  }
  const subColumns=[['plan_name'],['status'],['start_date',date],['renewal_date',date],['price',money]];
  const invoiceColumns=portal?[['invoice_number'],['issue_date',date],['total',money],['amount_paid',money],['amount_due',money],['status']]:[['invoice_number'],['customer_email'],['issue_date',date],['due_date',date],['amount_due',money],['status']];
  const paymentColumns=[['id'],['payment_date',date],['invoice_number'],['amount',money],['payment_method']];
  function bindPage(name,payload,render) {
    state[name]={payload,render};
    text(`${name}-page-label`,`${payload.count} records · server pagination`);
    $(`${name}-prev`).disabled=!payload.previous;$(`${name}-next`).disabled=!payload.next;
    for(const [suffix,key]of [['prev','previous'],['next','next']])$(`${name}-${suffix}`).onclick=async()=>{try{hide('error-state');const next=await apiRequest(state[name].payload[key]);render(next);}catch(exc){error(exc);}};
  }
  function subscriptions(payload) {
    const name=portal?'portal-subscriptions':'subscriptions';
    renderTable(`${name}-body`,payload.results,portal?subColumns:[['customer_display'],['plan_name'],['status'],['start_date',date],['renewal_date',date]],portal);
    hide(`${name}-empty`,payload.results.length!==0);text('subscriptions-count',`${payload.count} subscriptions`);
    bindPage(name,payload,subscriptions);hide(`${name}-integration`);
  }
  function invoices(payload) {
    const name=portal?'portal-invoices':'invoices';renderTable(`${name}-body`,payload.results,invoiceColumns);
    hide(`${name}-empty`,payload.results.length!==0);text('invoices-count',`${payload.count} invoices`);bindPage(name,payload,invoices);
  }
  function payments(payload) {renderTable('portal-payments-body',payload.results,paymentColumns);hide('portal-payments-empty',payload.results.length!==0);bindPage('portal-payments',payload,payments);}
  async function load() {
    hide('error-state');hide('session-message');hide('loading-state',false);hide(portal?'portal-content':'dashboard-content');
    try {
      const user=await currentUser();
      if(portal) {
        const [subs,inv,pay]=await Promise.all([apiRequest(root.dataset.subscriptionsUrl),apiRequest(root.dataset.invoicesUrl),apiRequest(root.dataset.paymentsUrl)]);
        subscriptions(subs);invoices(inv);payments(pay);text('portal-customer-name','My account');text('portal-customer-email',user.email);
      } else {
        const query=new URLSearchParams(new FormData($('dashboard-filters')));for(const[key,value]of [...query])if(!value)query.delete(key);
        if(query.get('status')==='overdue'){query.delete('status');query.set('overdue','1');}
        const subQuery=new URLSearchParams();if(query.get('customer'))subQuery.set('customer',query.get('customer'));
        if($('subscription-status').value)subQuery.set('status',$('subscription-status').value);
        const [summary,subs,inv]=await Promise.all([apiRequest(root.dataset.summaryUrl),apiRequest(`${root.dataset.subscriptionsUrl}?${subQuery}`),apiRequest(`${root.dataset.invoicesUrl}?${query}`)]);
        subscriptions(subs);invoices(inv);
        for(const[id,key,format]of [['metric-active','active_subscriptions'],['metric-billed','billed_revenue',money],['metric-collected','payments_collected',money],['metric-outstanding','total_outstanding',money],['metric-overdue','overdue_invoices']])text(id,format?format(summary[key]):summary[key]);
      }
      hide(portal?'portal-content':'dashboard-content',false);hide('loading-state');
    }catch(exc){error(exc);}
  }
  $('retry-button')?.addEventListener('click',load);
  $('sign-out')?.addEventListener('click',async()=>{try{await logout();location.assign('/login/');}catch(exc){error(exc);}});
  if(!portal) {
    $('dashboard-filters').addEventListener('submit',event=>{event.preventDefault();load();});
    $('reset-filters').addEventListener('click',()=>{$('dashboard-filters').reset();$('subscription-status').value='';load();});
    $('subscription-status').addEventListener('change',load);
    try {const data=await apiRequest('/api/customers/?page_size=100');data.results.forEach(customer=>$('filter-customer').append(make('option',customer.email,{value:String(customer.id)})));}catch(exc){error(exc);}
  } else document.querySelectorAll('[role=tab]').forEach(tab=>tab.addEventListener('click',()=>{document.querySelectorAll('[role=tab]').forEach(item=>item.setAttribute('aria-selected',String(item===tab)));document.querySelectorAll('.portal-tab-panel').forEach(panel=>{panel.hidden=panel.id!==tab.getAttribute('aria-controls');});}));
  await load();
}
