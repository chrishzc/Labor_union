import { mkdirSync, writeFileSync } from 'node:fs';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FinanceCaseList } from '../../../../../../../components/FinanceCaseList';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import type { OrderSummaryItem } from '../../../../../../../api/orders/order_query_schemas';
import { CORE_STAGE_CODES, OrderCoreStageTimelinePageSchema, SUBSTATUS_BY_STAGE_STATUS, type OrderCoreStageTimeline } from '../../../../../../../api/orders/order_core_stage_projection_schemas';
import type { CaseAccounting } from '../../../../../../../api/finance_import/finance_accounting_client';
import type { CasePaymentReminder } from '../../../../../../../api/line_order_groups/payment_overdue_reminder_client';

type Fixture = { orders: OrderSummaryItem[]; timelines: OrderCoreStageTimeline[]; accounting: Map<string, CaseAccounting>; notices: Map<string, CasePaymentReminder[]> };
type RequestTrace = { path: string; started: number; ended?: number; outcome?: 'success' | 'failure' | 'abort' };
type Measurement = { scenario: string; size: number; firstRowMs: number; completeMs: number; requests: number; success: number; failures: number; aborted: number; maxConcurrent: number; rows: string[]; trace: RequestTrace[] };
const measurements: Measurement[] = [];
const digest = 'a'.repeat(64);
const stages = ['deposit', 'first', 'second', 'scheme'] satisfies NonNullable<CaseAccounting['collection_progress']>['stage'][];
let fixture: Fixture;
let traces: RequestTrace[];
let denied: Set<string>;
let fixtureErrors: unknown[];
let active = 0;
let maxConcurrent = 0;
let latency = 20;

