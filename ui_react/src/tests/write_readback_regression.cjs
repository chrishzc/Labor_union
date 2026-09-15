'use strict';
/* No installs, network calls, app boot, credentials, or DB access.
 * Executes verbatim named source fragments with mocked HTTP/state boundaries.
 * This is NOT a React DOM, API integration, or MySQL persistence suite.
 * Run from repo root: node ui_react/src/tests/write_readback_regression.cjs
 * Requires the existing TypeScript devDependency; never installs anything.
 * TYPESCRIPT_PATH may point to an already installed TypeScript package.
 */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { randomUUID } = require('node:crypto');
const ts = require(process.env.TYPESCRIPT_PATH || 'typescript');
const root = path.resolve(__dirname, '..');
const reports=[];
// Extract the named declarations from the checked-out production source.
// These are function-boundary tests, not React DOM/API/MySQL integration tests.
const sources = {
  candidate_command: ['api/scheduling/candidate_contact_pool_client.ts', [
    'canonicalCaseNo', 'canonicalCandidateWillingnessCommand', 'createCandidateWillingnessCommand',
  ]],
  candidate_handlers: ['components/OrderCandidateContactStatusPanel.tsx', ['submitInformation', 'submitWillingness']],
  service_dates_flow: ['adapters/orders/order_mutation_adapter.ts', ['applyServiceDatesFlow', 'retryServiceDatesObservationFlow']],
  service_dates_observed: ['adapters/orders/order_mutation_flow_store.ts', ['setServiceDatesObserved']],
  date_comparison: ['adapters/orders/order_mutation_flow_store.ts', ['areDateArraysEqual']],
  typed_errors: ['api/shared/typed_errors.ts', ['ApiError', 'ApiNetworkError', 'ApiTimeoutError', 'ApiHttpError']],
};
function source(name) {
  const [relative, symbols] = sources[name];
  const file = path.join(root, relative);
  const tree = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true);
  return symbols.map(symbol => {
    const matches = [];
    function visit(node) {
      if ((ts.isFunctionDeclaration(node) || ts.isClassDeclaration(node)
        || ts.isVariableDeclaration(node) || ts.isMethodDeclaration(node)) && node.name?.getText(tree) === symbol) {
        matches.push(node);
      }
      ts.forEachChild(node, visit);
    }
    visit(tree);
    assert.equal(matches.length, 1, `${relative}: expected one ${symbol}`);
    const node = matches[0];
    return ts.isVariableDeclaration(node) ? `const ${node.getText(tree)};` : node.getText(tree);
  }).join('\n');
}
function compile(text,names,env={}) {
 const output=ts.transpileModule(text.replace(/\bexport\s+(?=(?:async\s+)?function|abstract\s+class|class)/g,''),{
  compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.None},reportDiagnostics:true,
 });
 const errors=(output.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error);
 if(errors.length) throw new Error(ts.formatDiagnostics(errors,{getCanonicalFileName:f=>f,getCurrentDirectory:()=>root,getNewLine:()=> '\n'}));
 const context=vm.createContext({Error,Map,Set,Promise,AbortController,console,crypto:{randomUUID},...env});
 return vm.runInContext(`(function(){${output.outputText}\nreturn {${names.join(',')}};})()`,context,{timeout:1000});
}
const errors=compile(source('typed_errors'),['ApiHttpError','ApiNetworkError','ApiTimeoutError']);
const {ApiHttpError}=errors;
const msg=(e,f='操作失敗')=>e instanceof Error&&e.message.trim()?e.message.trim():f;
const copy=x=>JSON.parse(JSON.stringify(x));
function setters(names,out){return Object.fromEntries(names.map(n=>['set'+n,v=>{const k=n[0].toLowerCase()+n.slice(1);out[k]=typeof v==='function'?v(out[k]):v;}]))}
async function test(id,area,name,fn) {
 try {const detail=await fn(); reports.push({id,area,name,status:'passed',detail:detail||null});}
 catch(e){reports.push({id,area,name,status:'failed',error:e.message});}
 const r=reports.at(-1); console.log(`${r.status.toUpperCase()} ${id} ${name}${r.error?' — '+r.error:''}`);
}


