import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm, mkdir } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { resolve, relative } from 'node:path';
import { pathToFileURL } from 'node:url';

const root = resolve(process.env.FINANCE_UI_ROOT ?? process.cwd());
const evidence = process.env.FINANCE_EVIDENCE_DIR;
assert(evidence, 'FINANCE_EVIDENCE_DIR is required');
assert.equal(process.env.REACT_ADMIN_ARTIFACT_BUILD, '1', 'Do not discover local .env files');
const require = createRequire(resolve(root, 'package.json'));
const { z } = await import(pathToFileURL(require.resolve('zod')).href);
assert(process.env.PLAYWRIGHT_PACKAGE_DIR, 'Install isolated CI browser tools first');
const browserRequire = createRequire(resolve(process.env.PLAYWRIGHT_PACKAGE_DIR, 'package.json'));
const { chromium } = browserRequire('playwright');
const { build, preview, loadConfigFromFile, mergeConfig } = await import(pathToFileURL(require.resolve('vite')).href);
const rowSchema = z.object({ caseNo: z.string(), amount: z.string().nullable(), status: z.array(z.string().nullable()), actions: z.array(z.string().nullable()) });
const wireFixtureSchema = z.object({
  digest: z.string(),
  fixtures: z.array(z.object({
    size: z.number().int(), orders: z.array(z.object({ case_no: z.string(), client_name: z.string() }).passthrough()),
    timelines: z.array(z.object({ case_no: z.string() }).passthrough()),
    accounting: z.array(z.tuple([z.string(), z.record(z.string(), z.unknown())])),
    notices: z.array(z.tuple([z.string(), z.array(z.unknown())])),
    expectedRows: z.array(rowSchema), expectedRefreshRows: z.array(rowSchema),
  })),
});
const data = wireFixtureSchema.parse(JSON.parse(await readFile(resolve(evidence, 'browser-fixtures.json'), 'utf8')));
const measurements = [];
const checks = [];
const tmp = await mkdtemp(resolve(root, '.finance-browser-'));
const prefix = `browser-${process.env.FINANCE_SIDE ?? 'unknown'}-${process.env.FINANCE_REPETITION ?? '0'}`;
let server;
let browser;
let completed = false;

function syntheticReply(url, fixture, accounting, notices) {
  const cursor = url.searchParams.get('after_case_no');
  function page(items) {
    const selected = items.filter(item => !cursor || item.case_no > cursor).slice(0, 13);
    const last = selected.at(-1)?.case_no;
    return { items: selected, next_cursor: last && items.some(item => item.case_no > last) ? last : null, etag: data.digest };
  }
  if (url.pathname === '/api/v1/orders/summaries') {
    const query = url.searchParams.get('query_text') ?? '';
    return page(fixture.orders.filter(order => !query || order.case_no.includes(query) || order.client_name.includes(query)));
  }
  if (url.pathname === '/api/orders/core-stage-timelines') {
    const codes = fixture.timelines[0]?.core_stages;
    assert(Array.isArray(codes), 'Synthetic timeline stages missing');
    return { ...page(fixture.timelines), stage_counts: Object.fromEntries(codes.map(stage => [stage.code, 0])), substatus_counts: {}, historical_lifecycle_counts: { unserved: 0, in_service: 0, service_completed: 0, accounting_completed: 0 } };
  }
  const parts = url.pathname.split('/');
  const caseNo = decodeURIComponent(parts.at(-1) === 'accounting' ? parts.at(-2) : parts.at(-1));
  if (url.pathname.endsWith('/accounting')) { assert(accounting.has(caseNo)); return accounting.get(caseNo); }
  if (url.pathname.includes('/payment-overdue-reminders/cases/')) { assert(notices.has(caseNo)); return notices.get(caseNo); }
  throw new Error(`Unexpected synthetic HTTP path ${url.pathname}`);
}

