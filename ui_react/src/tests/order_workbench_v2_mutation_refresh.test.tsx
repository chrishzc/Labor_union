import { useState } from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CORE_STAGE_CODES, SUBSTATUS_BY_STAGE_STATUS, substatusCodesForStage, type CoreStageCode } from '../api/orders/order_core_stage_projection_schemas';
import type { OrderCoreStageProjectionQueryParams } from '../api/orders/order_core_stage_projection_client';
import { OrderWorkbenchV2Page } from '../pages/OrderWorkbenchV2Page';

const mocks = vi.hoisted(() => ({ core: vi.fn(), summaries: vi.fn() }));
function Panel({ onObserved, onPoolReadback, onClose }: { onObserved?: () => void; onPoolReadback?: () => void; onClose?: () => void }) {
  const [draft, setDraft] = useState('');
  return <section>
    <input aria-label="整合測試面板草稿" value={draft} onChange={(event) => setDraft(event.target.value)} />
    <button type="button" onClick={onObserved ?? onPoolReadback}>模擬正式 owner 回讀完成</button>
    {onClose && <button type="button" onClick={onClose}>關閉整合測試 Drawer</button>}
  </section>;
}
vi.mock('../components/OrderCandidateQueryPanel', () => ({ OrderCandidateQueryPanel: Panel }));
vi.mock('../components/OrderCandidateContactStatusPanel', () => ({ OrderCandidateContactStatusPanel: Panel }));
vi.mock('../components/OrderFormalRecommendationPanel', () => ({ OrderFormalRecommendationPanel: Panel }));
vi.mock('../components/OrderCaregiverContractPanel', () => ({ OrderCaregiverContractPanel: Panel }));
vi.mock('../components/OrderClientContractPanel', () => ({ OrderClientContractPanel: Panel }));
vi.mock('../components/OrderServiceDatesPanel', () => ({ OrderServiceDatesPanel: Panel }));
vi.mock('../components/OrderAssignmentPlanPanel', () => ({ OrderAssignmentPlanPanel: Panel }));
vi.mock('../components/OrderWorkbenchV2Drawer', () => ({ OrderWorkbenchV2Drawer: Panel }));
vi.mock('../api/orders/order_core_stage_projection_client', () => ({ orderCoreStageProjectionClient: { getCoreStageTimelines: mocks.core } }));
vi.mock('../api/orders/order_query_client', () => ({ loadAllOrderSummaries: mocks.summaries, ordersQueryClient: { getOrderSummaries: vi.fn() } }));

const labels: Readonly<Record<CoreStageCode, string>> = {
  intake_validation: '進件與資料完整性驗證', matching_pool: '建立候選月嫂池',
  caregiver_line_delivery: '詢問月嫂接案意願', caregiver_willingness_reply: '等待月嫂意願回覆',
  formal_recommendation: '推薦月嫂給客戶確認', caregiver_contract: '月嫂契約簽署',
  deposit_settlement: '客戶定金核銷', client_contract: '客戶契約簽署',
  confirmed_service_dates: '正式服務日期確認', formal_service: '正式排班與服務履約',
  service_completion: '完工／服務完成確認', client_settlement: '客戶端結算', staff_payout: '月嫂端結算',
};
function page(selected: CoreStageCode) {
  return {
    items: [{ case_no: 'CASE-REFRESH', base_revision: 1, lifecycle_status: '訂單成立', branch_type: 'normal',
      current_core_stage_code: selected, current_core_stage_ordinal: CORE_STAGE_CODES.indexOf(selected) + 1,
      core_stages: CORE_STAGE_CODES.map((code, index) => {
        const status = code === selected ? 'in_progress' : 'completed';
        return { ordinal: index + 1, code, label: labels[code], owner: `owner-${code}`, status,
          substatus_code: SUBSTATUS_BY_STAGE_STATUS[code][status],
          source: { owner: `owner-${code}`, identity: `${code}:CASE-REFRESH`, version: 1 }, occurred_at: null,
          blockers: [], warnings: [], available_read_actions: [], availability_reason: null };
      }), source_projection_digest: 'a'.repeat(64) }],
    stage_counts: Object.fromEntries(CORE_STAGE_CODES.map((code) => [code, code === selected ? 1 : 0])),
    substatus_counts: Object.fromEntries(substatusCodesForStage(selected).map((code) => [code, 0])),
    next_cursor: null, etag: 'b'.repeat(64),
  };
}
async function selectStage(code: CoreStageCode) {
  await screen.findByText('CASE-REFRESH');
  const strip = screen.getByRole('region', { name: '13 個核心訂單階段' });
  fireEvent.click(within(strip).getAllByRole('button')[CORE_STAGE_CODES.indexOf(code)]!);
  return screen.findByLabelText('整合測試面板草稿');
}