function candidateEnv(apiError, info=false) {
 const out={state:{status:'ready',data:{candidates:[{id:7,willingness:'pending'}]}}},flows=new Map(),apiCalls=[];
 const key=(c,id,type)=>[c,id,type||''].join(':');
 const store={
  getCandidateWillingness:(c,id)=>flows.get(key(c,id)),
  setCandidateWillingness:(c,s)=>flows.set(key(c,s.command.candidateId),s),
  clearCandidateWillingness:(c,id)=>flows.delete(key(c,id)),
  getCandidateInformation:(c,id,type)=>flows.get(key(c,id,type)),
  setCandidateInformation:(c,s)=>flows.set(key(c,s.command.candidateId,s.command.infoType),s),
  clearCandidateInformation:(c,id,type)=>flows.delete(key(c,id,type)),
 };
 const activeCaseNo={current:'TEST-CASE'};
 const env={caseNo:'TEST-CASE',state:out.state,orderMutationFlowStore:store,mounted:{current:true},activeCaseNo,
  informationInFlight:{current:new Set()},...errors,...setters(['State'],out),errorMessage:msg,
  mutationIdentity:()=>({actor:'TEST-ACTOR',token:'unused'}),
  candidateContactPoolClient:{
   recordWillingness:async c=>{apiCalls.push(c);if(apiError)throw apiError;return {event_id:11,status:'recorded'}},
   sendInformation:async c=>{apiCalls.push(c);if(apiError)throw apiError;return {event_id:11,line_task_id:12,status:'queued'}},
  },
  observeWillingness:async id=>{store.clearCandidateWillingness('TEST-CASE',id);out.observed=true;},
  observeInformation:async c=>{store.clearCandidateInformation(c.caseNo,c.candidateId,c.infoType);out.observed=true;},
 };
 const functions=compile(source('candidate_command')+'\n'+source('candidate_handlers'),
  ['submitWillingness','submitInformation'],env);
 return {out,flows,apiCalls,functions,activeCaseNo};
}

class MutationError extends Error {constructor(x){super(x.message);Object.assign(this,x)}}
function dateEnv(change={},queryError=null,receiptChange={}) {
 const dateList=['2026-09-15','2026-09-16'];
 const receipt={case_no:'TEST-CASE',confirmed_version:2,order_version:4,scheduling_version:3,service_dates:dateList,preview_fingerprint:'a'.repeat(64),...receiptChange};
 const query={case_no:'TEST-CASE',current_version:2,order_version:4,scheduling_version:3,contracted_service_days:2,suggested_dates:[],selectable_dates:[...dateList],current_dates:[...dateList],...change};
 const draft={caseNo:'TEST-CASE',status:'preview_ready',selectedDates:[...dateList],reason:'TEST REASON',previewView:{order_version:4,scheduling_version:3,preview_fingerprint:'a'.repeat(64)},receiptView:null,idempotencyKey:'synthetic-key'};
 const observedClass=compile('class Store {\n'+source('service_dates_observed')+'\n}', ['Store'],{
  areDateArraysEqual:compile(source('date_comparison'), ['areDateArraysEqual']).areDateArraysEqual,
 }).Store;
 const store=new observedClass();
 store.getOrCreateServiceDatesDraft=()=>draft;store.notify=()=>{};
 for(const [method,status] of Object.entries({ApplyPending:'apply_pending',RequeryLoading:'requery_loading',OutcomeUnknown:'outcome_unknown',Stale:'stale',TypedError:'typed_error',ObservationFailed:'observation_failed'})){
  store['setServiceDates'+method]=(c,e)=>{draft.status=status;draft.error=e||null;};
 }
 store.setServiceDatesReceiptReceived=(c,r)=>{draft.receiptView=r;draft.status='receipt_received';};
 const calls={apply:0,query:0};
 const funcs=compile(source('service_dates_flow'),['applyServiceDatesFlow','retryServiceDatesObservationFlow'],{
  orderMutationFlowStore:store,OrderMutationValidationError:MutationError,OrderMutationConflictError:MutationError,
  normalizeFlowError:e=>e,isOutcomeUnknownError:e=>e instanceof errors.ApiNetworkError,isStaleConflictError:()=>false,
  ordersMutationClient:{applyServiceDates:async()=>{calls.apply++;return receipt},getServiceDates:async()=>{calls.query++;if(queryError)throw queryError;return query}},
 });
 return {draft,receipt,query,calls,funcs};
}