async function scenario(fixture, { denied = new Set(), token = 'synthetic-session' } = {}) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, timezoneId: 'Asia/Taipei' });
  const page = await context.newPage();
  const accounting = new Map(fixture.accounting);
  const notices = new Map(fixture.notices);
  const errors = [];
  const traces = [];
  let active = 0;
  let maxConcurrent = 0;
  page.on('pageerror', error => errors.push(String(error)));
  await context.route('**/api/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const trace = { path: url.pathname + url.search, started: performance.now(), ended: null, outcome: 'pending', status: null };
    traces.push(trace);
    active++;
    maxConcurrent = Math.max(maxConcurrent, active);
    try {
      assert.equal(request.method(), 'GET', 'Synthetic fixture is read-only');
      await new Promise(done => setTimeout(done, 20));
      const authorized = request.headers().authorization === 'Bearer synthetic-session';
      const status = authorized ? denied.has(url.pathname) ? 403 : 200 : 401;
      const payload = status === 200 ? { success: true, message: 'Synthetic only', error: null, data: syntheticReply(url, fixture, accounting, notices) } : { detail: 'Synthetic denied' };
      trace.status = status;
      await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) });
      trace.outcome = status === 200 ? 'success' : 'failure';
    } catch (error) {
      trace.outcome = 'failure';
      errors.push(String(error));
      await route.abort().catch(() => undefined);
    } finally { trace.ended = performance.now(); active--; }
  });
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) { errors.push(`External request blocked ${url.origin}`); await route.abort(); return; }
    await route.fallback();
  });
  await page.goto(`${origin}${base}${relative(root, tmp)}/perf.html`);
  await page.waitForFunction(() => typeof window.financeMount === 'function');
  await page.evaluate(value => { window.financeToken = value; }, token);

  async function rows() {
    return page.locator('[data-accounting-case]').evaluateAll(elements => elements.map(row => ({
      caseNo: row.getAttribute('data-accounting-case'), amount: row.querySelectorAll('td')[3]?.textContent ?? null,
      status: Array.from(row.querySelector('.finance-ongoing-item')?.children ?? []).map(element => element.textContent),
      actions: Array.from(row.querySelectorAll('.finance-ongoing-actions button')).map(element => element.textContent),
    })));
  }
  async function settled() {
    await page.getByRole('button', { name: '查詢案件', exact: true }).waitFor();
    await page.waitForFunction(() => !document.querySelector('button.finance-btn-primary')?.disabled, undefined, { timeout: 30000 });
    assert.equal(active, 0, 'All synthetic HTTP requests must terminate');
    assert.deepEqual(errors, []);
  }
  async function measure(phase, expected) {
    traces.length = 0;
    maxConcurrent = 0;
    await page.evaluate(({ phase, money }) => {
      const start = performance.now();
      window.financeTiming = { firstRowMs: -1, start };
      window.financeObserver = new MutationObserver(() => {
        const row = document.querySelector('[data-accounting-case="SYN-0002"]');
        if (window.financeTiming.firstRowMs < 0 && row?.textContent?.includes(money) && row.textContent.includes('通知')) window.financeTiming.firstRowMs = performance.now() - start;
      });
      window.financeObserver.observe(document.body, { subtree: true, childList: true, characterData: true });
      if (phase === 'initial') window.financeMount();
      else document.querySelector('button.finance-btn-primary').click();
    }, { phase, money: expected[0].amount });
    await settled();
    const timing = await page.evaluate(() => {
      window.financeObserver.disconnect();
      return { firstRowMs: window.financeTiming.firstRowMs, completeMs: performance.now() - window.financeTiming.start };
    });
    assert(timing.firstRowMs >= 0, 'First complete correct row must be observed');
    assert.deepEqual(await rows(), expected);
    assert.equal(traces.length, 2 * Math.ceil(fixture.size / 13) + 2 * (fixture.size - 1), 'Consume every synthetic summary/timeline page and eligible accounting/notice response');
    assert(traces.every(trace => trace.outcome === 'success' && trace.ended >= trace.started));
    measurements.push({ scenario: phase, size: fixture.size, ...timing, requests: traces.length, success: traces.filter(trace => trace.outcome === 'success').length, failures: traces.filter(trace => trace.outcome === 'failure').length, maxConcurrent, trace: structuredClone(traces) });
  }
  return { page, context, rows, settled, measure, accounting, traces, errors, mount: async () => { await page.evaluate(() => window.financeMount()); await settled(); } };
}

