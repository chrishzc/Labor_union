import { useState } from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CORE_STAGE_CODES, SUBSTATUS_BY_STAGE_STATUS, substatusCodesForStage, type CoreStageCode, type CoreStageProjection } from '../../../../../../../api/orders/order_core_stage_projection_schemas';
import type { OrderCoreStageProjectionQueryParams } from '../../../../../../../api/orders/order_core_stage_projection_client';
import { OrderWorkbenchV2Page } from '../../../../../../../pages/OrderWorkbenchV2Page';
import { ADMIN_VIEW_FRESH_MS, AdminOperationsViewProvider } from '../../../../../../../pages/admin_operations_view_cache';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
import * as intakeClient from '../../../../../../../api/case_import/import_field_issues';

const mocks = vi.hoisted(() => ({ core: vi.fn(), summaries: vi.fn() }));
function Panel({ onObserved, onPoolReadback, onCommitted, onClose }: { onObserved?: () => void; onPoolReadback?: () => void; onCommitted?: () => void; onClose?: () => void }) {
  const [draft, setDraft] = useState('');
  return <section>
    <input aria-label="整合測試面板草稿" value={draft} onChange={(event) => setDraft(event.target.value)} />
    <button type="button" onClick={onObserved ?? onPoolReadback ?? onCommitted}>模擬正式 owner 回讀完成</button>
    {onClose && <button type="button" onClick={onClose}>關閉整合測試 Drawer</button>}
  </section>;
}
vi.mock('../../../../../../../components/OrderCandidateQueryPanel', () => ({ OrderCandidateQueryPanel: Panel }));
vi.mock('../../../../../../../components/OrderCandidateContactStatusPanel', () => ({ OrderCandidateContactStatusPanel: Panel }));
vi.mock('../../../../../../../components/OrderFormalRecommendationPanel', () => ({ OrderFormalRecommendationPanel: Panel }));
vi.mock('../../../../../../../components/ContractExternalSigningActions', () => ({ ContractExternalSigningActions: Panel }));
vi.mock('../../../../../../../components/OrderServiceDatesPanel', () => ({ OrderServiceDatesPanel: Panel }));
vi.mock('../../../../../../../components/OrderAssignmentPlanPanel', () => ({ OrderAssignmentPlanPanel: Panel }));
vi.mock('../../../../../../../components/OrderWorkbenchV2Drawer', () => ({ OrderWorkbenchV2Drawer: Panel }));
vi.mock('../../../../../../../api/orders/order_core_stage_projection_client', () => ({ orderCoreStageProjectionClient: { getCoreStageTimelines: mocks.core } }));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({ loadAllOrderSummaries: mocks.summaries, ordersQueryClient: { getOrderSummaries: vi.fn() } }));