async function main(){
 await test('C01','候選意願','無意願空白理由：不送 API，並顯示錯誤而不是 rejected promise',async()=>{
  const e=candidateEnv(); let rejection=null;try{await e.functions.submitWillingness(7,'unwilling','   ')}catch(err){rejection=err.message}
  assert.equal(e.apiCalls.length,0);assert.equal(rejection,null,`未接住的錯誤：${rejection}`);assert.equal(e.out.state.status,'error');assert.match(e.out.state.message,/理由/);
 });
 for(const status of [403,409,422]) await test('C'+status,'候選意願',`HTTP ${status} 拒絕必須留下可見錯誤`,async()=>{
  const e=candidateEnv(new ApiHttpError(status,'TEST_REJECTION',`測試拒絕 ${status}`));await e.functions.submitWillingness(7,'unwilling','TEST REASON');
  assert.equal(e.apiCalls.length,1);assert.equal(e.flows.size,0);assert.equal(e.out.state.status,'error','清除 flow 後未留下畫面錯誤');assert.match(e.out.state.message,/測試拒絕/);
 });
 for(const status of [403,409]) await test('I'+status,'寄送資訊',`HTTP ${status} 拒絕寄送必須留下可見錯誤`,async()=>{
  const e=candidateEnv(new ApiHttpError(status,'TEST_REJECTION',`測試拒絕 ${status}`),true);await e.functions.submitInformation({caseNo:'TEST-CASE',candidateId:7,infoType:1,eventKey:'synthetic-key'});
  assert.equal(e.apiCalls.length,1);assert.equal(e.flows.size,0);assert.equal(e.out.state.status,'error','寄送 flow 消失但沒有畫面錯誤');
 });
 await test('C02','候選意願','連線／500 未知结果保留原命令，不當成成功',async()=>{
  const e=candidateEnv(new ApiHttpError(500,'TEST_UNKNOWN','結果未知'));await e.functions.submitWillingness(7,'unwilling','TEST REASON');
  assert.equal([...e.flows.values()][0].status,'outcome_unknown');assert.equal(e.out.observed,undefined);
 });
 await test('C03','候選意願','合法願意命令仍只送出一次並進入回讀',async()=>{
  const e=candidateEnv();await e.functions.submitWillingness(7,'willing','');assert.equal(e.apiCalls.length,1);assert.equal(e.out.observed,true);assert.equal(e.apiCalls[0].reason,'人工補登願意');
 });
 await test('C04','候選意願','舊案件延遲拒絕不能把錯誤寫到新案件畫面',async()=>{const e=candidateEnv(new ApiHttpError(403,'TEST_REJECTION','拒絕'));const p=e.functions.submitWillingness(7,'unwilling','TEST REASON');e.activeCaseNo.current='OTHER-CASE';await p;assert.equal(e.out.state.status,'ready');assert.equal(e.flows.size,0)});
 const badDates=[
  ['D01','舊確認版本',{current_version:1}],['D02','同版本但日期錯誤',{current_dates:['2026-09-20','2026-09-21']}],
  ['D03','其他案件',{case_no:'OTHER-CASE'}],['D04','訂單版本落後',{order_version:3}],['D05','排班版本落後',{scheduling_version:2}],

 ];
 for(const [id,name,change] of badDates) await test(id,'服務日期',`${name}不能標成 observed`,async()=>{
  const e=dateEnv(change);try{await e.funcs.applyServiceDatesFlow('TEST-CASE')}catch{}
  assert.equal(e.draft.status,'observation_failed',`實際狀態 ${e.draft.status}，回讀 ${JSON.stringify(e.query)}`);
  assert.ok(e.draft.receiptView);assert.equal(e.calls.apply,1);
 });
 await test('D06','服務日期','較新版本仍是相同服務日期，不應被誤判未保存',async()=>{const e=dateEnv({current_version:3});await e.funcs.applyServiceDatesFlow('TEST-CASE');assert.equal(e.draft.status,'observed');assert.equal(e.draft.queryView.current_version,3)});
 await test('D07','服務日期','正確日期／版本可以 observed',async()=>{const e=dateEnv();await e.funcs.applyServiceDatesFlow('TEST-CASE');assert.equal(e.draft.status,'observed');assert.equal(e.calls.apply,1)});
 await test('D08','服務日期','GET 失敗保留收據且不自動重送 Apply',async()=>{const e=dateEnv({},new Error('GET FAILED'));try{await e.funcs.applyServiceDatesFlow('TEST-CASE')}catch{}assert.equal(e.draft.status,'observation_failed');assert.ok(e.draft.receiptView);assert.equal(e.calls.apply,1)});
 await test('D09','服務日期','只重讀仍須拒絕舊日期，不可繞過相同檢查',async()=>{
  const e=dateEnv({current_version:1});e.draft.receiptView=e.receipt;e.draft.status='observation_failed';try{await e.funcs.retryServiceDatesObservationFlow('TEST-CASE')}catch{}
  assert.equal(e.draft.status,'observation_failed');assert.equal(e.calls.apply,0);assert.equal(e.calls.query,1);
 });
 await test('D10','服務日期','只重讀正確結果成功且不送 Apply',async()=>{
  const e=dateEnv();e.draft.receiptView=e.receipt;e.draft.status='observation_failed';await e.funcs.retryServiceDatesObservationFlow('TEST-CASE');assert.equal(e.draft.status,'observed');assert.equal(e.calls.apply,0);
 });
 await test('D11','服務日期','指紋不符不能 observed',async()=>{const e=dateEnv({},null,{preview_fingerprint:'b'.repeat(64)});try{await e.funcs.applyServiceDatesFlow('TEST-CASE')}catch{}assert.equal(e.draft.status,'observation_failed');assert.equal(e.calls.query,0)});
 const totals = {passed: reports.filter(x => x.status === 'passed').length, failed: reports.filter(x => x.status === 'failed').length};
 console.log(JSON.stringify({node: process.version, typescript: ts.version,
   boundary: 'Production declarations; mocked HTTP/state; no React DOM, live API or MySQL.', totals, tests: reports}, null, 2));
 process.exitCode = totals.failed ? 1 : 0;
}
main().catch(error => { console.error(error); process.exitCode = 2; });