let origin;
let base;
try {
  await writeFile(resolve(tmp, 'perf.html'), '<!doctype html><html><head><meta charset="UTF-8"></head><body><div id="root"></div><script type="module" src="./entry.tsx"></script></body></html>');
  await writeFile(resolve(tmp, 'entry.tsx'), `import React from 'react';
import {createRoot} from 'react-dom/client';
import {FinanceCaseList} from '/src/components/FinanceCaseList';
import {sessionClient} from '/src/api/auth/session_client';
sessionClient.getToken = () => window.financeToken;
const root=createRoot(document.getElementById('root'));
let revision=0;
const render=()=>root.render(<FinanceCaseList revision={revision} onCase={(caseNo, stage)=>{window.financeSelected={caseNo,stage};}}/>);
window.financeMount=render;
window.financeRefresh=()=>{revision++;render();};
`);
  const loaded = await loadConfigFromFile({ command: 'build', mode: 'production' }, resolve(root, 'vite.config.ts'));
  assert(loaded, 'Must inherit production Vite config');
  const config = mergeConfig(loaded.config, { root, configFile: false, envDir: false, build: { outDir: resolve(tmp, 'dist'), emptyOutDir: true, rollupOptions: { input: resolve(tmp, 'perf.html') } }, preview: { host: '127.0.0.1', port: 0, strictPort: false } });
  await build(config);
  server = await preview(config);
  const address = server.httpServer.address();
  assert(address && typeof address !== 'string');
  origin = `http://127.0.0.1:${address.port}`;
  base = typeof config.base === 'string' ? config.base : '/';
  browser = await chromium.launch({ headless: true });
  for (const fixture of data.fixtures) {
    const current = await scenario(fixture);
    try {
      await current.measure('initial', fixture.expectedRows);
      const old = current.accounting.get('SYN-0002');
      assert(old);
      current.accounting.set('SYN-0002', { ...old, staff_receivable_ntd: 76544 });
      await current.measure('manual-refresh', fixture.expectedRefreshRows);
      if (fixture.size === 16) {
        await current.page.getByRole('tab', { name: '所有案件', exact: true }).click();
        assert.equal((await current.rows()).length, 16);
        await current.page.getByLabel('目前階段', { exact: true }).selectOption('second');
        assert.deepEqual((await current.rows()).map(row => row.caseNo), ['SYN-0002', 'SYN-0006', 'SYN-0010', 'SYN-0014']);
        await current.page.getByLabel('時效篩選', { exact: true }).selectOption('future');
        assert.deepEqual((await current.rows()).map(row => row.caseNo), ['SYN-0006']);
        await current.page.getByLabel('目前階段', { exact: true }).selectOption('all');
        await current.page.getByLabel('時效篩選', { exact: true }).selectOption('all');
        await current.page.getByPlaceholder('案件編號、客戶或月嫂').fill('SYN-0004');
        await current.page.getByRole('button', { name: '查詢案件', exact: true }).click();
        await current.settled();
        assert.deepEqual((await current.rows()).map(row => row.caseNo), ['SYN-0004']);
        await current.page.getByRole('button', { name: '發出提醒', exact: true }).click();
        assert.deepEqual(await current.page.evaluate(() => window.financeSelected), { caseNo: 'SYN-0004', stage: 'deposit' });
        checks.push('all/stage/timing/exact-search/amounts/reminder-action');
      }
    } finally { await current.context.close(); }
  }
  const small = data.fixtures.find(fixture => fixture.size === 16);
  assert(small);
  for (const mode of ['individual-denied', 'list-denied', 'no-token']) {
    const denied = new Set(mode === 'individual-denied' ? ['/api/v1/finance-import/cases/SYN-0002/accounting', '/api/v1/line/payment-overdue-reminders/cases/SYN-0004'] : mode === 'list-denied' ? ['/api/v1/orders/summaries'] : []);
    const current = await scenario(small, { denied });
    try {
      await current.mount();
      if (mode === 'no-token') {
        await current.page.evaluate(() => { window.financeToken = null; window.financeRefresh(); });
        await current.page.getByRole('alert').waitFor();
        await current.settled();
      }
      if (mode === 'individual-denied') {
        const rows = await current.rows();
        const accounting = rows.find(row => row.caseNo === 'SYN-0002');
        const notice = rows.find(row => row.caseNo === 'SYN-0004');
        assert(accounting?.status.includes('帳務來源待確認'));
        assert(notice?.status.includes('通知紀錄待確認'));
        assert(!accounting.actions.includes('發出提醒'));
        assert(!notice.actions.includes('發出提醒'));
        assert.equal(current.traces.filter(trace => trace.outcome === 'failure').length, 2);
      } else {
        assert.equal(await current.page.getByRole('alert').count(), 1);
        assert.equal((await current.rows()).length, 0);
      }
      checks.push(mode);
    } finally { await current.context.close(); }
  }
  const capture = await scenario(small);
  try {
    await capture.context.tracing.start({ screenshots: true, snapshots: true, sources: true });
    await capture.mount();
    assert.deepEqual(await capture.rows(), small.expectedRows);
    await capture.page.screenshot({ path: resolve(evidence, `${prefix}.png`), fullPage: true });
    await capture.context.tracing.stop({ path: resolve(evidence, `${prefix}-untimed-trace.zip`) });
  } finally { await capture.context.close(); }
  completed = true;
} finally {
  try {
    await mkdir(evidence, { recursive: true });
    await writeFile(resolve(evidence, `${prefix}.json`), JSON.stringify({ surface: 'Real Chromium, production FinanceCaseList and typed HTTP clients; synthetic intercepted HTTP only. Real API/DB and formal end-to-end not_run.', sha: process.env.FINANCE_CHECKOUT_SHA, browser: browser?.version(), node: process.version, completed, timedTracing: false, measurements, checks }, null, 2));
  } finally {
    try { await browser?.close(); }
    finally {
      try { if (server) await new Promise((done, reject) => server.httpServer.close(error => error ? reject(error) : done())); }
      finally { await rm(tmp, { recursive: true, force: true }); }
    }
  }
}
