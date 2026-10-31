import { apiRequest, logout } from '/static/accounts/auth-client.js';

const $ = id => document.getElementById(id);
const section = document.body.dataset.section;
const role = document.body.dataset.role;
const endpoints = {products:'/api/catalog/products/', variants:'/api/catalog/variants/', plans:'/api/plans/', 'tax-rules':'/api/tax-rules/', 'quotation-templates':'/api/quotation-templates/', subscriptions:'/api/subscriptions/', invoices:'/api/billing/invoices/', payments:'/api/billing/payments/', discounts:'/api/billing/discounts/'};
const endpoint = endpoints[section];
const definitions = {
  products: [['name','Name','text',true],['product_type','Product type','text',true],['sales_price','Sales price (INR)','money',true],['cost_price','Internal cost price (INR)','money',true],['notes','Internal notes','textarea'],['is_active','Active','checkbox']],
  variants: [['product','Product','products',true],['name','Variant name','text',true],['values','Descriptive values (JSON)','json'],['price_extra','Additional price (INR)','money',true],['is_active','Active','checkbox']],
  plans: [['name','Plan name','text',true],['price','Recurring plan fee (INR)','money',true],['billing_interval','Billing interval','daily|weekly|monthly|yearly',true],['min_quantity','Minimum total product quantity','quantity',true],['available_from','Available from','date'],['available_until','Available through','date'],['allow_customer_accept','Customer may accept quotations','checkbox'],['allow_pause','Allow pause and resume','checkbox'],['allow_renewal','Allow renewal','checkbox'],['allow_early_close','Allow early closure','checkbox'],['auto_close','Automatically close at expiry','checkbox'],['is_active','Active','checkbox']],
  'tax-rules': [['name','Tax name','text',true],['rate','Percentage (0–100)','money',true],['is_active','Active','checkbox']],
  'quotation-templates': [['name','Template name','text',true],['plan','Plan','plans',true],['validity_days','Quotation validity (days)','number',true],['is_active','Active','checkbox']],
  subscriptions: [['customer','Customer','customers',true],['template','Quotation template (optional)','quotation-templates'],['plan','Plan (required without template)','plans'],['start_date','Service start','date',true],['expiry_date','Expiry (exclusive cycle boundary)','date'],['payment_terms_days','Payment terms (days, 0 allowed)','number',true],['validity_days','Quotation validity (days)','number',true]],
  payments: [['invoice','Confirmed invoice','invoices',true],['amount','Payment amount (INR)','money',true],['payment_method','Payment method','bank_transfer|credit_card|cash|cheque|other',true],['payment_date','Payment date','date',true],['reference','Reference','text'],['note','Note','textarea']],
  discounts: [['name','Discount name','text',true],['discount_type','Type','fixed|percentage',true],['value','Value','money',true],['min_purchase','Minimum purchase (optional)','money'],['min_quantity','Minimum quantity (optional)','number'],['start_date','Valid from','date',true],['end_date','Valid through','date'],['max_uses','Maximum uses (optional)','number'],['applies_to','Scope','subscription|product',true],['products','Product IDs for product scope (comma separated)','ids'],['is_active','Active','checkbox']],
};
const defaults = {product_type:'service',sales_price:'0.00',cost_price:'0.00',price:'0.00',price_extra:'560.00',rate:'18.00',min_quantity:'1.00',billing_interval:'monthly',validity_days:14,payment_terms_days:30,quantity:'1.00',is_active:true,auto_close:true,values:{},start_date:new Date().toISOString().slice(0,10),payment_date:new Date().toISOString().slice(0,10)};
let payload, editingId = null, pageUrl = endpoint;
const lookups = new Map();