const labels: Readonly<Record<CoreStageCode, string>> = {
  intake_validation: '進件與資料完整性驗證', matching_pool: '建立候選月嫂池',
  caregiver_line_delivery: '詢問月嫂接案意願', caregiver_willingness_reply: '等待月嫂意願回覆',
  formal_recommendation: '推薦月嫂給客戶確認', external_signing_dispatch: '建立契約並送交外部簽署平台',
  deposit_settlement: '客戶定金核銷', external_signing_completion: '雙方外部簽署完成',
  confirmed_service_dates: '服務日期確認', formal_service: '排班與服務履約',
  service_completion: '完工／服務完成確認', client_settlement: '客戶端結算', staff_payout: '月嫂端結算',
};
function page(selected: CoreStageCode) {
  return {
    items: [{ case_no: 'CASE-REFRESH', base_revision: 1, lifecycle_status: '訂單成立', branch_type: 'normal',
      current_core_stage_code: selected, current_core_stage_ordinal: CORE_STAGE_CODES.indexOf(selected) + 1,
      core_stages: CORE_STAGE_CODES.map((code, index): CoreStageProjection => {
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
  fireEvent.click(within(strip).getAllByRole('button')[CORE_STAGE_CODES.indexOf(code) + 1]!);
  const card = (await screen.findByText('CASE-REFRESH')).closest('tr')!;
  fireEvent.click(card);
  return (await screen.findAllByLabelText('整合測試面板草稿'))[0]!;
}

describe('Beta owner mutation 到清單與階段的完整 callback 接線', () => {
  beforeEach(() => {
    mocks.core.mockReset(); mocks.summaries.mockReset();
    mocks.summaries.mockResolvedValue({ items: [], next_cursor: null, etag: 'c'.repeat(64) });
    mocks.core.mockImplementation(async (query: OrderCoreStageProjectionQueryParams) => {
      const result = page(query.stage ?? 'matching_pool');
      if (query.stage === undefined) result.substatus_counts = {};
      return result;
    });
  });

  it('同一登入範圍返回保留篩選，過期時顯示舊清單至新查詢完成', async () => {
    mocks.core.mockResolvedValue({ ...page('intake_validation'), substatus_counts: {} });
    const now = vi.spyOn(Date, 'now');
    const start = now();
    now.mockReturnValue(start);
    const intake = vi.spyOn(intakeClient, 'loadCurrentImportFieldIssuesForCases').mockResolvedValue([{
      case_no: 'CASE-REFRESH',
      issues: [{ source: 'hcm', owner: 'client_profile', field: 'residence_type', source_field: '居住型態', code: 'invalid', message: '請確認居住型態' }],
    }]);
    const route = (visible: boolean, scope = 'first') => (
      <AdminOperationsViewProvider key={scope}>
        {visible && <OrderWorkbenchV2Page />}
      </AdminOperationsViewProvider>
    );
    const { rerender } = render(route(true));
    try {
      await screen.findByRole('link', { name: '修正資料' });
      fireEvent.change(screen.getByRole('textbox', { name: '搜尋案件編號或姓名' }), { target: { value: 'REFRESH' } });
      const initialReads = mocks.core.mock.calls.length;

      rerender(route(false));
      rerender(route(true));
      expect(screen.getByRole('textbox', { name: '搜尋案件編號或姓名' })).toHaveValue('REFRESH');
      expect(screen.getByText('CASE-REFRESH')).toBeInTheDocument();
      await act(async () => {});
      expect(mocks.core).toHaveBeenCalledTimes(initialReads);

      rerender(route(false));
      now.mockReturnValue(start + ADMIN_VIEW_FRESH_MS + 1);
      let fail!: (error: Error) => void;
      mocks.core.mockImplementationOnce(() => new Promise((_, reject) => { fail = reject; }));
      rerender(route(true));
      expect(screen.getByText('CASE-REFRESH')).toBeInTheDocument();
      expect(screen.getByText('清單更新中，顯示上次資料。重新讀取完成後可處理案件。')).toBeInTheDocument();
      expect(screen.getByRole('region', { name: '待辦案件清單，可橫向捲動' })).toHaveAttribute('tabindex', '0');
      expect(screen.getByRole('table', { name: '待辦案件清單' })).toHaveAccessibleDescription(/顯示上次資料/);
      expect(screen.getByText('居住型態')).toBeInTheDocument();
      expect(screen.queryByRole('link', { name: '修正資料' })).not.toBeInTheDocument();
      await waitFor(() => expect(mocks.core).toHaveBeenCalledTimes(initialReads + 1));
      await act(async () => { fail(new Error('query unavailable')); });
      expect(screen.getByText('CASE-REFRESH')).toBeInTheDocument();
      expect(screen.getByRole('alert')).toHaveTextContent('顯示');

      mocks.core.mockRejectedValueOnce(new ApiHttpError(403, 'forbidden', '權限不足'));
      fireEvent.click(screen.getByRole('button', { name: '重試' }));
      await waitFor(() => expect(screen.queryByText('CASE-REFRESH')).not.toBeInTheDocument());
      expect(screen.getByRole('alert')).toHaveTextContent('目前帳號無法查看案件清單。請聯絡系統管理員確認權限。');
      fireEvent.click(screen.getByRole('button', { name: '重新整理' }));
      await screen.findByText('CASE-REFRESH');

      rerender(route(false));
      mocks.core.mockImplementationOnce(() => new Promise(() => {}));
      rerender(route(true, 'second'));
      expect(screen.getByRole('textbox', { name: '搜尋案件編號或姓名' })).toHaveValue('');
      expect(screen.queryByText('CASE-REFRESH')).not.toBeInTheDocument();
      expect(screen.getByText('正在查詢訂單資料…')).toBeInTheDocument();
    } finally {
      now.mockRestore();
      intake.mockRestore();
    }
  });

  it('清單更新中或更新失敗時，點擊與鍵盤都不能開啟舊案件列', async () => {
    render(<OrderWorkbenchV2Page />);
    const card = await screen.findByRole('row', { name: '開啟案件 CASE-REFRESH 案件處理' });
    let reject!: (reason: Error) => void;
    mocks.core.mockImplementationOnce(() => new Promise((_, fail) => { reject = fail; }));
    fireEvent.click(screen.getByRole('button', { name: '重新整理' }));
    await waitFor(() => expect(card).toHaveAttribute('aria-disabled', 'true'));
    expect(card).toHaveAttribute('tabindex', '-1');
    fireEvent.click(card);
    fireEvent.keyDown(card, { key: 'Enter' });
    fireEvent.keyDown(card, { key: ' ' });
    expect(screen.queryByLabelText('整合測試面板草稿')).not.toBeInTheDocument();
    await act(async () => { reject(new Error('query unavailable')); });
    await screen.findByRole('alert');
    expect(card).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(card);
    expect(screen.queryByLabelText('整合測試面板草稿')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新整理' }));
    await waitFor(() => expect(card).toHaveAttribute('aria-disabled', 'false'));
    fireEvent.click(card);
    expect(await screen.findByLabelText('整合測試面板草稿')).toBeInTheDocument();
  });

  it.each<CoreStageCode>([
    'matching_pool', 'caregiver_line_delivery', 'caregiver_willingness_reply', 'formal_recommendation',
    'external_signing_dispatch', 'external_signing_completion', 'confirmed_service_dates', 'formal_service',
  ])('%s 完成正式回讀後重查目前條件與摘要，刷新期間保留同一面板', async (code) => {
    render(<OrderWorkbenchV2Page />);
    const input = await selectStage(code);
    fireEvent.change(input, { target: { value: '保留操作內容' } });
    let resolve!: (value: ReturnType<typeof page>) => void;
    mocks.core.mockImplementationOnce(() => new Promise<ReturnType<typeof page>>((done) => { resolve = done; }));
    const queries = mocks.core.mock.calls.length; const summaries = mocks.summaries.mock.calls.length;
    fireEvent.click(screen.getAllByRole('button', { name: '模擬正式 owner 回讀完成' })[0]!);
    await waitFor(() => expect(mocks.core).toHaveBeenCalledTimes(queries + 1));
    expect(mocks.core).toHaveBeenLastCalledWith(expect.objectContaining({ stage: code }), expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(mocks.summaries).toHaveBeenCalledTimes(summaries + 1);
    expect(input).toBeInTheDocument(); expect(input).toHaveValue('保留操作內容'); expect(input).toBeDisabled();
    await act(async () => { resolve(page(code)); });
    await waitFor(() => expect(input).toBeEnabled());
    expect(screen.getAllByLabelText('整合測試面板草稿')).toContain(input);
    expect(input).toHaveValue('保留操作內容');
  });

  it('刷新失敗不遺失面板，但禁止舊資料操作；重新查詢成功才恢復', async () => {
    render(<OrderWorkbenchV2Page />); const input = await selectStage('formal_recommendation');
    fireEvent.change(input, { target: { value: '不可因錯誤遺失' } });
    mocks.core.mockRejectedValueOnce(new Error('owner temporarily unavailable'));
    fireEvent.click(screen.getByRole('button', { name: '模擬正式 owner 回讀完成' }));
    await screen.findByRole('alert'); expect(input).toBeInTheDocument(); expect(input).toBeDisabled();
    expect(input).toHaveValue('不可因錯誤遺失');
    fireEvent.click(screen.getByRole('button', { name: '重新整理' }));
    await waitFor(() => expect(input).toBeEnabled());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument(); expect(input).toHaveValue('不可因錯誤遺失');
  });

  it('面板回讀收到拒絕存取時清除案件，重試成功後回到清單', async () => {
    render(<OrderWorkbenchV2Page />);
    await selectStage('formal_recommendation');
    mocks.core.mockRejectedValueOnce(new ApiHttpError(403, 'forbidden', '權限不足'));
    fireEvent.click(screen.getByRole('button', { name: '模擬正式 owner 回讀完成' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('目前帳號無法查看案件清單。請聯絡系統管理員確認權限。');
    expect(screen.queryByLabelText('整合測試面板草稿')).not.toBeInTheDocument();
    expect(screen.queryByText('CASE-REFRESH')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '重新整理' }));
    await screen.findByText('CASE-REFRESH');
    expect(screen.queryByLabelText('整合測試面板草稿')).not.toBeInTheDocument();
  });

  it('Drawer 內成功 callback 更新清單及摘要而不關閉或重建 Drawer', async () => {
    render(<OrderWorkbenchV2Page />); await screen.findByText('CASE-REFRESH');
    fireEvent.click(screen.getByRole('button', { name: '開啟案件 CASE-REFRESH 案件處理' }));
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

  it('排班回讀後清單更新狀態與實際期間，保留約定期間', async () => {
    const before = page('formal_service');
    before.substatus_counts = {};
    before.items[0]!.lifecycle_status = '服務中';
    const formalStage = before.items[0]!.core_stages.find((stage) => stage.code === 'formal_service')!;
    formalStage.status = 'unavailable';
    formalStage.substatus_code = 'service_schedule_unavailable';
    mocks.core.mockResolvedValueOnce(before);
    const summary = {
      case_no: 'CASE-REFRESH', client_name: '測試客戶', order_status: '服務中',
      staff_name: '測試月嫂', identity_status: null,
      start_date: '2026-09-21', end_date: '2026-10-30',
      actual_start_date: null, actual_end_date: null,
      service_days: 30, total_employer_self_pay_payable: null,
    };
    mocks.summaries.mockResolvedValueOnce({ items: [summary], next_cursor: null, etag: 'c'.repeat(64) });
    render(<OrderWorkbenchV2Page />);
    const card = (await screen.findByText('CASE-REFRESH')).closest('tr')!;
    expect(within(card).getByText('尚未取得排班資料')).toBeInTheDocument();
    expect(await within(card).findByText('2026-09-21 ~ 2026-10-30')).toBeInTheDocument();
    expect(within(card).queryByText(/實際服務/)).not.toBeInTheDocument();
    fireEvent.click(card);

    const after = page('formal_service');
    after.substatus_counts = {};
    after.items[0]!.lifecycle_status = '服務中';
    mocks.core.mockResolvedValue(after);
    mocks.summaries.mockResolvedValue({
      items: [{ ...summary, actual_start_date: '2026-09-14', actual_end_date: '2026-10-23' }],
      next_cursor: null, etag: 'd'.repeat(64),
    });
    const reads = mocks.summaries.mock.calls.length;
    fireEvent.click(await screen.findByRole('button', { name: '模擬正式 owner 回讀完成' }));
    await waitFor(() => expect(mocks.summaries.mock.calls.length).toBeGreaterThan(reads));
    fireEvent.click(screen.getByRole('button', { name: '關閉整合測試 Drawer' }));
    const updatedCard = (await screen.findByText('CASE-REFRESH')).closest('tr')!;
    expect(await within(updatedCard).findByText('服務進行中')).toBeInTheDocument();
    expect(await within(updatedCard).findByText('2026-09-14 ~ 2026-10-23')).toBeInTheDocument();
    expect(within(updatedCard).getByText('2026-09-21 ~ 2026-10-30')).toBeInTheDocument();
    expect(within(updatedCard).queryByText('尚未取得排班資料')).not.toBeInTheDocument();
  });
});
