import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FinanceCaseList } from '../../../../../../../components/FinanceCaseList';
import * as orderLoader from '../../../../../../../api/orders/order_query_client';
import * as timelineLoader from '../../../../../../../api/orders/load_all_core_stage_timelines';
import type { OrderSummaryItem } from '../../../../../../../api/orders/order_query_schemas';
import { CORE_STAGE_CODES, SUBSTATUS_BY_STAGE_STATUS, OrderCoreStageTimelinePageSchema, type OrderCoreStageTimeline } from '../../../../../../../api/orders/order_core_stage_projection_schemas';
import { financeAccountingClient, type CaseAccounting } from '../../../../../../../api/finance_import/finance_accounting_client';
import { paymentOverdueReminderClient, type CasePaymentReminder } from '../../../../../../../api/line_order_groups/payment_overdue_reminder_client';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';

function deferred<T>() {
  let resolve: (value: T | PromiseLike<T>) => void = () => { throw new Error('Deferred not initialized'); };
  let reject: (reason?: unknown) => void = () => { throw new Error('Deferred not initialized'); };
  const promise = new Promise<T>((accept, fail) => { resolve = accept; reject = fail; });
  return { promise, resolve, reject };
}
type PendingCase = {
  accounting: ReturnType<typeof deferred<CaseAccounting>>;
  notices: ReturnType<typeof deferred<CasePaymentReminder[]>>;
};
const cases = ['SYN-P-001', 'SYN-P-002', 'SYN-P-003', 'SYN-P-004'];
const digest = 'b'.repeat(64);
let pending: Map<string, PendingCase>;

function order(case_no: string): OrderSummaryItem {
  return { case_no, client_name: `合成客戶 ${case_no}`, order_status: '訂單成立', staff_name: '合成人員', identity_status: null, start_date: null, end_date: null, actual_start_date: null, actual_end_date: null, service_days: null, total_employer_self_pay_payable: null };
}
function timeline(case_no: string): OrderCoreStageTimeline {
  return {
    case_no, base_revision: 1, lifecycle_status: '訂單成立', branch_type: 'normal', current_core_stage_code: 'deposit_settlement', current_core_stage_ordinal: 8,
    historical_current_owner_stage_code: null, historical_current_owner_stage_ordinal: null, source_projection_digest: digest,
    core_stages: CORE_STAGE_CODES.map((code, index) => {
      const status = index < 7 ? 'completed' : index === 7 ? 'in_progress' : 'not_started';
      const substatus_code = SUBSTATUS_BY_STAGE_STATUS[code][status];
      if (!substatus_code) throw new Error(`Missing synthetic stage ${code}`);
      return { ordinal: index + 1, code, label: code, owner: 'Synthetic owner', status, substatus_code, source: { owner: 'Synthetic owner', identity: case_no, version: 1 }, occurred_at: null, blockers: [], warnings: [], available_read_actions: [], availability_reason: null };
    }),
  };
}
function accounting(case_no: string, amount = 11000, completed = false): CaseAccounting {
  return { case_no, client_name: `合成客戶 ${case_no}`, receivable_ntd: 5000, received_ntd: 1000, payable_ntd: 9000, paid_ntd: 0, staff_receivable_ntd: amount,
    pending_warning_count: 0, warnings: [], transactions: [], client_items: [], staff_items: [], ongoing_completed: completed,
    collection_progress: { stage: 'deposit', sources_complete: true, expected_ntd: 5000, received_ntd: 1000, remaining_ntd: 4000, due_date: '2099-12-31' } };
}
function generation(ids = cases): void {
  pending = new Map(ids.map(id => [id, { accounting: deferred<CaseAccounting>(), notices: deferred<CasePaymentReminder[]>() }]));
  vi.mocked(orderLoader.loadAllOrderSummaries).mockResolvedValue({ items: ids.map(order), next_cursor: null, etag: digest });
  vi.mocked(timelineLoader.loadAllCoreStageTimelines).mockResolvedValue(OrderCoreStageTimelinePageSchema.parse({
    items: ids.map(timeline), stage_counts: Object.fromEntries(CORE_STAGE_CODES.map(code => [code, 0])), substatus_counts: {},
    historical_lifecycle_counts: { unserved: 0, in_service: 0, service_completed: 0, accounting_completed: 0 }, next_cursor: null, etag: digest,
  }));
}
function pendingCase(id: string): PendingCase {
  const value = pending.get(id);
  if (!value) throw new Error(`Missing synthetic case ${id}`);
  return value;
}
async function finish(id: string, amount = 11000, completed = false): Promise<void> {
  const value = pendingCase(id);
  await act(async () => { value.accounting.resolve(accounting(id, amount, completed)); value.notices.resolve([]); });
}
function rowIds(): string[] {
  return screen.queryAllByRole('button', { name: /^SYN-P-/ }).map(button => button.textContent ?? '');
}
function expectAmount(id: string, amount: string): void {
  const row = screen.getByRole('button', { name: id }).closest('tr');
  if (!row) throw new Error(`Missing visible case ${id}`);
  expect(within(row).getByText(amount)).toBeVisible();
}
function expectIncomplete(): void {
  expect(screen.getByRole('button', { name: '查詢案件' })).toBeDisabled();
  expect(screen.getByText('—')).toBeVisible();
  expect(screen.queryByText(/已顯示全部/)).not.toBeInTheDocument();
  expect(screen.queryByText('目前沒有符合條件的進行中案件。')).not.toBeInTheDocument();
}
async function loaded(): Promise<void> {
  await waitFor(() => expect(screen.getByRole('button', { name: '查詢案件' })).toBeEnabled());
}
async function started(id = 'SYN-P-004'): Promise<void> {
  await waitFor(() => expect(financeAccountingClient.query).toHaveBeenCalledWith(id, expect.any(AbortSignal)));
}

