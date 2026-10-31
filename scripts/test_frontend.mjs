// Execute the shipped dashboard module against a small DOM adapter. This is a
// behavior regression check, not a browser/layout test; no external packages.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,unlinkSync} from 'node:fs';

class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners={};this.dataset={};this.value='';this.hidden=false;}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  addEventListener(event,callback){this.listeners[event]=callback;}
  setAttribute(key,value){this[key]=value;}
  scrollIntoView(){}
  reset(){}
}
const source=readFileSync(new URL('../dashboard/static/dashboard/dashboard.js',import.meta.url),'utf8').replace(/^import[^\n]*\n/,'');
const temporary=new URL('../.local/',import.meta.url);
mkdirSync(temporary,{recursive:true});
const adapter=new URL('dashboard-test-adapter.mjs',temporary);
writeFileSync(adapter,`export const apiRequest=(...args)=>globalThis.dashboardTestContext.apiRequest(...args); export const currentUser=(...args)=>globalThis.dashboardTestContext.currentUser(...args); export const logout=async()=>{};`);
const generated=[];
async function environment(portal=false) {
  const nodes=new Map();
  const get=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
  const root=new Element();root.dataset={featurePage:portal?'portal':'overview',subscriptionsUrl:portal?'/api/my/subscriptions/':'/api/subscriptions/',invoicesUrl:portal?'/api/billing/my/invoices/':'/api/billing/invoices/',paymentsUrl:'/api/billing/my/payments/',summaryUrl:'/api/billing/dashboard/summary/'};
  const calls=[];
  let failNext=false;
  const subscription=(id,name)=>({id,subscription_number:`REAL-${id}`,plan_name:name,customer_display:'Real Customer',status:'active',start_date:'2026-01-01',renewal_date:'2026-02-01',price:'1940.80',lines:[],permitted_actions:['pause']});
  const first={count:21,next:`${root.dataset.subscriptionsUrl}?page=2`,previous:null,results:[subscription(1,'Live first page')]};
  const second={count:21,next:null,previous:root.dataset.subscriptionsUrl,results:[subscription(2,'Live second page')]};
  const apiRequest=async (url,options={})=>{
    calls.push([url,options]);
    if(url.includes('/actions/'))return {};
    if(url.startsWith(root.dataset.subscriptionsUrl)){if(failNext)throw new Error('Offline');return url.includes('page=2')?second:first;}
    if(url.includes('summary'))return {active_subscriptions:21,billed_revenue:'5822.40',payments_collected:'2440.80',total_outstanding:'3381.60',overdue_invoices:2};
    if(url.includes('/customers/'))return {results:[]};
    return {count:0,next:null,previous:null,results:[]};
  };
  const document={querySelector:()=>root,getElementById:get,createElement:tag=>new Element(tag),querySelectorAll:()=>[]};
  const currentUser=async()=>({role:portal?'customer':'staff',email:'demo@example.test'});
  class FakeFormData { [Symbol.iterator](){return [['status','confirmed'],['customer','']][Symbol.iterator]();} }
  globalThis.dashboardTestContext={apiRequest,currentUser};
  globalThis.document=document;globalThis.location={href:'http://localhost/dashboard/',assign(){}};globalThis.FormData=FakeFormData;
  const target=new URL(`dashboard-test-${portal?'customer':'staff'}.mjs`,temporary);
  generated.push(target);
  writeFileSync(target,`import {apiRequest,currentUser,logout} from './dashboard-test-adapter.mjs';\n`+source);
  await import(target.href);
  return {get,calls,fail:()=>{failNext=true;}};
}
const staff=await environment();
const totals=staff.get('metric-billed').textContent;
assert.equal(staff.get('subscriptions-body').children[0].children[1].children[0].textContent,'Live first page');
await staff.get('subscriptions-next').onclick();
assert.equal(staff.get('subscriptions-body').children[0].children[1].children[0].textContent,'Live second page');
assert.equal(staff.get('metric-billed').textContent,totals,'Pagination must not replace global live financial totals');
assert.equal(staff.get('subscriptions-next').disabled,true);
assert.equal(staff.calls.filter(([url])=>url.includes('/summary/')).length,1);
staff.fail();await staff.get('subscriptions-prev').onclick();
assert.equal(staff.get('error-state').hidden,false);
assert.equal(staff.get('metric-billed').textContent,totals,'Failure must never introduce demo totals');
const customer=await environment(true);
await customer.get('portal-subscriptions-next').onclick();
assert.equal(customer.get('portal-subscriptions-body').children[0].children[0].children[0].textContent,'Live second page');
const pause=customer.get('portal-subscriptions-body').children[0].children[5].children[0];
await pause.listeners.click();
assert(customer.calls.some(([url,options])=>url==='/api/my/subscriptions/2/actions/pause/'&&options.method==='POST'));
assert(!customer.calls.some(([url])=>url.startsWith('/api/subscriptions/')));
console.log('PASS: live staff and customer pagination, unchanged global metrics, error state, own-customer action routing. Browser rendering not tested.');
// Loading the management module exercises its initial live list and parses the
// complete editor/action code without pretending to render a browser layout.
globalThis.document.body={dataset:{section:'products',role:'staff'}};
globalThis.location.search='';
const management=new URL('management-test.mjs',temporary);
generated.push(management);
writeFileSync(management,readFileSync(new URL('../subscriptions/static/subscriptions/manage.js',import.meta.url),'utf8').replace(/^import[^\n]*\n/,`import {apiRequest,logout} from './dashboard-test-adapter.mjs';\n`));
await import(management.href);
console.log('PASS: management module syntax and initial live catalog list.');
for(const target of [...generated,adapter])unlinkSync(target);
