'use strict';
/* Run: node ui_react/src/tests/write_readback_regression.cjs
 * Uses the existing TypeScript dependency (or an installed TYPESCRIPT_PATH).
 * Executes production declarations, the real store, and production JSX expressions.
 * HTTP, React state/effects, and JSX element creation are test doubles: NOT a
 * React DOM, browser, API integration, or MySQL persistence suite. No installs,
 * network requests, credentials, application boot, or database writes.
 */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { randomUUID } = require('node:crypto');
const ts = require(process.env.TYPESCRIPT_PATH || 'typescript');
const root = path.resolve(__dirname, '..');
const files = {
  candidate: 'components/OrderCandidateContactStatusPanel.tsx',
  command: 'api/scheduling/candidate_contact_pool_client.ts',
  dates: 'components/OrderServiceDatesPanel.tsx',
  actual: 'components/OrderActualStartPanel.tsx',
  store: 'adapters/orders/order_mutation_flow_store.ts',
  flow: 'adapters/orders/order_mutation_adapter.ts',
  errors: 'api/shared/typed_errors.ts',
};
function tree(file) {
  return ts.createSourceFile(files[file], fs.readFileSync(path.join(root, files[file]), 'utf8'), ts.ScriptTarget.Latest, true);
}
function declaration(file, symbol) {
  const ast = tree(file), found = [];
  function visit(node) {
    if ((ts.isVariableDeclaration(node) || ts.isFunctionDeclaration(node) || ts.isClassDeclaration(node))
      && node.name?.getText(ast) === symbol) found.push(node);
    ts.forEachChild(node, visit);
  }
  visit(ast);
  assert.equal(found.length, 1, `${file}: expected one ${symbol}`);
  return { ast, node: found[0] };
}
function source(file, ...names) {
  return names.map(name => {
    const { ast, node } = declaration(file, name);
    return ts.isVariableDeclaration(node) ? `const ${node.getText(ast)};` : node.getText(ast);
  }).join('\n');
}
function compile(text, names, env = {}) {
  const result = ts.transpileModule(text.replace(/\bexport\s+(?=(?:async\s+)?function|abstract\s+class|class)/g, ''), {
    fileName: 'test-boundary.tsx', reportDiagnostics: true,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None, jsx: ts.JsxEmit.React },
  });
  assert.equal((result.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error).length, 0);
  const context = vm.createContext({ Error, Map, Set, Promise, AbortController, console, crypto: { randomUUID }, ...env });
  const functions = vm.runInContext(`(function(){${result.outputText}\nreturn {${names.join(',')}};})()`, context, { timeout: 1000 });
  return { context, functions };
}
const errors = compile(source('errors', 'ApiError', 'ApiHttpError', 'ApiNetworkError', 'ApiTimeoutError'),
  ['ApiHttpError', 'ApiNetworkError', 'ApiTimeoutError']).functions;