beforeEach(() => {
  vi.spyOn(orderLoader, 'loadAllOrderSummaries');
  vi.spyOn(timelineLoader, 'loadAllCoreStageTimelines');
  vi.spyOn(financeAccountingClient, 'query').mockImplementation(caseNo => pendingCase(caseNo).accounting.promise);
  vi.spyOn(paymentOverdueReminderClient, 'case').mockImplementation(caseNo => pendingCase(caseNo).notices.promise);
  generation();
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('Finance case list progressive owner results', () => {
  it('shows complete rows before the slow owners finish, preserving owner order and incomplete status', async () => {
    render(<FinanceCaseList onCase={vi.fn()} />);
    await started();
    expectIncomplete();
    await act(async () => { pendingCase('SYN-P-003').accounting.resolve(accounting('SYN-P-003', 13000)); });
    expect(rowIds()).toEqual([]);
    await act(async () => { pendingCase('SYN-P-003').notices.resolve([]); });
    expect(rowIds()).toEqual(['SYN-P-003']);
    expectAmount('SYN-P-003', 'NT$ 13,000');
    expectIncomplete();
    await finish('SYN-P-001', 12000);
    expect(rowIds()).toEqual(['SYN-P-001', 'SYN-P-003']);
    expectIncomplete();
    await finish('SYN-P-004', 14000);
    await finish('SYN-P-002', 15000);
    await loaded();
    expect(rowIds()).toEqual(cases);
    expect(screen.getByText('4')).toBeVisible();
    expect(screen.getByText(/搜尋範圍共 4 案；已顯示全部/)).toBeVisible();
  });

  it('updates a fast refreshed case while retaining slow old rows, then removes completed and no-longer-eligible cases', async () => {
    const view = render(<FinanceCaseList onCase={vi.fn()} />);
    await started();
    for (const id of cases) await finish(id);
    await loaded();
    expect(rowIds()).toEqual(cases);
    generation(['SYN-P-001', 'SYN-P-002', 'SYN-P-003']);
    vi.mocked(financeAccountingClient.query).mockClear();
    view.rerender(<FinanceCaseList onCase={vi.fn()} revision={1} />);
    await started('SYN-P-003');
    expectAmount('SYN-P-002', 'NT$ 11,000');
    await finish('SYN-P-001', 21000);
    expect(rowIds()).toEqual(['SYN-P-001', 'SYN-P-002', 'SYN-P-003']);
    expectAmount('SYN-P-001', 'NT$ 21,000');
    expectAmount('SYN-P-002', 'NT$ 11,000');
    expectIncomplete();
    await finish('SYN-P-002', 22000, true);
    expect(rowIds()).toEqual(['SYN-P-001', 'SYN-P-003']);
    expectIncomplete();
    await finish('SYN-P-003', 23000);
    await loaded();
    expect(rowIds()).toEqual(['SYN-P-001', 'SYN-P-003']);
    expectAmount('SYN-P-003', 'NT$ 23,000');
    expect(screen.getByText(/搜尋範圍共 2 案；已顯示全部/)).toBeVisible();
  });

  it.each(['revision', 'search'])('ignores late owner resolutions after partial publication and a %s change', async change => {
    const view = render(<FinanceCaseList onCase={vi.fn()} />);
    await started();
    const firstSignal = vi.mocked(financeAccountingClient.query).mock.calls[0]?.[1];
    const oldPending = pending;
    await finish('SYN-P-003', 13000);
    expect(rowIds()).toEqual(['SYN-P-003']);
    generation(['SYN-P-001']);
    vi.mocked(financeAccountingClient.query).mockClear();
    if (change === 'revision') {
      view.rerender(<FinanceCaseList onCase={vi.fn()} revision={1} />);
    } else {
      const input = screen.getByRole('textbox', { name: '搜尋案件或對象' });
      fireEvent.change(input, { target: { value: 'SYN-P-001' } });
      const form = input.closest('form');
      if (!form) throw new Error('Missing case search form');
      fireEvent.submit(form);
    }
    await started('SYN-P-001');
    expect(firstSignal?.aborted).toBe(true);
    await finish('SYN-P-001', 31000);
    await loaded();
    expect(rowIds()).toEqual(['SYN-P-001']);
    expectAmount('SYN-P-001', 'NT$ 31,000');
    await act(async () => {
      for (const [id, value] of oldPending) {
        value.accounting.resolve(accounting(id, 99000));
        value.notices.resolve([]);
      }
    });
    expect(rowIds()).toEqual(['SYN-P-001']);
    expectAmount('SYN-P-001', 'NT$ 31,000');
    expect(screen.queryByText('NT$ 99,000')).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByText(/搜尋範圍共 1 案；已顯示全部/)).toBeVisible();
  });

  it.each(['orders', 'timelines'])('hides previously visible sensitive rows when the refreshed %s owner denies access', async owner => {
    const view = render(<FinanceCaseList onCase={vi.fn()} />);
    await started();
    for (const id of cases) await finish(id, 41000);
    await loaded();
    expectAmount('SYN-P-001', 'NT$ 41,000');
    generation();
    const denied = new ApiHttpError(403, 'FORBIDDEN', 'Synthetic access revoked');
    if (owner === 'orders') vi.mocked(orderLoader.loadAllOrderSummaries).mockRejectedValueOnce(denied);
    else vi.mocked(timelineLoader.loadAllCoreStageTimelines).mockRejectedValueOnce(denied);
    view.rerender(<FinanceCaseList onCase={vi.fn()} revision={1} />);
    expect(await screen.findByRole('alert')).toBeVisible();
    await loaded();
    expect(rowIds()).toEqual([]);
    expect(screen.queryByText('NT$ 41,000')).not.toBeInTheDocument();
    expect(screen.queryByText('目前沒有符合條件的進行中案件。')).not.toBeInTheDocument();
  });
});
