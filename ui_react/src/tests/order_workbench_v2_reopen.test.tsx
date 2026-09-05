import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderControlledReopenPanel } from '../components/OrderControlledReopenPanel';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { ApiHttpError } from '../api/shared/typed_errors';
import type { OrderReopenPreviewView, OrderReopenReceiptView } from '../api/orders/order_mutation_schemas';

const mocks = vi.hoisted(() => ({ preview: vi.fn(), apply: vi.fn(), detail: vi.fn() }));
vi.mock('../api/orders/order_mutation_client', () => ({ ordersMutationClient: { previewReopen: mocks.preview, applyReopen: mocks.apply } }));
vi.mock('../api/orders/order_query_client', () => ({ ordersQueryClient: { getOrderDetail: mocks.detail } }));
const CASE = 'CASE-BETA-REOPEN'; const fingerprint = 'b'.repeat(64);
function preview(): OrderReopenPreviewView {
  return { case_no: CASE, order_version: 3, client_finance_version: 5, payroll_version: 6, cancellation_event_id: 31,
    before_status: '訂單取消', after_status: '訂單成立', requires_fresh_scheduling_preview: true,
    restored_assignment_ids: [], restored_schedule_ids: [], restored_lock_ids: [], preview_fingerprint: fingerprint };
}
function receipt(): OrderReopenReceiptView {
  return { case_no: CASE, order_version: 4, lifecycle_status: '訂單成立', cancellation_event_id: 31,
    requires_fresh_scheduling_preview: true, preview_fingerprint: fingerprint };
}
async function check() {
  fireEvent.click(screen.getByRole('button', { name: '檢查受控重開影響' }));
  await screen.findByText('訂單取消 → 訂單成立');
  fireEvent.change(screen.getByLabelText('Beta 受控重開原因'), { target: { value: '客戶重新確認服務需求。' } });
}

describe('Beta 沿用正式受控重開狀態機', () => {
  beforeEach(() => {
    orderMutationFlowStore.clearAll(); Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.preview.mockResolvedValue(preview()); mocks.apply.mockResolvedValue(receipt());
    mocks.detail.mockResolvedValue({ case_no: CASE, order_status: '訂單成立' });
  });

  it('三版本／fingerprint／原因沿用既有 flow，讀取正式案件之後才通知父頁', async () => {
    const onObserved = vi.fn(); render(<OrderControlledReopenPanel caseNo={CASE} onObserved={onObserved} />);
    await check(); fireEvent.click(screen.getByRole('button', { name: '確認受控重開' }));
    await screen.findByText('受控重開已完成正式回讀：訂單成立。請重新確認正式服務日期與排班。');
    expect(mocks.apply).toHaveBeenCalledWith(CASE, {
      expected_order_version: 3, expected_client_finance_version: 5, expected_payroll_version: 6,
      preview_fingerprint: fingerprint, reason: '客戶重新確認服務需求。',
    }, { idempotencyKey: expect.any(String) });
    expect(mocks.detail).toHaveBeenCalledWith(CASE); expect(onObserved).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/不恢復舊指派、舊排班或舊檔期鎖/)).toBeInTheDocument();
  });

  it('沒有原因不可 Apply，restored roots 不為空則既有 adapter 拒絕預覽', async () => {
    render(<OrderControlledReopenPanel caseNo={CASE} />);
    fireEvent.click(screen.getByRole('button', { name: '檢查受控重開影響' }));
    await screen.findByText('訂單取消 → 訂單成立');
    expect(screen.getByRole('button', { name: '確認受控重開' })).toBeDisabled();
    mocks.preview.mockResolvedValue({ ...preview(), restored_assignment_ids: [17] });
    fireEvent.click(screen.getByRole('button', { name: '檢查受控重開影響' }));
    await screen.findByText('伺服器返回非空的 restored 列表，拒絕重開操作');
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('預覽案件錯配不能套用', async () => {
    mocks.preview.mockResolvedValue({ ...preview(), case_no: 'OTHER' });
    render(<OrderControlledReopenPanel caseNo={CASE} />); await check();
    await screen.findByText('受控重開預覽案件識別不一致。');
    expect(screen.getByRole('button', { name: '確認受控重開' })).toBeDisabled(); expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('outcome unknown 鎖住草稿，使用同 key 與 payload 重試', async () => {
    mocks.apply.mockRejectedValueOnce(new ApiHttpError(503, 'unavailable', '暫時無法確認', true));
    const onBusyChange = vi.fn(); render(<OrderControlledReopenPanel caseNo={CASE} onBusyChange={onBusyChange} />);
    await check(); fireEvent.click(screen.getByRole('button', { name: '確認受控重開' }));
    const retry = await screen.findByRole('button', { name: '以原操作重新確認重開結果' });
    expect(screen.getByLabelText('Beta 受控重開原因')).toBeDisabled();
    expect(screen.getByRole('button', { name: '檢查受控重開影響' })).toBeDisabled();
    fireEvent.click(retry); await screen.findByText(/受控重開已完成正式回讀/);
    expect(mocks.apply.mock.calls[1]).toEqual(mocks.apply.mock.calls[0]);
    expect(onBusyChange).toHaveBeenLastCalledWith(false);
  });

  it('receipt 後回讀失敗，恢復只重試觀察、不重開第二次', async () => {
    mocks.detail.mockRejectedValueOnce(new Error('readback unavailable')).mockResolvedValue({ case_no: CASE, order_status: '訂單成立' });
    const onObserved = vi.fn(); render(<OrderControlledReopenPanel caseNo={CASE} onObserved={onObserved} />);
    await check(); fireEvent.click(screen.getByRole('button', { name: '確認受控重開' }));
    const retry = await screen.findByRole('button', { name: '只重新讀取重開結果' });
    expect(onObserved).not.toHaveBeenCalled(); fireEvent.click(retry);
    await screen.findByText(/受控重開已完成正式回讀/);
    expect(mocks.apply).toHaveBeenCalledTimes(1); expect(onObserved).toHaveBeenCalledTimes(1);
  });

  it('正式回讀狀態不同不冒充完成，保留 receipt', async () => {
    mocks.detail.mockResolvedValue({ case_no: CASE, order_status: '訂單取消' });
    const onObserved = vi.fn(); render(<OrderControlledReopenPanel caseNo={CASE} onObserved={onObserved} />);
    await check(); fireEvent.click(screen.getByRole('button', { name: '確認受控重開' }));
    await screen.findByRole('button', { name: '只重新讀取重開結果' });
    expect(orderMutationFlowStore.getReopenDraft(CASE)?.receiptView).toEqual(receipt());
    expect(onObserved).not.toHaveBeenCalled();
  });

  it('stale conflict 由既有 flow 使 preview 失效，不再提供 Apply', async () => {
    mocks.apply.mockRejectedValue(new ApiHttpError(409, 'stale_preview', '預覽過期'));
    render(<OrderControlledReopenPanel caseNo={CASE} />); await check();
    fireEvent.click(screen.getByRole('button', { name: '確認受控重開' }));
    await waitFor(() => expect(orderMutationFlowStore.getReopenDraft(CASE)?.status).toBe('stale'));
    expect(screen.queryByRole('button', { name: '確認受控重開' })).not.toBeInTheDocument();
    expect(mocks.apply).toHaveBeenCalledTimes(1);
  });
});