function el(tag, text, props={}) { const node=document.createElement(tag); if(text!==undefined) node.textContent=text; Object.assign(node,props); return node; }
function message(text, error=false) { $('feedback').textContent=text; $('feedback').className=error?'error':''; $('feedback').hidden=false; }
function errorMessage(error) {
  if(error.status===403) return 'Your session expired or this action is not permitted. Sign in again at /login/ if needed.';
  return error.errors ? JSON.stringify(error.errors,null,2) : error.message;
}
function labelFor(row) {return row.name || row.invoice_number || row.email || `#${row.id}`;}
async function choices(type, selected) {
  const url=type==='customers'?'/api/customers/':endpoints[type];
  if(!lookups.has(url)) lookups.set(url, (await apiRequest(`${url}?page_size=100`)).results);
  const rows=[...lookups.get(url)];
  if(selected && !rows.some(row=>String(row.id)===String(selected))) {
    try {rows.push(await apiRequest(`${url}${selected}/`));} catch { /* An invalid stored choice remains visibly unavailable. */ }
  }
  return rows;
}
async function makeField([name,label,type,required],value, prefix='') {
  const wrapper=el('label',label); let input;
  if(endpoints[type] || type==='customers') {
    input=el('select'); input.append(el('option','Choose…',{value:''}));
    const rows=await choices(type,value);
    rows.forEach(row=>input.append(el('option',labelFor(row),{value:String(row.id)})));
    // A search box keeps large related-object catalogs usable without loading every page.
    const search=el('input',undefined,{type:'search',placeholder:'Search choices',ariaLabel:`Search ${label}`});
    let timer;
    search.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(async()=>{try{
      const url=type==='customers'?'/api/customers/':endpoints[type];
      const result=await apiRequest(`${url}?search=${encodeURIComponent(search.value)}&page_size=100`);
      input.replaceChildren(el('option','Choose…',{value:''}));
      result.results.forEach(row=>input.append(el('option',labelFor(row),{value:String(row.id)})));
    }catch(error){message(errorMessage(error),true);}},250);});
    wrapper.append(search);
  } else if(type.includes('|')) {
    input=el('select');type.split('|').forEach(item=>input.append(el('option',item.replaceAll('_',' '),{value:item})));
  } else if(type==='textarea'||type==='json') input=el('textarea');
  else {input=el('input',undefined,{type:['money','quantity','number'].includes(type)?'number':type==='ids'?'text':type});}
  input.name=prefix+name; input.dataset.kind=type; input.required=!!required;
  if(type==='checkbox') input.checked=!!value;
  else input.value=type==='json'?JSON.stringify(value||{}):type==='ids'?(value||[]).join(','):(value??'');
  if(['money','quantity','number'].includes(type)){input.min=type==='quantity'?'0.01':'0';input.step=type==='number'?'1':'0.01';}
  if(name==='rate') input.max='100';
  wrapper.append(input);return wrapper;
}
function readFields(container) {
  const data={};
  container.querySelectorAll('[name]').forEach(input=>{
    const type=input.dataset.kind; let value=input.type==='checkbox'?input.checked:input.value;
    if(type==='json') value=JSON.parse(value||'{}');
    else if(type==='ids') value=value?value.split(',').map(item=>Number(item.trim())):[];
    else if(type==='number'||endpoints[type]||type==='customers') value=value===''?null:Number(value);
    else if(value==='') {if(type==='date'||type==='money')value=null;}
    data[input.name]=value;
  }); return data;
}
async function addLine(value={}) {
  const container=el('div',undefined,{className:'line'});
  const fields=[['product','Product','products',true],['product_variant','Variant (optional)','variants'],['quantity','Quantity','quantity',true],['base_unit_price','Base unit price (INR)','money'],['tax_rule','Tax rule (optional)','tax-rules']];
  const variantRows=await choices('variants',value.product_variant);
  const adjustment=variantRows.find(row=>row.id===value.product_variant)?.price_extra||0;
  const data={quantity:'1.00',...value,base_unit_price:value.unit_price===undefined?'':(Number(value.unit_price)-Number(adjustment)).toFixed(2)};
  for(const field of fields)container.append(await makeField(field,data[field[0]]));
  const product=container.querySelector('[name=product]'), variant=container.querySelector('[name=product_variant]');
  async function filterVariants(reset) {
    const rows=product.value?(await apiRequest(`/api/catalog/variants/?product=${product.value}&page_size=100`)).results:[];
    const selected=reset?'':variant.value;variant.replaceChildren(el('option','None',{value:''}));
    rows.filter(row=>row.is_active).forEach(row=>variant.append(el('option',`${row.name} (+${row.price_extra})`,{value:String(row.id)})));variant.value=selected;
  }
  product.addEventListener('change',async()=>{try{await filterVariants(true);container.querySelector('[name=base_unit_price]').value='';}catch(error){message(errorMessage(error),true);}});
  const remove=el('button','Remove line',{type:'button'});remove.addEventListener('click',()=>container.remove());container.append(remove);$('lines').append(container);
  await filterVariants(false);
}
async function edit(record=null) {
  try {
    editingId=record?.id||null;$('fields').replaceChildren();$('lines').replaceChildren();
    $('editor-title').textContent=`${record?'Edit draft / record':'Create'} · ${section}`;
    const values={...defaults,...record};
    for(const definition of definitions[section]||[])$('fields').append(await makeField(definition,values[definition[0]]));
    const hasLines=['quotation-templates','subscriptions'].includes(section);
    $('line-section').hidden=!hasLines;
    if(hasLines)for(const line of record?.lines?.filter(row=>!row.is_plan_fee)||[{}])await addLine(line);
    if(section==='subscriptions') {
      const template=$('fields').querySelector('[name=template]');
      const applyTemplate=async()=>{
        const selected=Boolean(template.value);
        $('line-section').hidden=selected;
        $('line-section').querySelectorAll('input,select,textarea,button').forEach(input=>{input.disabled=selected;});
        if(selected) {
          try {const chosen=await apiRequest(`${endpoints['quotation-templates']}${template.value}/`);$('fields').querySelector('[name=plan]').value=chosen.plan;$('fields').querySelector('[name=validity_days]').value=chosen.validity_days;}
          catch(error){message(errorMessage(error),true);}
        }
      };
      template.addEventListener('change',applyTemplate);await applyTemplate();
    }
    $('form-note').textContent=section==='subscriptions'?'Save creates a draft. Issue quotation, confirm and activate using the detail actions. A template supplies its own product lines; leave the editor lines unused when selecting one. Only drafts can be edited.':section==='plans'?'The recurring fee is billed once in addition to product lines. Policies are snapshotted when the subscription draft is saved.':'';
    $('editor').hidden=false;$('editor').scrollIntoView({behavior:'smooth'});
  }catch(error){message(errorMessage(error),true);}
}
async function load(url=pageUrl) {
  pageUrl=url;$('loading').hidden=false;$('records').replaceChildren();
  try {
    payload=await apiRequest(url);const rows=payload.results;
    const cols=section==='subscriptions'?['subscription_number','customer_email','plan_name','status','renewal_date','price']:section==='invoices'?['invoice_number','customer_email','due_date','total','amount_paid','amount_due','status']:section==='payments'?['id','invoice_number','payment_date','amount','payment_method']:section==='products'?['name','product_type','sales_price','is_active']:section==='variants'?['product_name','name','price_extra','is_active']:section==='plans'?['name','price','billing_interval','min_quantity','is_active']:section==='tax-rules'?['name','rate','is_active']:['name','id','is_active'];
    const head=el('tr');cols.forEach(col=>head.append(el('th',col.replaceAll('_',' '))));head.append(el('th','Actions'));$('table-head').replaceChildren(head);
    rows.forEach(row=>{const tr=el('tr');cols.forEach(col=>tr.append(el('td',row[col]??'—')));const actions=el('td');
      const view=el('button','View',{type:'button'});view.addEventListener('click',()=>detail(row.id));actions.append(view);
      if(definitions[section]&&section!=='payments'&&(section!=='subscriptions'||row.status==='draft')&&(!['tax-rules','discounts'].includes(section)||role==='admin')) {
        const button=el('button','Edit',{type:'button'});button.addEventListener('click',async()=>{try{await edit(await apiRequest(`${endpoint}${row.id}/`));}catch(error){message(errorMessage(error),true);}});actions.append(button);
      } tr.append(actions);$('records').append(tr);
    });
    $('empty').hidden=rows.length!==0;$('prev').disabled=!payload.previous;$('next').disabled=!payload.next;
    $('page-info').textContent=`${payload.count} records · server pagination`;
  }catch(error){message(errorMessage(error),true);}finally{$('loading').hidden=true;}
}
async function perform(url, data={}) {
  try {await apiRequest(url,{method:'POST',data});message('Action completed.');lookups.clear();await load();return true;}
  catch(error){message(errorMessage(error),true);return false;}
}
async function detail(id) {
  try {
    const row=await apiRequest(`${endpoint}${id}/`);const box=$('detail');box.replaceChildren(el('h2',row.subscription_number||labelFor(row)));
    const list=el('dl');Object.entries(row).filter(([,value])=>value===null||typeof value!=='object').forEach(([key,value])=>{list.append(el('dt',key.replaceAll('_',' ')),el('dd',value??'—'));});box.append(list);
    if(row.lines) {
      const wrap=el('div',undefined,{className:'table-wrap'}), table=el('table'), head=el('tr');
      ['Description','Quantity','Unit price','Tax %','Amount'].forEach(value=>head.append(el('th',value)));table.append(head);
      row.lines.forEach(line=>{const tr=el('tr');[line.description||line.product_name,line.quantity,line.unit_price,line.tax_rate,line.amount||line.line_total].forEach(value=>tr.append(el('td',value)));table.append(tr);});wrap.append(table);box.append(wrap);
    }
    const toolbar=el('div',undefined,{className:'toolbar'});
    if(section==='subscriptions') {
      row.permitted_actions.forEach(action=>{const button=el('button',action,{type:'button'});button.addEventListener('click',async()=>{button.disabled=true;if(await perform(`${endpoint}${id}/actions/${action}/`))await detail(id);else button.disabled=false;});toolbar.append(button);});
      toolbar.append(el('a','View invoices',{href:`/manage/invoices/?subscription=${id}`}));
    } else if(section==='invoices') {
      for(const action of ['confirm','cancel','send']) {
        if(action==='confirm'&&row.status!=='draft')continue;if(action==='send'&&!['confirmed','paid'].includes(row.status))continue;if(action==='cancel'&&(!['draft','confirmed'].includes(row.status)||Number(row.amount_paid)>0))continue;
        const button=el('button',action,{type:'button'});button.addEventListener('click',async()=>{button.disabled=true;if(await perform(`${endpoint}${id}/${action}/`))await detail(id);else button.disabled=false;});toolbar.append(button);
      }
      toolbar.append(el('a','Print invoice',{href:`${endpoint}${id}/print/`,target:'_blank',rel:'noopener'}));
      toolbar.append(el('a','Record payment',{href:`/manage/payments/?invoice=${id}`}));
      box.append(el('p','Send uses the configured Django email backend. Console output does not deliver to an inbox.'));
    }
    box.append(toolbar);box.hidden=false;box.scrollIntoView({behavior:'smooth'});
  }catch(error){message(errorMessage(error),true);}
}
$('record-form').addEventListener('submit',async event=>{
  event.preventDefault();$('save').disabled=true;
  try {
    const data=readFields($('fields'));
    if(['quotation-templates','subscriptions'].includes(section)) {
      if(!data.template) data.lines=[...$('lines').children].map(container=>{const value=readFields(container);if(value.base_unit_price===null||value.base_unit_price==='')delete value.base_unit_price;return value;});
      if(!data.plan)delete data.plan;
      if(!data.template)delete data.template;
      if(editingId)delete data.template;
    }
    const result=await apiRequest(`${endpoint}${editingId?`${editingId}/`:''}`,{method:editingId?'PATCH':'POST',data});
    $('editor').hidden=true;lookups.clear();message('Saved successfully.');await load();await detail(result.id);
  }catch(error){message(errorMessage(error),true);}finally{$('save').disabled=false;}
});
$('add-line').addEventListener('click',()=>addLine().catch(error=>message(errorMessage(error),true)));
$('cancel-edit').addEventListener('click',()=>{$('editor').hidden=true;});
$('new-record').addEventListener('click',()=>edit());
$('refresh').addEventListener('click',()=>load());
$('prev').addEventListener('click',()=>{if(payload.previous)load(payload.previous);});
$('next').addEventListener('click',()=>{if(payload.next)load(payload.next);});
$('filters').addEventListener('submit',event=>{event.preventDefault();const data=new FormData(event.target), query=new URLSearchParams();for(const [key,value]of data)if(value)query.set(key,value);load(`${endpoint}?${query}`);});
$('sign-out').addEventListener('click',async()=>{try{await logout();window.location.assign('/login/');}catch(error){message(errorMessage(error),true);}});
$('generate').hidden=section!=='invoices';$('generate').addEventListener('click',async()=>{const button=$('generate');button.disabled=true;try{await perform('/api/billing/invoices/generate/');}finally{button.disabled=false;}});
$('status-filter').hidden=section!=='subscriptions';
$('new-record').hidden=!definitions[section]||(['tax-rules','discounts'].includes(section)&&role!=='admin');
$('description').textContent=section==='subscriptions'?'Quotations, recurring service and policy-controlled lifecycle.':section==='invoices'?'Invoices generated in arrears. Confirm, print, send and record payments.':'Manage reusable catalog records and archived items.';
const params=new URLSearchParams(location.search);
if(section==='invoices'&&params.has('subscription'))pageUrl=`${endpoint}?subscription=${encodeURIComponent(params.get('subscription'))}`;
await load();
if(params.has('id'))await detail(params.get('id'));
if(section==='payments'&&params.has('invoice')){await edit();$('fields').querySelector('[name=invoice]').value=params.get('invoice');}
