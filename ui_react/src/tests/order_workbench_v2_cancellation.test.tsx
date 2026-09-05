import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderCancellationPanel } from '../components/OrderCancellationPanel';
import { ApiHttpError } from '../api/shared/typed_errors';
import type { OrderCancellationQuery, OrderCancellationReceipt, ServiceDay } from '../api/orders/order_cancellation_client';

const mocks = vi.hoisted(() => ({ query: vi.fn(), preview: vi.fn(), apply: vi.fn(), receipt: vi.fn() }));
vi.mock('../api/orders/order_cancellation_client', () => ({ orderCancellationClient: mocks }));
const CASE = 'CASE-BETA-CANCEL';
const fingerprint = 'c'.repeat(64);
let facts: OrderCancellationQuery;
function query(): OrderCancellationQuery {
  return { case_no: CASE, lifecycle_status: '訂單成立', actual_start_date: null, contracted_service_days: 20,
    service_hours_per_day: 8, service_started: false, historical_mid_service_confirmation_available: false,
    service_data_locked: false, order_version: 2, scheduling_version: 3, scheduling_generation: 1,
    client_finance_version: 4, payroll_version: 5, confirmed_service_days: [], caregiver_options: [{ staff_id: 8, display_name: '測試月嫂' }] };
}
// Component-boundary doubles expose the owner fields consumed by this panel;
// decoding remains covered by the existing cancellation client contract tests.
function preview(days: ServiceDay[] = []) {
  return { cancellation_date: '2026-09-05', actual_start_date: facts.actual_start_date, actual_end_date: null,
    confirmed_service_days: days, official_service_day_count: days.length, official_service_hours: days.length * 8,
    order_version: 2, scheduling_version: 3, scheduling_generation: 1, client_finance_version: 4, payroll_version: 5,
    scheduling: { case_no: CASE }, client_finance_impact: { case_no: CASE, actions: [{ payment_stage: 'deposit', direction: 'refund_due', direction_amount_ntd: 1000 }], blockers: [] },
    payroll_impact: { case_no: CASE, actions: [], blockers: [] },
    lifecycle_impact: { case_no: CASE, before_status: facts.lifecycle_status, after_status: '訂單取消' }, preview_fingerprint: fingerprint };
}
function receipt(): OrderCancellationReceipt {
  return { case_no: CASE, lifecycle_status: '訂單取消', order_version: 3, scheduling_version: 4, scheduling_generation: 2,
    client_finance_version: 5, payroll_version: 6, actual_end_date: null, official_service_day_count: 0,
    official_service_hours: 0, cancelled_assignment_ids: [], created_assignment_keys: [], preview_fingerprint: fingerprint };
}
function commitFacts() { facts = { ...facts, lifecycle_status: '訂單取消', order_version: 3, scheduling_version: 4 }; }
async function open() {
  fireEvent.click(screen.getByRole('button', { name: '讀取取消狀態' }));
  await screen.findByText(`目前狀態：${facts.lifecycle_status}`);
}
async function confirmPreview() {
  fireEvent.click(screen.getByRole('button', { name: '檢查取消影響' }));
  await screen.findByText(/取消日期：2026-09-05/);
  fireEvent.change(screen.getByLabelText('Beta 取消原因'), { target: { value: '客戶電話確認取消。' } });
  fireEvent.click(screen.getByRole('checkbox', { name: '我已核對實際服務日、帳務與取消影響' }));
}
async function apply() {
  const button = screen.getByRole('button', { name: '確認取消／補登' });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
}