const Store = compile(source('store', 'generateIdempotencyKey', 'areDateArraysEqual', 'OrderMutationFlowStore'), ['OrderMutationFlowStore']).functions.OrderMutationFlowStore;
const copy = value => JSON.parse(JSON.stringify(value));
const message = error => error instanceof Error ? error.message : '操作失敗';
const records = [];
async function test(id, fn) {
  try { await fn(); records.push({ id, status: 'passed' }); }
  catch (error) { records.push({ id, status: 'failed', error: error.message }); }
  console.log(JSON.stringify(records.at(-1)));
}
function setters(out, names) {
  return Object.fromEntries(names.map(name => ['set' + name, value => {
    const key = name[0].toLowerCase() + name.slice(1);
    out[key] = typeof value === 'function' ? value(out[key]) : value;
  }]));
}
const jsx = { Fragment: 'Fragment', createElement: (type, props, ...children) => ({ type, props: props || {}, children: children.flat(Infinity) }) };
function render(file, name, env) {
  const { ast, node } = declaration(file, name);
  const returns = node.initializer.body.statements.filter(ts.isReturnStatement);
  assert.equal(returns.length, 1);
  return compile(`function render(){return ${returns[0].expression.getText(ast)};}`, ['render'], { React: jsx, ...env }).functions.render();
}
function nodes(node, predicate) {
  if (!node || typeof node !== 'object') return [];
  return [...(predicate(node) ? [node] : []), ...(node.children || []).flatMap(child => nodes(child, predicate))];
}
function text(node) {
  if (node === null || node === undefined || typeof node === 'boolean') return '';
  if (typeof node !== 'object') return String(node);
  return (node.children || []).map(text).join('');
}
function candidateHarness(failure = null) {
  const store = new Store(), calls = [];
  const candidates = [7, 8].map(id => ({ id, staff_name: `TEST-${id}`, willingness: 'pending', status: 'active',
    service_start_date: '2026-09-15', service_end_date: '2026-09-16', reason: null, information: { '1': null, '2': null } }));
  const out = { state: { status: 'ready', data: { candidates } }, mutationError: null, sendPreview: null,
    willingnessNotices: {}, reasonDrafts: { 7: 'TEST REASON' } };
  const activeCaseNo = { current: 'TEST-CASE' };
  const api = {
    recordWillingness: async command => { calls.push(command); if (failure) throw failure; return { event_id: 11, status: 'recorded' }; },
    sendInformation: async command => { calls.push(command); if (failure) throw failure; return { event_id: 11, line_task_id: 12, status: 'queued' }; },
  };
  const env = { ...errors, ...out, caseNo: 'TEST-CASE', mounted: { current: true }, activeCaseNo, orderMutationFlowStore: store,
    informationInFlight: { current: new Set() }, errorMessage: message, mutationIdentity: () => ({ actor: 'TEST-ACTOR' }),
    ...setters(out, ['State', 'MutationError', 'SendPreview', 'ReasonDrafts']), candidateContactPoolClient: api,
    observeWillingness: async id => { store.clearCandidateWillingness('TEST-CASE', id); out.observed = true; },
    observeInformation: async c => { store.clearCandidateInformation(c.caseNo, c.candidateId, c.infoType); out.observed = true; },
  };
  const functions = compile(source('command', 'canonicalCaseNo', 'canonicalCandidateWillingnessCommand', 'createCandidateWillingnessCommand')
    + '\n' + source('candidate', 'submitInformation', 'submitWillingness'), ['submitInformation', 'submitWillingness'], env).functions;
  const view = () => render('candidate', 'OrderCandidateContactStatusPanel', { ...env, ...out, ...functions,
    candidateInformationFlows: store.getCandidateInformationForCase('TEST-CASE'), CandidateInformationSend: 'InfoPreview',
    deliveryStatus: () => 'TEST', loadStatus: () => {}, retryInformation: () => {}, retryInformationReadback: () => {},
    retryWillingness: () => {}, retryWillingnessReadback: () => {},
  });
  return { store, calls, out, api, functions, view, activeCaseNo };
}
function datesHarness(queryChange = {}, failure = null, receiptChange = {}) {
  const store = new Store(), calls = { apply: 0, query: 0 };
  const dates = ['2026-09-15', '2026-09-16'];
  const receipt = { case_no: 'TEST-CASE', confirmed_version: 2, order_version: 4, scheduling_version: 3,
    service_dates: dates, preview_fingerprint: 'a'.repeat(64), ...receiptChange };
  const query = { case_no: 'TEST-CASE', current_version: 2, order_version: 4, scheduling_version: 3, contracted_service_days: 2,
    current_dates: [...dates], suggested_dates: [], selectable_dates: ['2026-09-15', '2026-09-16', '2026-09-17', '2026-09-18'], ...queryChange };
  const draft = store.getOrCreateServiceDatesDraft('TEST-CASE');
  Object.assign(draft, { status: 'preview_ready', selectedDates: [...dates], reason: 'TEST REASON',
    queryView: { ...query, current_version: 1, current_dates: [...dates] }, previewView: { order_version: 4, scheduling_version: 3, preview_fingerprint: 'a'.repeat(64) } });
  const api = { applyServiceDates: async () => { calls.apply++; return receipt; },
    getServiceDates: async () => { calls.query++; if (failure) throw failure; return copy(query); } };
  class MutationError extends Error { constructor(value) { super(value.message); Object.assign(this, value); } }
  const functions = compile(source('flow', 'applyServiceDatesFlow', 'retryServiceDatesObservationFlow')
    + '\n' + source('dates', 'recoveryFromServiceDatesDraft'), ['applyServiceDatesFlow', 'retryServiceDatesObservationFlow', 'recoveryFromServiceDatesDraft'], {
    orderMutationFlowStore: store, ordersMutationClient: api, normalizeFlowError: e => e,
    isOutcomeUnknownError: e => e instanceof errors.ApiNetworkError, isStaleConflictError: () => false,
    OrderMutationValidationError: MutationError, OrderMutationConflictError: MutationError,
  }).functions;
  return { store, get draft() { return store.getServiceDatesDraft('TEST-CASE'); }, receipt, query, calls, functions, api };
}
function latestHarness(h, next = h.query, failure = null) {
  const out = { queryView: h.draft.queryView, selectedDates: [...h.draft.selectedDates], precision: { actual_start_date: 'OLD', actual_end_date: 'OLD' },
    serviceMode: '連續服務', preview: { service_dates: ['OLD'] }, working: null, error: null, success: null,
    calculationBasis: { date: 'OLD', confirmed: true }, basisNotice: 'OLD', hasManualChanges: true };
  const renderedCaseNo = { current: 'TEST-CASE' }, actionInFlight = { current: new Set() };
  const api = { getServiceDates: async () => { h.calls.query++; if (failure) throw failure; return copy(next); } };
  const env = { ...out, caseNo: 'TEST-CASE', calculationRevision: 0, orderMutationFlowStore: h.store, ordersMutationClient: api,
    readController: { current: null }, calculationSequence: { current: 0 },
    recoveryFromServiceDatesDraft: h.functions.recoveryFromServiceDatesDraft, renderedCaseNo, actionInFlight,
    selectServiceDates: (c, d) => h.store.updateServiceDatesSelection(c, d), updateServiceDatesReason: (c, r) => h.store.updateServiceDatesReason(c, r),
    AUTOMATIC_CONFIRMATION_REASON: '確認正式服務日期', errorMessage: message, onObserved: () => {},
    ...setters(out, ['Working', 'Error', 'Success', 'Preview', 'QueryView', 'SelectedDates', 'Precision', 'ServiceMode', 'CalculationBasis', 'BasisNotice', 'HasManualChanges', 'AttemptedCalculationRevision']),
  };
  const load = () => compile(source('dates', 'loadServiceDates'), ['loadServiceDates'], env).functions.loadServiceDates('resume');
  const view = () => {
    const recovery = h.functions.recoveryFromServiceDatesDraft('TEST-CASE');
    const derived = compile(source('dates', 'requiredDateCount', 'canPreview', 'canApply'), ['requiredDateCount', 'canPreview', 'canApply'], {
      ...out, needsBasisUpdate: false, isRecoveryActive: recovery?.caseNo === 'TEST-CASE',
    }).functions;
    return render('dates', 'OrderServiceDatesPanel', { ...out, ...derived, needsBasisUpdate: false, caseNo: 'TEST-CASE', recovery, isRecoveryActive: recovery?.caseNo === 'TEST-CASE',
      loadServiceDates: load, retryApply: () => {}, retryObservation: () => {},
      changeDate: () => {}, runPreview: () => {}, runApply: () => {}, onOpenActualStart: undefined,
    });
  };
  return { out, load, view, renderedCaseNo, api };
}
function actualHarness() {
  const store = new Store(), calls = { preview: 0, apply: [], query: 0 };
  let rootFact = { case_no: 'TEST-CASE', current_actual_start_date: null, planned_start_date: '2026-09-20', order_version: 1, scheduling_version: 1, service_data_locked: false };
  let context;
  const env = { ...errors, OrderMutationError: class extends Error {}, caseNo: 'TEST-CASE', query: copy(rootFact), date: '2026-09-15',
    reason: 'TEST REASON', preview: null, phase: 'idle', error: null, inFlight: { current: new Set() }, sequence: { current: 0 },
    observationSequence: { current: 0 }, mounted: { current: true }, activeCaseNo: { current: 'TEST-CASE' },
    onBusyChange: () => {}, onObserved: () => {}, orderMutationFlowStore: store,
    ordersQueryClient: { getActualStart: async () => { calls.query++; return copy(rootFact); } },
    orderActualStartClient: {
      preview: async (c, p) => { calls.preview++; return { actual_start: { case_no: c }, after_actual_start_date: p.new_actual_start_date,
        order_version: rootFact.order_version, scheduling_version: rootFact.scheduling_version, client_finance_version: 0, payroll_version: 0,
        preview_fingerprint: 'a'.repeat(64), client_finance_impact: { blockers: [] }, payroll_impact: { blockers: [] } }; },
      apply: async (c, p, options) => { calls.apply.push({ payload: copy(p), key: options.idempotencyKey });
        rootFact = { ...rootFact, current_actual_start_date: p.new_actual_start_date, order_version: rootFact.order_version + 1, scheduling_version: rootFact.scheduling_version + 1 };
        return { case_no: c, order_version: rootFact.order_version, scheduling_version: rootFact.scheduling_version, preview_fingerprint: p.preview_fingerprint }; },
    },
  };
  function derive() {
    context.flow = store.getActualStart('TEST-CASE');
    const derived = compile(source('actual', 'flowPhase', 'unresolved', 'busy'), ['flowPhase', 'unresolved', 'busy'], { flow: context.flow, phase: context.phase }).functions;
    Object.assign(context, derived);
  }
  for (const name of ['Query', 'Date', 'Reason', 'Preview', 'Phase', 'Error']) env['set' + name] = v => { context[name[0].toLowerCase() + name.slice(1)] = v; derive(); };
  const built = compile(source('actual', 'isActive', 'observe', 'load', 'check', 'apply'), ['check', 'apply'], env);
  context = built.context; store.subscribe(derive); derive();
  return { context, functions: built.functions, store, calls, derive, fact: () => rootFact };
}
// Full component lifecycle cases; the hook scheduler and HTTP endpoints remain test doubles.
class FlowError extends Error { constructor(x) {super(x.message);Object.assign(this,x);} }
class StaleError extends FlowError {}
function deferred() {let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
function refreshHarness({revision=0, historical=false, unconfirmed=false, savedDates=['2026-09-15','2026-09-17'], seed, file=files.dates}={}) {
 const store=new Store(); if(seed)seed(store);
 const calls={get:0, actual:0, calculate:[], preview:[], apply:[], observed:0};
 const allDays=Array.from({length:12},(_,i)=>`2026-09-${String(15+i).padStart(2,'0')}`);
 const model={caseNo:historical?'TEST-HISTORICAL':'TEST-NORMAL', start:unconfirmed?null:'2026-09-15', historical,
  query:{case_no:historical?'TEST-HISTORICAL':'TEST-NORMAL',order_version:1,scheduling_version:1,current_version:savedDates.length?1:null,
   current_dates:savedDates,contracted_service_days:2,selectable_dates:allDays,suggested_dates:[]}};
 const api={
  getServiceDates:async()=>{calls.get++;return copy(model.query);},
  previewServiceDates:async(c,p)=>{calls.preview.push(copy(p));return {case_no:c,current_version:model.query.current_version,
   order_version:model.query.order_version,scheduling_version:model.query.scheduling_version,service_dates:p.service_dates,preview_fingerprint:'a'.repeat(64)};},
  applyServiceDates:async(c,p,options)=>{calls.apply.push({caseNo:c,payload:copy(p),key:options.idempotencyKey});
   model.query={...model.query,current_version:(model.query.current_version??0)+1,current_dates:copy(p.service_dates),
    scheduling_version:model.query.scheduling_version+(model.historical?1:0)};
   return {case_no:c,confirmed_version:model.query.current_version,order_version:model.query.order_version,
    scheduling_version:model.query.scheduling_version,service_dates:copy(p.service_dates),preview_fingerprint:p.preview_fingerprint};},
 };
 const queries={getActualStart:async()=>{calls.actual++;return {case_no:model.caseNo,current_actual_start_date:model.start,
  planned_start_date:'2026-09-20',order_version:model.query.order_version,scheduling_version:model.query.scheduling_version};},
  getOrderCalendarDetail:async()=>({case_no:model.caseNo,service_mode:'連續服務'})};
 const precision={calculate:async p=>{calls.calculate.push(copy(p));const ds=allDays.slice(allDays.indexOf(p.actual_start_date),allDays.indexOf(p.actual_start_date)+2);
   return {actual_start_date:p.actual_start_date,actual_end_date:ds.at(-1),target_service_days:2,day_by_day:ds.map(date=>({date,is_work_day:true}))};}};
 const flow=compile(source('flow', 'fetchServiceDatesQuery', 'selectServiceDates', 'updateServiceDatesReason',
   'previewServiceDatesFlow', 'applyServiceDatesFlow', 'retryServiceDatesApplyFlow', 'retryServiceDatesObservationFlow'),
   ['fetchServiceDatesQuery', 'selectServiceDates', 'updateServiceDatesReason', 'previewServiceDatesFlow',
    'applyServiceDatesFlow', 'retryServiceDatesApplyFlow', 'retryServiceDatesObservationFlow'], {
   orderMutationFlowStore:store,ordersMutationClient:api,normalizeFlowError:e=>e,
   isOutcomeUnknownError:e=>e.code==='NETWORK',isStaleConflictError:e=>e instanceof StaleError,
   OrderMutationValidationError:FlowError,OrderMutationConflictError:StaleError}).functions;
 const slots=[],effects=[];let index=0,dirty=true,view=null,mounted=true,renders=0;
 let props={caseNo:model.caseNo,calculationRevision:revision,onObserved:()=>calls.observed++};
 const hooks={
  useRef:value=>{const i=index++;if(!slots[i])slots[i]={current:value};return slots[i];},
  useState:initial=>{const i=index++;if(!slots[i]){const cell={value:typeof initial==='function'?initial():initial};
    cell.set=value=>{const next=typeof value==='function'?value(cell.value):value;if(!Object.is(next,cell.value)){cell.value=next;dirty=true;}};slots[i]=cell;}
    return [slots[i].value,slots[i].set];},
  useEffect:(setup,deps)=>{const i=index++;if(!effects[i]||deps.some((d,j)=>!Object.is(d,effects[i].deps[j]))){
    const old=effects[i];effects[i]={deps:[...deps],setup,cleanup:old?.cleanup,pending:true};}},
 };
 const code=fs.readFileSync(path.join(root,file),'utf8').replace(/^import[\s\S]*?from ['"][^'"]+['"];\n/gm,'')
   .replace(/^export default[^\n]*$/gm,'').replace(/^export /gm,'');
 const component=compile(code,['OrderServiceDatesPanel'],{...hooks,...flow,orderMutationFlowStore:store,ordersMutationClient:api,
  ordersQueryClient:queries,schedulePrecisionClient:precision,
  React:{Fragment:'Fragment',createElement:(type,props,...children)=>({type,props:props||{},children:children.flat(Infinity)})}}).functions.OrderServiceDatesPanel;
 function render(){if(!mounted||!dirty)return;dirty=false;index=0;view=component(props);renders++;
   for(const effect of effects){if(effect?.pending){effect.pending=false;effect.cleanup?.();effect.cleanup=effect.setup();}}}
 async function flush(){for(let i=0;i<35;i++){await Promise.resolve();render();}if(dirty)throw new Error('render loop');}
 function button(label){const b=nodes(view,n=>n.type==='button'&&text(n)===label)[0];if(!b)throw new Error('Missing button: '+label+'; '+text(view));return b;}
 function click(label){const b=button(label);assert.equal(Boolean(b.props.disabled),false,'disabled '+label);return b.props.onClick();}
 function unmount(){mounted=false;for(const e of effects)e?.cleanup?.();}
 render();
 return {store,calls,model,api,queries,precision,flow,flush,click,button,unmount,
  view:()=>view,labels:()=>text(view),props:p=>{props={...props,...p};dirty=true;},renders:()=>renders,
  dates:()=>nodes(view,n=>n.props['aria-pressed']===true).map(n=>n.props['aria-label'].slice('服務日期 '.length))};
}

async function calculate(h){h.click('精算天數並設定服務日期');await h.flush();}
async function preview(h){h.click('確認服務日期');await h.flush();}
async function refreshCases(){
 for(const historical of [false,true]){
  await test(`${historical?'historical':'normal'}: open reads saved manual dates without calculating or writing`,async()=>{
   const h=refreshHarness({historical});await h.flush();assert.deepEqual(h.dates(),['2026-09-15','2026-09-17']);assert.equal(h.calls.calculate.length,0);assert.equal(h.calls.apply.length,0);
   assert.equal(nodes(h.view(),n=>n.props['aria-label']==='正式服務日期回讀').length,1);h.unmount();});
  await test(`${historical?'historical-restart':'normal'}: calculate, confirm, read version, reopen preserves saved dates`,async()=>{
   const h=refreshHarness({historical,savedDates:[],revision:historical?1:0});await h.flush();if(!historical)await calculate(h);
   await preview(h);h.click('完成服務日期確認');await h.flush();const d=h.store.getServiceDatesDraft(h.model.caseNo);
   assert.equal(d.status,'observed');assert.equal(h.calls.apply.length,1);assert.equal(d.queryView.scheduling_version,historical?2:1);
   const saved=copy(h.model.query.current_dates);h.unmount();const reopened=refreshHarness({historical,savedDates:saved});await reopened.flush();
   assert.deepEqual(reopened.dates(),saved);assert.equal(reopened.calls.calculate.length,0);assert.equal(reopened.calls.apply.length,0);reopened.unmount();});
 }
 await test('late old GET cannot overwrite a later observation_failed receipt',async()=>{
  const h=refreshHarness(), old=deferred(), original=copy(h.model.query);let n=0;
  // Initial request was issued at mount; start a slow explicit calculation next.
  await h.flush();h.api.getServiceDates=()=>{h.calls.get++;return ++n===1?old.promise:Promise.resolve(copy(h.model.query));};
  h.click('精算天數並設定服務日期');await h.flush();h.model.start='2026-09-18';h.model.query={...h.model.query,order_version:2,scheduling_version:2};
  h.props({calculationRevision:1});await h.flush();await preview(h);
  h.api.getServiceDates=async()=>{throw new Error('READ FAILED');};h.click('完成服務日期確認');await h.flush();
  const d=h.store.getServiceDatesDraft(h.model.caseNo), receipt=d.receiptView;assert.equal(d.status,'observation_failed');
  old.resolve(original);await h.flush();assert.equal(d.status,'observation_failed');assert.equal(d.receiptView,receipt);
  assert.ok(h.button('只重新讀取服務日期結果'));assert.deepEqual(h.dates(),['2026-09-18','2026-09-19']);h.unmount();
 });
 await test('revision arriving during Apply resumes after stale rejection',async()=>{
  const h=refreshHarness();await h.flush();await calculate(h);await preview(h);const pending=deferred();h.api.applyServiceDates=()=>pending.promise;
  h.click('完成服務日期確認');await h.flush();h.model.start='2026-09-18';h.model.query={...h.model.query,order_version:2,scheduling_version:2};
  h.props({calculationRevision:1});await h.flush();assert.equal(h.calls.calculate.length,1);assert.ok(h.labels().includes('待目前操作結果確認'));
  pending.reject(new StaleError({code:'stale_preview',message:'NEW BASIS'}));await h.flush();assert.equal(h.calls.calculate.length,2);
  assert.deepEqual(h.dates(),['2026-09-18','2026-09-19']);h.unmount();
 });
 await test('unconfirmed historical restart uses planned date and truthful trial notice',async()=>{
  const h=refreshHarness({revision:1,historical:true,unconfirmed:true,savedDates:[]});await h.flush();
  assert.deepEqual(h.dates(),['2026-09-20','2026-09-21']);assert.ok(h.labels().includes('依原訂日期試算'));
  assert.equal(h.labels().includes('已依正式實際開始日更新'),false);assert.equal(h.calls.apply.length,0);h.unmount();
 });
 await test('pending preview is not adopted as a current preview after basis change',async()=>{
  const h=refreshHarness();await h.flush();const pending=deferred();h.api.previewServiceDates=()=>pending.promise;h.click('確認服務日期');await h.flush();
  h.model.start='2026-09-18';h.model.query={...h.model.query,order_version:2,scheduling_version:2};h.props({calculationRevision:1});await h.flush();
  pending.resolve({case_no:h.model.caseNo,current_version:1,order_version:1,scheduling_version:1,service_dates:['2026-09-15','2026-09-17'],preview_fingerprint:'a'.repeat(64)});
  await h.flush();assert.deepEqual(h.dates(),['2026-09-18','2026-09-19']);assert.equal(h.store.getServiceDatesDraft(h.model.caseNo).previewView,null);
  assert.equal(nodes(h.view(),n=>n.type==='button'&&text(n)==='完成服務日期確認').length,0);h.unmount();
 });
 await test('failed automatic read stops, explicit retry works without infinite retries',async()=>{
  const h=refreshHarness();await h.flush();let count=0;h.api.getServiceDates=async()=>{count++;if(count===1)throw new Error('UNAVAILABLE');return copy(h.model.query);};
  h.props({calculationRevision:1});await h.flush();await h.flush();assert.equal(count,1);assert.ok(h.labels().includes('尚未更新'));
  assert.equal(nodes(h.view(),n=>n.type==='button'&&text(n)==='確認服務日期'&&!n.props.disabled).length,0,'failed recalculation must not offer stale dates for confirmation');
  await calculate(h);assert.equal(count,2);assert.equal(h.calls.calculate.length,1);h.unmount();
 });
 await test('unrelated rerender does not recalculate confirmed dates or manual selection',async()=>{
  const h=refreshHarness({revision:1});await h.flush();await preview(h);h.click('完成服務日期確認');await h.flush();h.props({onObserved:()=>{}});await h.flush();
  assert.equal(h.calls.calculate.length,1);assert.equal(h.store.getServiceDatesDraft(h.model.caseNo).status,'observed');h.unmount();
 });
 for(const status of ['outcome_unknown','apply_pending','requery_loading','observation_failed'])await test(`pending ${status} retains command, key and receipt on new revision`,async()=>{
  const h=refreshHarness();await h.flush();const d=h.store.getServiceDatesDraft(h.model.caseNo);d.status=status;d.receiptView=status==='outcome_unknown'?null:{case_no:h.model.caseNo,confirmed_version:1,order_version:1,scheduling_version:1,service_dates:copy(d.selectedDates)};
  const before={key:d.idempotencyKey,receipt:d.receiptView};h.props({calculationRevision:1});await h.flush();assert.equal(d.status,status);assert.equal(d.receiptView,before.receipt);assert.equal(d.idempotencyKey,before.key);assert.equal(h.calls.calculate.length,0);h.unmount();
 });
 async function superseded(revision=0){const h=refreshHarness();await h.flush();const d=h.store.getServiceDatesDraft(h.model.caseNo);
  d.status='observation_failed';d.receiptView={case_no:h.model.caseNo,confirmed_version:1,order_version:1,scheduling_version:1,service_dates:['2026-09-15','2026-09-17']};
  h.model.query={...h.model.query,current_version:2,current_dates:['2026-09-18','2026-09-19']};d.queryView=copy(h.model.query);h.props({calculationRevision:revision});await h.flush();return h;}
 await test('explicit newer formal read preserves current dates without recalculation or resubmission',async()=>{
  const h=await superseded(1);h.click('載入目前正式服務日期');await h.flush();assert.deepEqual(h.dates(),h.model.query.current_dates);
  assert.equal(h.calls.calculate.length,0);assert.equal(h.calls.apply.length,0);assert.equal(h.store.getServiceDatesDraft(h.model.caseNo).receiptView,null);
  assert.equal(h.labels().includes('建議服務日期摘要'),false);h.unmount();
 });
 for(const failure of ['network','older','wrong-case'])await test(`newer formal read ${failure} keeps receipt recovery`,async()=>{
  const h=await superseded(),d=h.store.getServiceDatesDraft(h.model.caseNo),r=d.receiptView,key=d.idempotencyKey;
  h.api.getServiceDates=async()=>{if(failure==='network')throw new Error('READ FAILED');return {...h.model.query,...(failure==='older'?{current_version:1}:{case_no:'OTHER'})};};
  h.click('載入目前正式服務日期');await h.flush();assert.equal(d.receiptView,r);assert.equal(d.idempotencyKey,key);assert.ok(h.button('載入目前正式服務日期'));assert.equal(h.calls.apply.length,0);h.unmount();
 });
 await test('case switch invalidates a late read before shared state publication',async()=>{
  const h=refreshHarness();await h.flush();const pending=deferred(),before=h.store.getServiceDatesDraft(h.model.caseNo).queryView;
  h.api.getServiceDates=()=>pending.promise;h.click('精算天數並設定服務日期');await h.flush();h.unmount();pending.resolve({...before,current_version:99});await h.flush();
  assert.equal(h.store.getServiceDatesDraft(h.model.caseNo).queryView,before);
 });
 await test('mixed actual-start/service-date versions never produce a supposedly current calculation',async()=>{
  const h=refreshHarness();await h.flush();h.queries.getActualStart=async()=>({case_no:h.model.caseNo,current_actual_start_date:'2026-09-18',order_version:2,scheduling_version:2});
  await calculate(h);assert.equal(h.calls.calculate.length,0);assert.ok(h.labels().includes('版本不同'));assert.equal(h.calls.apply.length,0);h.unmount();
 });
 await test('revision deferred by failed observation resumes after successful readback',async()=>{
  const h=refreshHarness();await h.flush();await calculate(h);await preview(h);
  const get=h.api.getServiceDates;h.api.getServiceDates=async()=>{throw new Error('READ FAILED');};
  h.click('完成服務日期確認');await h.flush();assert.equal(h.store.getServiceDatesDraft(h.model.caseNo).status,'observation_failed');
  h.model.start='2026-09-18';h.model.query={...h.model.query,order_version:2,scheduling_version:2};h.props({calculationRevision:1});await h.flush();
  assert.equal(h.calls.calculate.length,1);h.api.getServiceDates=get;h.click('只重新讀取服務日期結果');await h.flush();
  assert.equal(h.calls.calculate.length,2);assert.equal(h.calls.apply.length,1);assert.deepEqual(h.dates(),['2026-09-18','2026-09-19']);h.unmount();
 });
 await test('read may not replace a newer shared draft created while calculation was pending',async()=>{
  const h=refreshHarness();await h.flush();const pending=deferred();h.precision.calculate=()=>pending.promise;
  h.click('精算天數並設定服務日期');await h.flush();const newer={...h.model.query,current_version:7,current_dates:['2026-09-18','2026-09-19']};
  h.store.setServiceDatesQueryReady(h.model.caseNo,newer);
  pending.resolve({actual_start_date:'2026-09-15',actual_end_date:'2026-09-16',day_by_day:[{date:'2026-09-15',is_work_day:true},{date:'2026-09-16',is_work_day:true}]});await h.flush();
  assert.equal(h.store.getServiceDatesDraft(h.model.caseNo).queryView,newer);h.unmount();
 });
 await test('manual draft on the same official basis survives reopening a read-only view',async()=>{
  const h=refreshHarness({seed:store=>{const d=store.getOrCreateServiceDatesDraft('TEST-NORMAL');Object.assign(d,{status:'draft_changed',
   queryView:{case_no:'TEST-NORMAL',order_version:1,scheduling_version:1,current_version:1},selectedDates:['2026-09-16','2026-09-18']});}});
  await h.flush();assert.deepEqual(h.dates(),['2026-09-16','2026-09-18']);assert.equal(h.calls.calculate.length,0);assert.equal(h.calls.apply.length,0);h.unmount();
 });
}

async function main() {
  await test('C01 blank reason keeps list, draft, and other recovery visible', async () => {
    const h = candidateHarness();
    h.store.setCandidateWillingness('TEST-CASE', { status: 'observation_failed', command: { caseNo: 'TEST-CASE', candidateId: 8 }, receipt: { event_id: 9 } });
    await h.functions.submitWillingness(7, 'unwilling', '   ');
    assert.equal(h.calls.length, 0); assert.match(h.out.mutationError || '', /理由/); assert.equal(h.out.state.status, 'ready');
    assert.equal(h.out.reasonDrafts[7], 'TEST REASON');
    assert.equal(nodes(h.view(), n => n.type === 'article').length, 2);
    assert.ok(nodes(h.view(), n => n.type === 'button' && text(n) === '重新讀取最新結果').length);
  });
  for (const status of [403, 409, 422]) await test(`C${status} rejection stays visible without hiding candidates`, async () => {
    const h = candidateHarness(new errors.ApiHttpError(status, 'TEST', `DENIED ${status}`));
    await h.functions.submitWillingness(7, 'unwilling', 'TEST REASON');
    assert.equal(h.calls.length, 1); assert.equal(h.store.getCandidateWillingness('TEST-CASE', 7), undefined);
    assert.match(h.out.mutationError || '', /DENIED/); assert.equal(h.out.state.status, 'ready');
    assert.ok(nodes(h.view(), n => n.props.role === 'alert' && text(n).includes('DENIED')).length);
  });
  for (const status of [403, 409]) await test(`I${status} information rejection preserves list`, async () => {
    const h = candidateHarness(new errors.ApiHttpError(status, 'TEST', 'DENIED'));
    await h.functions.submitInformation({ caseNo: 'TEST-CASE', candidateId: 7, infoType: 1, eventKey: 'TEST' });
    assert.equal(h.calls.length, 1); assert.match(h.out.mutationError || '', /DENIED/); assert.equal(h.out.state.status, 'ready');
  });
  await test('C02 unknown outcome retains original command', async () => {
    const h = candidateHarness(new errors.ApiHttpError(500, 'TEST', 'UNKNOWN'));
    await h.functions.submitWillingness(7, 'unwilling', 'TEST REASON');
    assert.equal(h.store.getCandidateWillingness('TEST-CASE', 7).status, 'outcome_unknown'); assert.equal(h.out.observed, undefined);
  });
  await test('C03 valid operation still sends once', async () => {
    const h = candidateHarness(); await h.functions.submitWillingness(7, 'willing', '');
    assert.equal(h.calls.length, 1); assert.equal(h.out.observed, true);
  });
  await test('C04 late rejection does not affect another case', async () => {
    const h = candidateHarness(); let reject;
    h.api.recordWillingness = () => new Promise((_, r) => { reject = r; });
    const request = h.functions.submitWillingness(7, 'unwilling', 'TEST REASON');
    h.activeCaseNo.current = 'OTHER'; reject(new errors.ApiHttpError(403, 'TEST', 'DENIED')); await request;
    assert.equal(h.out.mutationError, null); assert.equal(h.out.state.status, 'ready');
  });
  await test('C05 open preview remains closable after another operation fails', async () => {
    const h = candidateHarness(); let reject;
    h.api.recordWillingness = () => new Promise((_, r) => { reject = r; });
    const request = h.functions.submitWillingness(7, 'unwilling', 'TEST REASON'); h.out.sendPreview = { candidateId: 8, kind: 1 };
    reject(new errors.ApiHttpError(403, 'TEST', 'DENIED')); await request;
    const modal = nodes(h.view(), n => n.type === 'InfoPreview'); assert.equal(modal.length, 1);
    modal[0].props.onClose();
    assert.equal(nodes(h.view(), n => n.type === 'button' && text(n) === '重新讀取候選清單')[0].props.disabled, false);
  });
  await test('C06 validation error can be corrected without reloading', async () => {
    const h = candidateHarness(); await h.functions.submitWillingness(7, 'unwilling', '');
    await h.functions.submitWillingness(7, 'unwilling', 'CORRECTED'); assert.equal(h.calls.length, 1); assert.equal(h.out.mutationError, null);
  });
  for (const [id, change] of Object.entries({
    D01: { current_version: 1 }, D02: { current_dates: ['2026-09-16', '2026-09-17'] }, D03: { case_no: 'OTHER' },
    D04: { order_version: 3 }, D05: { scheduling_version: 2 },
  })) await test(`${id} invalid readback never becomes observed`, async () => {
    const h = datesHarness(change); await assert.rejects(h.functions.applyServiceDatesFlow('TEST-CASE'));
    assert.equal(h.draft.status, 'observation_failed'); assert.equal(h.draft.receiptView, h.receipt); assert.equal(h.calls.apply, 1);
    assert.equal(h.functions.recoveryFromServiceDatesDraft('TEST-CASE').kind, 'observation_failed');
  });
  for (const version of [2, 3]) await test(`D-valid-${version} matching dates accepted`, async () => {
    const h = datesHarness({ current_version: version }); await h.functions.applyServiceDatesFlow('TEST-CASE'); assert.equal(h.draft.status, 'observed');
  });
  await test('D08 GET failure preserves receipt', async () => {
    const h = datesHarness({}, new Error('READ FAILED')); await assert.rejects(h.functions.applyServiceDatesFlow('TEST-CASE'));
    assert.equal(h.draft.status, 'observation_failed'); assert.equal(h.draft.receiptView, h.receipt);
  });
  await test('D09 observation retry does not rewrite', async () => {
    const h = datesHarness({ current_version: 1 }); h.draft.receiptView = h.receipt; h.draft.status = 'observation_failed';
    await assert.rejects(h.functions.retryServiceDatesObservationFlow('TEST-CASE')); assert.equal(h.calls.apply, 0);
  });
  await test('D10 fingerprint mismatch stops observation', async () => {
    const h = datesHarness({}, null, { preview_fingerprint: 'b'.repeat(64) });
    await assert.rejects(h.functions.applyServiceDatesFlow('TEST-CASE')); assert.equal(h.calls.query, 0);
  });
  await test('D11 valid observation retry completes without rewrite', async () => {
    const h = datesHarness(); h.draft.receiptView = h.receipt; h.draft.status = 'observation_failed';
    await h.functions.retryServiceDatesObservationFlow('TEST-CASE'); assert.equal(h.draft.status, 'observed'); assert.equal(h.calls.apply, 0);
  });
  async function superseded() {
    const h = datesHarness({ current_version: 3, current_dates: ['2026-09-16', '2026-09-17'] });
    await assert.rejects(h.functions.applyServiceDatesFlow('TEST-CASE')); return h;
  }
  await test('D12 later changed version has an explicit recovery path', async () => {
    const h = await superseded(); const key = h.draft.idempotencyKey;
    assert.equal(h.draft.receiptView, h.receipt); assert.equal(h.draft.queryView.current_version, 3);
    assert.equal(h.draft.previewView, null); assert.equal(h.functions.recoveryFromServiceDatesDraft('TEST-CASE').kind, 'superseded');
    const v = latestHarness(h).view(); assert.ok(nodes(v, n => n.type === 'button' && text(n) === '載入目前正式服務日期').length);
    assert.equal(nodes(v, n => n.type === 'button' && text(n) === '只重新讀取服務日期結果').length, 0);
    assert.equal(h.draft.idempotencyKey, key);
  });
  await test('D13 load latest version selects its dates, invalidates preview, and never writes', async () => {
    const h = await superseded(), key = h.draft.idempotencyKey, oldWrites = h.calls.apply;
    const next = { ...h.query, current_version: 4, current_dates: ['2026-09-17', '2026-09-18'] };
    const l = latestHarness(h, next); await l.load();
    assert.equal(h.calls.apply, oldWrites); assert.notEqual(h.draft.idempotencyKey, key);
    assert.deepEqual(copy(h.draft.selectedDates), next.current_dates); assert.equal(h.draft.receiptView, null);
    assert.equal(h.functions.recoveryFromServiceDatesDraft('TEST-CASE'), null); assert.equal(l.out.preview, null); assert.equal(l.out.precision, null);
    assert.equal(l.out.calculationBasis, null); assert.equal(l.out.basisNotice, null); assert.equal(l.out.hasManualChanges, false);
    const v = l.view(); assert.equal(nodes(v, n => n.props['aria-pressed'] === true).length, 2);
    assert.equal(nodes(v, n => n.type === 'button' && text(n) === '確認服務日期')[0].props.disabled, false);
  });
  for (const [id, mode] of [['D14', 'failure'], ['D15', 'old'], ['D16', 'other']]) await test(`${id} failed latest load keeps original recovery`, async () => {
    const h = await superseded(), receipt = h.draft.receiptView, key = h.draft.idempotencyKey;
    const next = { ...h.query, ...(mode === 'old' ? { current_version: 2 } : mode === 'other' ? { case_no: 'OTHER' } : {}) };
    const l = latestHarness(h, next, mode === 'failure' ? new Error('READ FAILED') : null); await l.load();
    assert.ok(l.out.error); assert.equal(h.draft.receiptView, receipt); assert.equal(h.draft.idempotencyKey, key);
    assert.equal(h.functions.recoveryFromServiceDatesDraft('TEST-CASE').kind, 'superseded'); assert.equal(h.calls.apply, 1);
  });
  await test('D17 latest load finishing after case switch does not release original recovery', async () => {
    const h = await superseded(), l = latestHarness(h); let resolve;
    l.api.getServiceDates = () => new Promise(r => { resolve = r; }); const pending = l.load();
    l.renderedCaseNo.current = 'OTHER'; resolve(h.query); await pending;
    assert.equal(h.draft.receiptView, h.receipt); assert.equal(l.out.success, null);
  });
  await test('AS01 consecutive confirmed corrections use distinct commands', async () => {
    const h = actualHarness(); await h.functions.check(); await h.functions.apply(); assert.equal(h.calls.apply.length, 1);
    h.context.setDate('2026-09-16'); h.context.setPreview(null); h.context.setPhase('idle'); h.context.setReason('SECOND');
    await h.functions.check(); await h.functions.apply(); assert.equal(h.calls.apply.length, 2);
    assert.notEqual(h.calls.apply[0].key, h.calls.apply[1].key); assert.equal(h.fact().current_actual_start_date, '2026-09-16');
    assert.equal(h.store.getActualStart('TEST-CASE').status, 'observed');
  });
  for (const status of ['applying', 'outcome_unknown', 'observation_failed', 'observing']) await test(`AS-${status} unresolved command is never cleared`, async () => {
    const h = actualHarness(), saved = { status, command: { payload: {} }, receipt: { case_no: 'TEST-CASE' } };
    h.store.setActualStart('TEST-CASE', saved); await h.functions.check(); assert.equal(h.store.getActualStart('TEST-CASE'), saved); assert.equal(h.calls.preview, 0);
  });
  await test('AS-locked cannot preview or clear a completed command', async () => {
    const h = actualHarness(), saved = { status: 'observed', receipt: { case_no: 'TEST-CASE' } };
    h.store.setActualStart('TEST-CASE', saved); h.context.query.service_data_locked = true;
    await h.functions.check(); assert.equal(h.store.getActualStart('TEST-CASE'), saved); assert.equal(h.calls.preview, 0);
  });
  await test('UX calendar displays service days without fabricated eight-hour labels', async () => {
    const h = datesHarness(), l = latestHarness(h); l.out.preview = null; l.out.precision = null; l.out.serviceMode = null;
    const v = l.view(); assert.equal(nodes(v, n => n.props.className === 'calendar-date-cell-badge' && text(n) === '服務日').length, 2);
    assert.equal(text(v).includes('8hr'), false); assert.equal(nodes(v, n => n.props['aria-label'] === '建議服務日期摘要').length, 0);
  });
  await refreshCases();
  const summary = { node: process.version, typescript: ts.version, total: records.length,
    passed: records.filter(r => r.status === 'passed').length, failed: records.filter(r => r.status === 'failed').length };
  console.log(JSON.stringify(summary)); if (summary.failed) process.exitCode = 1;
}
main().catch(error => { console.error(error); process.exitCode = 1; });
