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
  return { store, draft, receipt, query, calls, functions, api };
}
function latestHarness(h, next = h.query, failure = null) {
  const out = { queryView: h.draft.queryView, selectedDates: [...h.draft.selectedDates], precision: { actual_start_date: 'OLD', actual_end_date: 'OLD' },
    serviceMode: '連續服務', preview: { service_dates: ['OLD'] }, working: null, error: null, success: null,
    calculationBasis: { date: 'OLD', confirmed: true }, basisNotice: 'OLD', hasManualChanges: true };
  const renderedCaseNo = { current: 'TEST-CASE' }, actionInFlight = { current: new Set() };
  const api = { getServiceDates: async () => { h.calls.query++; if (failure) throw failure; return copy(next); } };
  const env = { caseNo: 'TEST-CASE', orderMutationFlowStore: h.store, ordersMutationClient: api,
    recoveryFromServiceDatesDraft: h.functions.recoveryFromServiceDatesDraft, renderedCaseNo, actionInFlight,
    selectServiceDates: (c, d) => h.store.updateServiceDatesSelection(c, d), updateServiceDatesReason: (c, r) => h.store.updateServiceDatesReason(c, r),
    AUTOMATIC_CONFIRMATION_REASON: '確認正式服務日期', errorMessage: message, onObserved: () => {},
    ...setters(out, ['Working', 'Error', 'Success', 'Preview', 'QueryView', 'SelectedDates', 'Precision', 'ServiceMode', 'CalculationBasis', 'BasisNotice', 'HasManualChanges']),
  };
  const load = () => compile(source('dates', 'loadLatestDates'), ['loadLatestDates'], env).functions.loadLatestDates();
  const view = () => {
    const recovery = h.functions.recoveryFromServiceDatesDraft('TEST-CASE');
    const derived = compile(source('dates', 'requiredDateCount', 'canPreview', 'canApply'), ['requiredDateCount', 'canPreview', 'canApply'], {
      ...out, isRecoveryActive: recovery?.caseNo === 'TEST-CASE',
    }).functions;
    return render('dates', 'OrderServiceDatesPanel', { ...out, ...derived, caseNo: 'TEST-CASE', recovery, isRecoveryActive: recovery?.caseNo === 'TEST-CASE',
      loadAndCalculate: () => {}, retryApply: () => {}, retryObservation: () => {}, loadLatestDates: load,
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
  const summary = { node: process.version, typescript: ts.version, total: records.length,
    passed: records.filter(r => r.status === 'passed').length, failed: records.filter(r => r.status === 'failed').length };
  console.log(JSON.stringify(summary)); if (summary.failed) process.exitCode = 1;
}
main().catch(error => { console.error(error); process.exitCode = 1; });
