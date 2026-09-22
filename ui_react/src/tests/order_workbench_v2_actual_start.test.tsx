import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderActualStartPanel } from '../components/OrderActualStartPanel';
import { ApiHttpError } from '../api/shared/typed_errors';
import type { ActualStart } from '../api/orders/order_query_schemas';
import type { ActualStartReceipt } from '../api/orders/order_actual_start_client';
const mocks = vi.hoisted(() => ({ query: vi.fn(), preview: vi.fn(), apply: vi.fn() }));
vi.mock('../api/orders/order_query_client', () => ({ ordersQueryClient: { getActualStart: mocks.query } }));
vi.mock('../api/orders/order_actual_start_client', () => ({ orderActualStartClient: { preview: mocks.preview, apply: mocks.apply } }));
const CASE = 'CASE-BETA-START';
const fingerprint = 'a'.repeat(64);
let facts: ActualStart;
function query(): ActualStart {
  return { case_no: CASE, current_actual_start_date: null, planned_start_date: '2026-09-01', service_data_locked: false,
    order_version: 2, scheduling_version: 3, scheduling_generation: 1, client_finance_version: 4, payroll_version: 5,
    has_formal_assignments: true };
}
// Component doubles; existing typed-client tests own HTTP/schema validation.
function preview() {
  return { operation: 'reschedule' as const, before_actual_start_date: null, after_actual_start_date: '2026-09-02', actual_end_date: '2026-09-03',
    order_version: 2, scheduling_version: 3, scheduling_generation: 1,
    actual_start: { case_no: CASE, official_service_dates: ['2026-09-02', '2026-09-03'] },
    lifecycle_impact: { before_status: '訂單成立', after_status: '服務中' }, preview_fingerprint: fingerprint };
}
function receipt(): ActualStartReceipt {
  return { operation: 'reschedule', case_no: CASE, order_version: 3, scheduling_version: 4, scheduling_generation: 2,
    lifecycle_status: '服務中', service_data_lock_formed: false, cancelled_assignment_ids: [], created_assignment_keys: ['new:1'],
    official_service_day_count: 2, official_service_hours: 16, preview_fingerprint: fingerprint };
}
function commitFacts() { facts = { ...facts, current_actual_start_date: '2026-09-02', order_version: 3, scheduling_version: 4 }; }
async function open() {
  fireEvent.click(screen.getByRole('button', { name: '讀取實際開始日' }));
  await screen.findByLabelText('Beta 實際開始日期');
}
async function confirm() {
  fireEvent.change(screen.getByLabelText('Beta 實際開始日期'), { target: { value: '2026-09-02' } });
  const button = screen.getByRole('button', { name: '確認實際開始日' });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
}

describe('Beta 實際開始日正式操作', () => {
  beforeEach(() => {
    orderMutationFlowStore.clearAll();
    Object.values(mocks).forEach((mock) => mock.mockReset()); facts = query();
    mocks.query.mockImplementation(async () => structuredClone(facts));
    mocks.preview.mockResolvedValue(preview());
    mocks.apply.mockImplementation(async () => { commitFacts(); return receipt(); });
  });

  it('以單一步驟預覽並套用日期及排班，回讀確認後才通知父頁', async () => {
    const onObserved = vi.fn(); render(<OrderActualStartPanel caseNo={CASE} onObserved={onObserved} />);
    await open(); await confirm();
    expect(mocks.preview).toHaveBeenCalledWith(CASE, { new_actual_start_date: '2026-09-02' });
    await screen.findByText('實際開始日已完成正式回讀：2026-09-02');
    expect(mocks.apply).toHaveBeenCalledWith(CASE, {
      operation: 'reschedule', new_actual_start_date: '2026-09-02', expected_order_version: 2, expected_scheduling_version: 3,
      preview_fingerprint: fingerprint, reason: '確認實際開始日：2026-09-02',
    }, { idempotencyKey: expect.any(String) });
    expect(onObserved).toHaveBeenCalledTimes(1);
  });

  it('service_data_locked 不能改日期或 Preview', async () => {
    facts.service_data_locked = true;
    render(<OrderActualStartPanel caseNo={CASE} />); await open();
    expect(screen.getByLabelText('Beta 實際開始日期')).toBeDisabled();
    expect(screen.getByRole('button', { name: '確認實際開始日' })).toBeDisabled();
    expect(mocks.preview).not.toHaveBeenCalled(); expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('預覽案件識別不同即停止', async () => {
    mocks.preview.mockResolvedValue({ ...preview(), actual_start: { case_no: 'OTHER', official_service_dates: [] } });
    render(<OrderActualStartPanel caseNo={CASE} />); await open();
    fireEvent.change(screen.getByLabelText('Beta 實際開始日期'), { target: { value: '2026-09-02' } });
    fireEvent.click(screen.getByRole('button', { name: '確認實際開始日' }));
    await screen.findByText('實際開始日預覽 identity 不一致。'); expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('422 會顯示後端驗證代碼，不再只顯示通用訊息', async () => {
    mocks.preview.mockRejectedValue(new ApiHttpError(
      422,
      'payroll_case_policy_bootstrap_required',
      '實際開工日請求未通過驗證。',
    ));
    render(<OrderActualStartPanel caseNo={CASE} />); await open(); await confirm();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '實際開工日請求未通過驗證。（payroll_case_policy_bootstrap_required）',
    );
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('409 清除預覽，不以其他版本重送', async () => {
    mocks.apply.mockRejectedValue(new ApiHttpError(409, 'stale_preview', '版本過期'));
    render(<OrderActualStartPanel caseNo={CASE} />); await open(); await confirm();
    await screen.findByText('實際開始日未通過檢查，請重新讀取並預覽：版本過期（stale_preview）');
    expect(screen.queryByLabelText('Beta 實際開始日期')).not.toBeInTheDocument();
    expect(mocks.apply).toHaveBeenCalledTimes(1);
  });

  it('receipt 與 readback 日期或版本不一致，不宣稱完成', async () => {
    mocks.apply.mockResolvedValue(receipt());
    const onObserved = vi.fn(); render(<OrderActualStartPanel caseNo={CASE} onObserved={onObserved} />);
    await open(); await confirm();
    await screen.findByRole('button', { name: '只重新讀取實際開始日結果' });
    expect(onObserved).not.toHaveBeenCalled(); expect(mocks.apply).toHaveBeenCalledTimes(1);
  });

  it('重複點擊只寫一次，卸載後晚回讀不通知其他畫面', async () => {
    let finish!: (value: ActualStartReceipt) => void;
    mocks.apply.mockImplementation(() => new Promise<ActualStartReceipt>((resolve) => { finish = resolve; }));
    const onObserved = vi.fn(); const view = render(<OrderActualStartPanel caseNo={CASE} onObserved={onObserved} />);
    await open();
    fireEvent.change(screen.getByLabelText('Beta 實際開始日期'), { target: { value: '2026-09-02' } });
    const button = screen.getByRole('button', { name: '確認實際開始日' }); fireEvent.click(button); fireEvent.click(button);
    await waitFor(() => expect(mocks.apply).toHaveBeenCalledTimes(1));
    view.unmount(); commitFacts(); await act(async () => { finish(receipt()); });
    expect(onObserved).not.toHaveBeenCalled();
  });
});