describe('Beta owner mutation 到清單與階段的完整 callback 接線', () => {
  beforeEach(() => {
    mocks.core.mockReset(); mocks.summaries.mockReset();
    mocks.summaries.mockResolvedValue({ items: [], next_cursor: null, etag: 'c'.repeat(64) });
    mocks.core.mockImplementation(async (query: OrderCoreStageProjectionQueryParams) => page(query.stage ?? 'intake_validation'));
  });

  it.each<CoreStageCode>([
    'matching_pool', 'caregiver_line_delivery', 'caregiver_willingness_reply', 'formal_recommendation',
    'caregiver_contract', 'client_contract', 'confirmed_service_dates', 'formal_service',
  ])('%s 完成正式回讀後重查目前條件與摘要，刷新期間保留同一面板', async (code) => {
    render(<OrderWorkbenchV2Page />);
    const input = await selectStage(code);
    fireEvent.change(input, { target: { value: '保留操作內容' } });
    let resolve!: (value: ReturnType<typeof page>) => void;
    mocks.core.mockImplementationOnce(() => new Promise<ReturnType<typeof page>>((done) => { resolve = done; }));
    const queries = mocks.core.mock.calls.length; const summaries = mocks.summaries.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: '模擬正式 owner 回讀完成' }));
    await waitFor(() => expect(mocks.core).toHaveBeenCalledTimes(queries + 1));
    expect(mocks.core).toHaveBeenLastCalledWith(expect.objectContaining({ branch_type: 'normal', stage: code }), expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(mocks.summaries).toHaveBeenCalledTimes(summaries + 1);
    expect(input).toBeInTheDocument(); expect(input).toHaveValue('保留操作內容'); expect(input).toBeDisabled();
    await act(async () => { resolve(page(code)); });
    await waitFor(() => expect(input).toBeEnabled());
    expect(screen.getByLabelText('整合測試面板草稿')).toBe(input);
    expect(input).toHaveValue('保留操作內容');
  });

  it('刷新失敗不遺失面板，但禁止舊資料操作；重新查詢成功才恢復', async () => {
    render(<OrderWorkbenchV2Page />); const input = await selectStage('formal_recommendation');
    fireEvent.change(input, { target: { value: '不可因錯誤遺失' } });
    mocks.core.mockRejectedValueOnce(new Error('owner temporarily unavailable'));
    fireEvent.click(screen.getByRole('button', { name: '模擬正式 owner 回讀完成' }));
    await screen.findByRole('alert'); expect(input).toBeInTheDocument(); expect(input).toBeDisabled();
    expect(input).toHaveValue('不可因錯誤遺失');
    fireEvent.click(screen.getByRole('button', { name: '重新讀取正式清單' }));
    await waitFor(() => expect(input).toBeEnabled());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument(); expect(input).toHaveValue('不可因錯誤遺失');
  });

  it('Drawer 內成功 callback 更新清單及摘要而不關閉或重建 Drawer', async () => {
    render(<OrderWorkbenchV2Page />); await screen.findByText('CASE-REFRESH');
    fireEvent.click(screen.getByRole('button', { name: '開啟唯讀工作 Drawer' }));
    const input = await screen.findByLabelText('整合測試面板草稿');
    fireEvent.change(input, { target: { value: 'Drawer 保留' } });
    const queries = mocks.core.mock.calls.length; const summaries = mocks.summaries.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: '模擬正式 owner 回讀完成' }));
    await waitFor(() => expect(mocks.core).toHaveBeenCalledTimes(queries + 1));
    expect(mocks.summaries).toHaveBeenCalledTimes(summaries + 1);
    expect(input).toBeInTheDocument(); expect(input).toHaveValue('Drawer 保留');
    fireEvent.click(screen.getByRole('button', { name: '關閉整合測試 Drawer' }));
    expect(screen.queryByLabelText('整合測試面板草稿')).not.toBeInTheDocument();
  });
});