describe('Beta 取消與歷史取消服務補登', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    facts = query();
    mocks.query.mockImplementation(async () => structuredClone(facts));
    mocks.preview.mockImplementation(async (_case, days) => preview(days));
    mocks.apply.mockImplementation(async () => { commitFacts(); return receipt(); });
  });

  it('未服務案件以零日 Preview，明確確認後傳送四版本、fingerprint、原因並回讀', async () => {
    const onObserved = vi.fn(); const onBusyChange = vi.fn();
    render(<OrderCancellationPanel caseNo={CASE} onObserved={onObserved} onBusyChange={onBusyChange} />);
    await open();
    expect(screen.queryByRole('button', { name: '新增實際服務日' })).not.toBeInTheDocument();
    await confirmPreview();
    expect(mocks.preview).toHaveBeenCalledWith(CASE, []);
    expect(screen.getByText('客戶 deposit：refund_due NT$ 1000')).toBeInTheDocument();
    await apply();
    await screen.findByText('訂單取消已完成正式回讀：訂單取消');
    expect(mocks.apply).toHaveBeenCalledWith(CASE, {
      confirmed_service_days: [], expected_order_version: 2, expected_scheduling_version: 3,
      expected_client_finance_version: 4, expected_payroll_version: 5, preview_fingerprint: fingerprint, reason: '客戶電話確認取消。',
    }, { idempotencyKey: expect.any(String) });
    expect(onObserved).toHaveBeenCalledTimes(1);
    expect(onBusyChange).toHaveBeenCalledWith(true);
    expect(onBusyChange).toHaveBeenLastCalledWith(false);
  });

  it('服務中不可清空實際日，修改日期／月嫂需逐日原因且重新 Preview', async () => {
    facts = { ...facts, service_started: true, actual_start_date: '2026-09-01',
      confirmed_service_days: [{ service_date: '2026-09-01', staff_id: 8, reason: null }] };
    render(<OrderCancellationPanel caseNo={CASE} />); await open();
    fireEvent.change(screen.getByLabelText('取消實際服務日 1'), { target: { value: '2026-09-02' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查取消影響' }));
    await screen.findByText('新增或變更實際服務日／月嫂，必須填寫該日人工原因。');
    expect(mocks.preview).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('取消實際服務日原因 1'), { target: { value: '核對實際出勤' } });
    await confirmPreview();
    expect(mocks.preview).toHaveBeenCalledWith(CASE, [{ service_date: '2026-09-02', staff_id: 8, reason: '核對實際出勤' }]);
    fireEvent.click(screen.getByRole('button', { name: '移除取消實際服務日 1' }));
    expect(screen.queryByRole('button', { name: '確認取消／補登' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '檢查取消影響' }));
    await screen.findByText('服務已開始或歷史取消補登，至少保留一日實際服務事實。');
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('歷史取消明確 capability 允許實際日補登，但普通已取消案件不可再取消', async () => {
    facts = { ...facts, lifecycle_status: '訂單取消', historical_mid_service_confirmation_available: true,
      confirmed_service_days: [{ service_date: '2026-09-01', staff_id: 8, reason: '歷史出勤資料' }] };
    const view = render(<OrderCancellationPanel caseNo={CASE} />); await open();
    await screen.findByText('後端允許補登歷史取消的實際服務事實；不是重新取消或重開。');
    expect(screen.getByRole('button', { name: '檢查取消影響' })).toBeEnabled();
    await confirmPreview(); expect(mocks.preview).toHaveBeenCalledWith(CASE, facts.confirmed_service_days);
    view.unmount(); facts.historical_mid_service_confirmation_available = false;
    render(<OrderCancellationPanel caseNo={CASE} />); await open();
    expect(screen.getByRole('button', { name: '檢查取消影響' })).toBeDisabled();
  });

  it('owner blocker、缺原因或未明確確認均不能 Apply', async () => {
    mocks.preview.mockResolvedValue({ ...preview(), payroll_impact: { case_no: CASE, actions: [], blockers: ['payroll_frozen'] } });
    render(<OrderCancellationPanel caseNo={CASE} />); await open(); await confirmPreview();
    expect(screen.getByText('payroll_frozen')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '確認取消／補登' })).toBeDisabled();
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('Apply 409 使預覽失效，不能用舊版本重送', async () => {
    mocks.apply.mockRejectedValue(new ApiHttpError(409, 'stale_preview', '版本已變更'));
    render(<OrderCancellationPanel caseNo={CASE} />); await open(); await confirmPreview(); await apply();
    await screen.findByText('取消未通過檢查，請重新讀取並預覽：版本已變更');
    expect(screen.queryByRole('button', { name: '確認取消／補登' })).not.toBeInTheDocument();
    expect(mocks.apply).toHaveBeenCalledTimes(1);
  });

  it('未知結果先讀原收據，已取得時只回讀而不重送 Apply', async () => {
    mocks.apply.mockImplementation(async () => { commitFacts(); throw new Error('network outcome unknown'); });
    mocks.receipt.mockResolvedValue(receipt());
    const onObserved = vi.fn();
    render(<OrderCancellationPanel caseNo={CASE} onObserved={onObserved} />); await open(); await confirmPreview(); await apply();
    const retry = await screen.findByRole('button', { name: '查詢原取消收據並確認結果' });
    expect(onObserved).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Beta 取消原因')).toBeDisabled();
    fireEvent.click(retry);
    await screen.findByText('訂單取消已完成正式回讀：訂單取消');
    expect(mocks.receipt).toHaveBeenCalledWith(CASE, mocks.apply.mock.calls[0]![2].idempotencyKey);
    expect(mocks.apply).toHaveBeenCalledTimes(1); expect(onObserved).toHaveBeenCalledTimes(1);
  });

  it('只有原收據 404 才能用同 payload／key 重試 Apply', async () => {
    mocks.apply.mockRejectedValueOnce(new Error('lost response'));
    mocks.receipt.mockRejectedValue(new ApiHttpError(404, 'receipt_not_found', 'no receipt'));
    render(<OrderCancellationPanel caseNo={CASE} />); await open(); await confirmPreview(); await apply();
    fireEvent.click(await screen.findByRole('button', { name: '查詢原取消收據並確認結果' }));
    await screen.findByText('訂單取消已完成正式回讀：訂單取消');
    expect(mocks.apply).toHaveBeenCalledTimes(2);
    expect(mocks.apply.mock.calls[1]).toEqual(mocks.apply.mock.calls[0]);
  });

  it('原收據 403 或暫時失敗不能當成404重送取消', async () => {
    mocks.apply.mockRejectedValue(new Error('lost response'));
    mocks.receipt.mockRejectedValue(new ApiHttpError(403, 'forbidden', 'no permission'));
    render(<OrderCancellationPanel caseNo={CASE} />); await open(); await confirmPreview(); await apply();
    fireEvent.click(await screen.findByRole('button', { name: '查詢原取消收據並確認結果' }));
    await waitFor(() => expect(mocks.receipt).toHaveBeenCalledTimes(1));
    expect(mocks.apply).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole('button', { name: '查詢原取消收據並確認結果' })).toBeInTheDocument();
  });

  it('receipt 後 Query 失敗只重試觀察，不再次寫入', async () => {
    mocks.query.mockResolvedValueOnce(query()).mockRejectedValueOnce(new Error('readback unavailable'))
      .mockImplementation(async () => structuredClone(facts));
    const onObserved = vi.fn(); render(<OrderCancellationPanel caseNo={CASE} onObserved={onObserved} />);
    await open(); await confirmPreview(); await apply();
    fireEvent.click(await screen.findByRole('button', { name: '只重新讀取取消結果' }));
    await screen.findByText('訂單取消已完成正式回讀：訂單取消');
    expect(mocks.apply).toHaveBeenCalledTimes(1); expect(mocks.receipt).not.toHaveBeenCalled();
    expect(onObserved).toHaveBeenCalledTimes(1);
  });

  it('重複點擊只能送出一次，卸載後晚回讀不通知其他案件', async () => {
    let finish!: (value: OrderCancellationReceipt) => void;
    mocks.apply.mockImplementation(() => new Promise<OrderCancellationReceipt>((resolve) => { finish = resolve; }));
    const onObserved = vi.fn(); const view = render(<OrderCancellationPanel caseNo={CASE} onObserved={onObserved} />);
    await open(); await confirmPreview();
    const button = screen.getByRole('button', { name: '確認取消／補登' });
    fireEvent.click(button); fireEvent.click(button);
    expect(mocks.apply).toHaveBeenCalledTimes(1);
    view.unmount(); commitFacts();
    await act(async () => { finish(receipt()); });
    expect(onObserved).not.toHaveBeenCalled();
  });
});