function synthetic(size: number): Fixture {
  const orders: OrderSummaryItem[] = [];
  const timelines: OrderCoreStageTimeline[] = [];
  const accounting = new Map<string, CaseAccounting>();
  const notices = new Map<string, CasePaymentReminder[]>();
  for (let index = 0; index < size; index++) {
    const case_no = `SYN-${String(index).padStart(4, '0')}`;
    const stage = stages[index % stages.length];
    if (!stage) throw new Error('Missing synthetic stage');
    orders.push({ case_no, client_name: `合成客戶${index % 3}`, order_status: '訂單成立', staff_name: '合成人員', identity_status: null, start_date: null, end_date: null, actual_start_date: null, actual_end_date: null, service_days: null, total_employer_self_pay_payable: null });
    timelines.push({ case_no, base_revision: 1, lifecycle_status: '訂單成立', branch_type: 'normal', current_core_stage_code: index === 0 ? 'external_signing_completion' : 'deposit_settlement', current_core_stage_ordinal: index === 0 ? 7 : 8, historical_current_owner_stage_code: null, historical_current_owner_stage_ordinal: null, source_projection_digest: digest,
      core_stages: CORE_STAGE_CODES.map((code, ordinal) => {
        const status = ordinal < (index === 0 ? 6 : 7) ? 'completed' : ordinal === (index === 0 ? 6 : 7) ? 'in_progress' : 'not_started';
        const substatus_code = SUBSTATUS_BY_STAGE_STATUS[code][status];
        if (!substatus_code) throw new Error(`Missing stage mapping ${code}`);
        return { ordinal: ordinal + 1, code, label: code, owner: 'Synthetic owner', status, substatus_code, source: { owner: 'Synthetic owner', identity: case_no, version: 1 }, occurred_at: null, blockers: [], warnings: [], available_read_actions: [], availability_reason: null };
      }),
    });
    accounting.set(case_no, { case_no, client_name: `合成客戶${index % 3}`, receivable_ntd: 5000, received_ntd: 1000, payable_ntd: 9000, paid_ntd: 0, staff_receivable_ntd: 10000 + index, pending_warning_count: 0, warnings: [], transactions: [], client_items: [], staff_items: [], ongoing_completed: index === 1,
      collection_progress: { stage, sources_complete: index % 7 !== 0, expected_ntd: 5000, received_ntd: 1000, remaining_ntd: 4000, due_date: index % 3 === 0 ? '2099-12-31' : index % 3 === 1 ? '2000-01-01' : null } });
    notices.set(case_no, stage === 'scheme' ? [] : [{ case_no, payment_stage: stage, payment: { case_no, payment_stage: stage, obligation_identity: `${case_no}:payment`, projection_version: 1, obligation_event_id: index + 1, due_date: '2000-01-01', remaining_amount_ntd: 4000 }, recipient_label: '合成收件者', can_send: true, unavailable_reason: null, message: '合成通知', history: [] }]);
  }
  return { orders, timelines, accounting, notices };
}
function page<T extends { case_no: string }>(items: T[], cursor: string | null): { items: T[]; next_cursor: string | null; etag: string } {
  const selected = items.filter(item => !cursor || item.case_no > cursor).slice(0, 13);
  return { items: selected, next_cursor: selected.length && items.some(item => item.case_no > (selected.at(-1)?.case_no ?? '')) ? selected.at(-1)?.case_no ?? null : null, etag: digest };
}
function reply(url: URL): unknown {
  const cursor = url.searchParams.get('after_case_no');
  if (url.pathname === '/api/v1/orders/summaries') {
    const query = url.searchParams.get('query_text') ?? '';
    return page(fixture.orders.filter(order => !query || order.case_no.includes(query) || order.client_name.includes(query)), cursor);
  }
  if (url.pathname === '/api/orders/core-stage-timelines') {
    return OrderCoreStageTimelinePageSchema.parse({ ...page(fixture.timelines, cursor), stage_counts: Object.fromEntries(CORE_STAGE_CODES.map(code => [code, 0])), substatus_counts: {}, historical_lifecycle_counts: { unserved: 0, in_service: 0, service_completed: 0, accounting_completed: 0 } });
  }
  const caseNo = decodeURIComponent(url.pathname.split('/').at(-1) === 'accounting' ? url.pathname.split('/').at(-2) ?? '' : url.pathname.split('/').at(-1) ?? '');
  if (url.pathname.endsWith('/accounting')) {
    const data = fixture.accounting.get(caseNo);
    if (!data) throw new Error(`Missing synthetic accounting ${caseNo}`);
    return data;
  }
  if (url.pathname.includes('/payment-overdue-reminders/cases/')) {
    const data = fixture.notices.get(caseNo);
    if (!data) throw new Error(`Missing synthetic notices ${caseNo}`);
    return data;
  }
  throw new Error(`Unexpected synthetic request ${url.pathname}`);
}
async function syntheticFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://synthetic.invalid');
  if (init?.method && init.method !== 'GET') throw new Error('Synthetic fixture is read-only');
  const trace: RequestTrace = { path: url.pathname + url.search, started: performance.now() };
  traces.push(trace);
  active++;
  maxConcurrent = Math.max(maxConcurrent, active);
  try {
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(resolve, latency);
      init?.signal?.addEventListener('abort', () => { clearTimeout(timer); reject(new DOMException('Synthetic abort', 'AbortError')); }, { once: true });
      if (init?.signal?.aborted) { clearTimeout(timer); reject(new DOMException('Synthetic abort', 'AbortError')); }
    });
    if (denied.has(url.pathname)) {
      trace.outcome = 'failure';
      return new Response(JSON.stringify({ detail: 'Synthetic denied' }), { status: 403, headers: { 'Content-Type': 'application/json' } });
    }
    const data = reply(url);
    trace.outcome = 'success';
    return new Response(JSON.stringify({ success: true, message: 'Synthetic only', data, error: null }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      trace.outcome = 'abort';
    } else {
      trace.outcome = 'failure';
      fixtureErrors.push(error);
    }
    throw error;
  } finally {
    active--;
    trace.ended = performance.now();
  }
}
function rowIds(): string[] { return Array.from(document.querySelectorAll('[data-accounting-case]')).map(row => row.getAttribute('data-accounting-case') ?? ''); }
async function loaded(): Promise<void> {
  await waitFor(() => expect(screen.getByRole('button', { name: '查詢案件' })).toBeEnabled(), { timeout: 15000, interval: 5 });
  expect(fixtureErrors).toEqual([]);
}
type VisibleRow = { caseNo: string; amount: string | null; status: (string | null)[]; actions: (string | null)[] };
function expectedRows(size: number, updatedAmount?: number): VisibleRow[] {
  return Array.from({ length: size - 2 }, (_, offset) => {
    const index = offset + 2;
    const caseNo = `SYN-${String(index).padStart(4, '0')}`;
    const label = ['訂金', '第一期', '第二期', '設定補助退款方案'][index % 4];
    const known = index % 7 !== 0;
    const scheme = index % 4 === 3;
    const date = index % 3 === 0 ? '2099-12-31' : index % 3 === 1 ? '2000-01-01' : null;
    const state = date === null ? '日期待確認' : date === '2099-12-31' ? '未到期' : '逾期';
    const status = !known ? [`${label}來源待確認`, scheme ? '未設定' : '來源待確認']
      : scheme ? ['設定補助退款方案', '未設定']
      : [`待收${label}`, state, '待收 NT$ 4,000', date ? `原到期日 ${date}` : '到期日待確認', '部分已收 NT$ 1,000', '尚無成功通知紀錄'];
    return { caseNo, amount: `NT$ ${(index === 2 && updatedAmount !== undefined ? updatedAmount : 10000 + index).toLocaleString('zh-TW')}`, status, actions: known && !scheme ? ['查看案件', '發出提醒'] : ['查看案件'] };
  });
}
function visibleRows(): VisibleRow[] {
  return Array.from(document.querySelectorAll('[data-accounting-case]')).map(row => ({
    caseNo: row.getAttribute('data-accounting-case') ?? '',
    amount: row.querySelectorAll('td')[3]?.textContent ?? null,
    status: Array.from(row.querySelector('.finance-ongoing-item')?.children ?? []).map(element => element.textContent),
    actions: Array.from(row.querySelectorAll('.finance-ongoing-actions button')).map(element => element.textContent),
  }));
}
async function measure(scenario: string, size: number, action: () => void, updatedAmount?: number): Promise<void> {
  const expectedMoney = `NT$ ${(updatedAmount ?? 10002).toLocaleString('zh-TW')}`;
  traces = [];
  maxConcurrent = 0;
  const start = performance.now();
  let firstRowMs = -1;
  const observer = new MutationObserver(() => {
    const target = document.querySelector('[data-accounting-case="SYN-0002"]');
    if (firstRowMs < 0 && target?.textContent?.includes(expectedMoney) && target.textContent.includes('通知')) firstRowMs = performance.now() - start;
  });
  observer.observe(document.body, { subtree: true, childList: true, characterData: true });
  action();
  await loaded();
  observer.disconnect();
  const completeMs = performance.now() - start;
  expect(firstRowMs).toBeGreaterThanOrEqual(0);
  expect(active).toBe(0);
  expect(traces.length).toBeGreaterThan(0);
  for (const trace of traces) {
    expect(trace.ended).toBeGreaterThanOrEqual(trace.started);
    expect(trace.outcome).toBe('success');
  }
  expect(visibleRows()).toEqual(expectedRows(size, updatedAmount));
  const result: Measurement = { scenario, size, firstRowMs, completeMs, requests: traces.length, success: traces.filter(trace => trace.outcome === 'success').length, failures: traces.filter(trace => trace.outcome === 'failure').length, aborted: traces.filter(trace => trace.outcome === 'abort').length, maxConcurrent, rows: rowIds(), trace: structuredClone(traces) };
  measurements.push(result);
  console.info(`FINANCE_MEASUREMENT ${JSON.stringify(result)}`);
}
beforeEach(() => {
  fixture = synthetic(16);
  traces = [];
  denied = new Set();
  fixtureErrors = [];
  active = 0;
  maxConcurrent = 0;
  latency = 20;
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-11-28T04:00:00Z'));
  vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-session');
  vi.stubGlobal('fetch', syntheticFetch);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });
afterAll(() => {
  if (!process.env.FINANCE_EVIDENCE_DIR) return;
  mkdirSync(process.env.FINANCE_EVIDENCE_DIR, { recursive: true });
  writeFileSync(`${process.env.FINANCE_EVIDENCE_DIR}/frontend-${process.env.FINANCE_SIDE ?? 'unknown'}-${process.env.FINANCE_REPETITION ?? '0'}.json`, JSON.stringify({ surface: 'happy-dom real component and typed HTTP clients; synthetic fetch; browser/API/DB end-to-end not_run', sha: process.env.FINANCE_CHECKOUT_SHA, node: process.version, measurements }, null, 2));
});

describe('Finance case list synthetic behavior and latency', () => {
  for (const size of [16, 160]) {
    it(`records complete work for ${size} synthetic cases and refresh`, async () => {
      fixture = synthetic(size);
      const view = render(<></>);
      await measure('initial', size, () => { view.rerender(<FinanceCaseList onCase={() => undefined} />); });
      expect(rowIds()).toEqual(fixture.orders.slice(2).map(order => order.case_no));
      expect(traces.filter(trace => trace.outcome !== 'success')).toHaveLength(0);
      const first = fixture.accounting.get('SYN-0002');
      if (!first) throw new Error('Synthetic accounting missing');
      fixture.accounting.set('SYN-0002', { ...first, staff_receivable_ntd: 76543 });
      await measure('revision', size, () => { view.rerender(<FinanceCaseList onCase={() => undefined} revision={1} />); }, 76543);
      expect(within(screen.getByRole('row', { name: /SYN-0002/ })).getByText('NT$ 76,543')).toBeVisible();
      fixture.accounting.set('SYN-0002', { ...first, staff_receivable_ntd: 76544 });
      await measure('manual-refresh', size, () => { fireEvent.click(screen.getByRole('button', { name: '查詢案件' })); }, 76544);
      expect(rowIds()).toHaveLength(size - 2);
    }, 30000);
  }
  it('preserves all, stage, timing, exact search, amounts and reminder actions', async () => {
    const selected = vi.fn();
    render(<FinanceCaseList onCase={selected} />);
    await loaded();
    expect(rowIds()).toHaveLength(14);
    fireEvent.click(screen.getByRole('tab', { name: '所有案件' }));
    expect(rowIds()).toHaveLength(16);
    expect(screen.getByRole('row', { name: /SYN-0001/ })).toHaveTextContent('已結清');
    fireEvent.change(screen.getByLabelText('目前階段'), { target: { value: 'second' } });
    expect(rowIds()).toEqual(['SYN-0002', 'SYN-0006', 'SYN-0010', 'SYN-0014']);
    fireEvent.change(screen.getByLabelText('時效篩選'), { target: { value: 'future' } });
    expect(rowIds()).toEqual(['SYN-0006']);
    fireEvent.change(screen.getByLabelText('目前階段'), { target: { value: 'all' } });
    fireEvent.change(screen.getByLabelText('時效篩選'), { target: { value: 'all' } });
    fireEvent.change(screen.getByPlaceholderText('案件編號、客戶或月嫂'), { target: { value: 'SYN-0004' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢案件' }));
    await loaded();
    expect(rowIds()).toEqual(['SYN-0004']);
    const row = within(screen.getByRole('row', { name: /SYN-0004/ }));
    expect(row.getByText('NT$ 10,004')).toBeVisible();
    expect(row.getByText('尚無成功通知紀錄')).toBeVisible();
    fireEvent.click(row.getByRole('button', { name: '發出提醒' }));
    expect(selected).toHaveBeenCalledWith('SYN-0004', 'deposit');
  });
  it('keeps individual accounting and notice failures unknown and never fabricates zero or send authority', async () => {
    denied.add('/api/v1/finance-import/cases/SYN-0002/accounting');
    denied.add('/api/v1/line/payment-overdue-reminders/cases/SYN-0004');
    render(<FinanceCaseList onCase={() => undefined} />);
    await loaded();
    const failedAccounting = within(screen.getByRole('row', { name: /SYN-0002/ }));
    expect(failedAccounting.getByText('帳務來源待確認')).toBeVisible();
    expect(failedAccounting.queryByRole('button', { name: '發出提醒' })).not.toBeInTheDocument();
    const failedNotice = within(screen.getByRole('row', { name: /SYN-0004/ }));
    expect(failedNotice.getByText('通知紀錄待確認')).toBeVisible();
    expect(failedNotice.queryByText('尚無成功通知紀錄')).not.toBeInTheDocument();
    expect(failedNotice.queryByRole('button', { name: '發出提醒' })).not.toBeInTheDocument();
    expect(traces.filter(trace => trace.outcome === 'failure')).toHaveLength(2);
  });
  it('distinguishes empty from denied and fresh token revocation', async () => {
    fixture = synthetic(0);
    const view = render(<FinanceCaseList onCase={() => undefined} />);
    await loaded();
    expect(screen.getByText('目前沒有符合條件的進行中案件。')).toBeVisible();
    fixture = synthetic(16);
    denied.add('/api/v1/orders/summaries');
    fireEvent.click(screen.getByRole('button', { name: '查詢案件' }));
    await loaded();
    expect(screen.getByRole('alert')).toBeVisible();
    expect(screen.queryByText('目前沒有符合條件的進行中案件。')).not.toBeInTheDocument();
    denied.clear();
    vi.mocked(sessionClient.getToken).mockReturnValue(null);
    view.rerender(<FinanceCaseList onCase={() => undefined} revision={1} />);
    await loaded();
    expect(screen.getByRole('alert')).toBeVisible();
    expect(rowIds()).toHaveLength(0);
  });
  it('aborts replaced generations and publishes only the latest search', async () => {
    latency = 100;
    const view = render(<FinanceCaseList onCase={() => undefined} />);
    await waitFor(() => expect(traces.length).toBeGreaterThan(0));
    view.rerender(<FinanceCaseList onCase={() => undefined} revision={1} />);
    await loaded();
    expect(traces.some(trace => trace.outcome === 'abort')).toBe(true);
    fireEvent.change(screen.getByPlaceholderText('案件編號、客戶或月嫂'), { target: { value: 'SYN-0004' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢案件' }));
    await loaded();
    expect(rowIds()).toEqual(['SYN-0004']);
    view.unmount();
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 1)); });
    expect(active).toBe(0);
  }, 15000);
});
