import { useState } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderWorkbenchV2Drawer } from '../../../../../../../components/OrderWorkbenchV2Drawer';

const mocks = vi.hoisted(() => ({ core: vi.fn(), detail: vi.fn(), terms: vi.fn(), assignment: vi.fn() }));
interface OperationProps { caseNo: string; label: string; onObserved?: () => void; onBusyChange?: (busy: boolean) => void }
function Operation({ label, onObserved, onBusyChange }: OperationProps) {
  const [draft, setDraft] = useState('');
  const [done, setDone] = useState(false);
  return <section aria-label={`操作面板 ${label}`}>
    <input aria-label="受控操作草稿" value={draft} onChange={(event) => setDraft(event.target.value)} />
    <button type="button" onClick={() => onBusyChange?.(true)}>模擬結果未明</button>
    <button type="button" onClick={() => { setDone(true); onBusyChange?.(false); onObserved?.(); }}>模擬收據與正式回讀完成</button>
    {done && <p>此面板已觀察完成</p>}
  </section>;
}
vi.mock('../../../../../../../components/OrderCancellationPanel', () => ({ OrderCancellationPanel: (props: Omit<OperationProps, 'label'>) => <Operation {...props} label="cancellation" /> }));
vi.mock('../../../../../../../components/OrderControlledReopenPanel', () => ({ OrderControlledReopenPanel: (props: Omit<OperationProps, 'label'>) => <Operation {...props} label="reopen" /> }));
vi.mock('../../../../../../../components/OrderActualStartPanel', () => ({ OrderActualStartPanel: (props: Omit<OperationProps, 'label'>) => <Operation {...props} label="actual-start" /> }));
vi.mock('../../../../../../../components/OrderWorkbenchV2OwnerContext', () => ({ OrderWorkbenchV2OwnerContext: ({ revision }: { revision: number }) => <p>Owner context revision {revision}</p> }));
vi.mock('../../../../../../../components/OrderServiceCompletionActions', () => ({ OrderServiceCompletionActions: () => <p>正常完工操作入口</p> }));
vi.mock('../../../../../../../api/orders/order_core_stage_projection_client', () => ({ orderCoreStageProjectionClient: { getCoreStageTimelines: mocks.core } }));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({ ordersQueryClient: { getOrderDetail: mocks.detail, getOrderTerms: mocks.terms, getAssignmentPlan: mocks.assignment } }));
vi.mock('../../../../../../../components/OrderServiceDatesPanel', () => ({ OrderServiceDatesPanel: () => <p>日期操作入口</p> }));
vi.mock('../../../../../../../components/OrderAssignmentPlanPanel', () => ({ OrderAssignmentPlanPanel: () => <p>排班操作入口</p> }));
vi.mock('../../../../../../../components/OrderOfficialDateCorrectionPanel', () => ({ OrderOfficialDateCorrectionPanel: () => <p>正式日期更正操作入口</p> }));
const CASE = 'CASE-LIFECYCLE-DRAWER';
function page(cancelled = false) {
  return { items: [{ case_no: CASE, branch_type: cancelled ? 'cancelled' : 'normal',
    lifecycle_status: cancelled ? '訂單取消' : '服務中', core_stages: [],
    current_core_stage_code: cancelled ? null : 'formal_service', source_projection_digest: 'a'.repeat(64) }],
    stage_counts: {}, substatus_counts: {}, next_cursor: null, etag: 'b'.repeat(64) };
}

describe('Beta Drawer 受控操作整合與跨支線回讀', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.core.mockResolvedValue(page());
    mocks.detail.mockResolvedValue({ case_no: CASE, client_name: '測試客戶', client_id: 1, order_status: '服務中', identity_status: null, actual_start_date: '2026-09-01' });
    mocks.terms.mockResolvedValue({ case_no: CASE, order_version: 1, scheduling_version: 1,
      terms: { planned_start_date: '2026-09-01', service_days: 20, service_hours_per_day: 8 } });
    mocks.assignment.mockResolvedValue({ case_no: CASE, assignments: [{
      assignment_id: 17, candidate_key: null, staff_id: 7, sequence: 1,
      assigned_start_date: '2026-09-01', assigned_end_date: '2026-09-01',
      official_service_dates: ['2026-09-01'], actual_hours: null, lineage_source_assignment_ids: [],
    }] });
  });

  it.each([
    ['formal_service', '正式排班'],
    ['service_completion', '完工確認'],
    ['confirmed_service_dates', '確認日期'],
  ])('依 %s 直接呈現 %s，其他服務作業預設收合', async (stage, label) => {
    const data = page();
    data.items[0]!.current_core_stage_code = stage;
    mocks.core.mockResolvedValue(data);
    render(<OrderWorkbenchV2Drawer caseNo={CASE} branchType="normal" onClose={vi.fn()} />);
    await screen.findByRole('heading', { name: label });
    const summary = screen.getByText('其他服務作業');
    const secondary = summary.closest('details')!;
    expect(secondary).not.toHaveAttribute('open');
    expect(screen.queryByRole('button', { name: '更正完工服務日期' })).not.toBeInTheDocument();
    fireEvent.click(summary);
    secondary.open = true;
    const other = label === '完工確認' ? '確認日期' : '完工確認';
    fireEvent.click(screen.getByRole('button', { name: other }));
    expect(screen.getByRole('heading', { name: other })).toBeInTheDocument();
    expect(secondary).not.toHaveAttribute('open');
  });

  it.each([
    ['取消／補登取消服務事實', 'cancellation'],
    ['更正開始日並重排', 'actual-start'],
  ])('%s 的明確入口能展開對應正式操作面板', async (entry, label) => {
    render(<OrderWorkbenchV2Drawer caseNo={CASE} branchType="normal" onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '案件異動' }));
    const button = await screen.findByRole('button', { name: entry });
    await waitFor(() => expect(button).toBeEnabled());
    expect(screen.queryByLabelText('受控操作草稿')).not.toBeInTheDocument();
    fireEvent.click(button);
    expect(screen.getByRole('region', { name: `操作面板 ${label}` })).toBeInTheDocument();
  });

  it.each(['in_progress', 'completed'] as const)('完工日期更正依正式 lifecycle 開啟，不受 %s 看板分頁限制', async (scope) => {
    const data = page();
    data.items[0]!.lifecycle_status = '訂單完成';
    data.items[0]!.current_core_stage_code = null;
    mocks.core.mockResolvedValue(data);
    mocks.detail.mockResolvedValue({ case_no: CASE, client_name: '測試客戶', order_status: '訂單完成', actual_start_date: '2026-09-01' });
    render(<OrderWorkbenchV2Drawer caseNo={CASE} branchType="normal" workbenchScope={scope} onClose={vi.fn()} />);
    await screen.findByRole('heading', { name: '結算狀態' });
    expect(screen.queryByRole('button', { name: '更正完工服務日期' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '案件異動' }));
    const entry = screen.getByRole('button', { name: '更正完工服務日期' });
    await waitFor(() => expect(entry).toBeEnabled());
    expect(screen.queryByRole('button', { name: '更正開始日並重排' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '確認／更正實際開始日' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '取消／補登取消服務事實' })).not.toBeInTheDocument();
    fireEvent.click(entry);
    expect(screen.getByText('正式日期更正操作入口')).toBeVisible();
  });

  it('未完工案件只提供開始日異動，不提供完工日期更正', async () => {
    render(<OrderWorkbenchV2Drawer caseNo={CASE} branchType="normal" onClose={vi.fn()} />);
    await screen.findByRole('heading', { name: '正式排班' });
    fireEvent.click(screen.getByRole('button', { name: '案件異動' }));
    expect(screen.getByRole('button', { name: '更正開始日並重排' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: '更正完工服務日期' })).not.toBeInTheDocument();
    expect(screen.getByText(/實際開始日已一併保存/)).toBeVisible();
  });

  it('尚無正式排班時仍可確認日期，入口不宣稱會重排', async () => {
    mocks.assignment.mockResolvedValue({ case_no: CASE, assignments: [] });
    render(<OrderWorkbenchV2Drawer caseNo={CASE} branchType="normal" onClose={vi.fn()} />);
    await screen.findByRole('heading', { name: '正式排班' });
    fireEvent.click(screen.getByRole('button', { name: '案件異動' }));
    const entry = screen.getByRole('button', { name: '確認／更正實際開始日' });
    expect(entry).toBeEnabled();
    expect(screen.queryByRole('button', { name: '更正開始日並重排' })).not.toBeInTheDocument();
    fireEvent.click(entry);
    expect(screen.getByRole('region', { name: '操作面板 actual-start' })).toBeVisible();
  });

  it('實際開始日面板展開後移除無作用的重複入口', async () => {
    render(<OrderWorkbenchV2Drawer caseNo={CASE} branchType="normal" onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '案件異動' }));
    const entry = await screen.findByRole('button', { name: '更正開始日並重排' });
    await waitFor(() => expect(entry).toBeEnabled());
    fireEvent.click(entry);
    expect(screen.getByRole('region', { name: '操作面板 actual-start' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '更正開始日並重排' })).not.toBeInTheDocument();
  });

  it('受控重開入口只在取消支線顯示', async () => {
    const normal = render(<OrderWorkbenchV2Drawer caseNo={CASE} branchType="normal" onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '案件異動' }));
    await waitFor(() => expect(mocks.core).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole('button', { name: '受控重開取消案件' })).not.toBeInTheDocument();
    normal.unmount();

    mocks.core.mockResolvedValue(page(true));
    mocks.detail.mockResolvedValue({ case_no: CASE, client_name: '測試客戶', client_id: 1, order_status: '訂單取消', identity_status: null, actual_start_date: '2026-09-01' });
    render(<OrderWorkbenchV2Drawer caseNo={CASE} branchType="cancelled" onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '案件異動' }));
    const button = await screen.findByRole('button', { name: '受控重開取消案件' });
    expect(screen.queryByRole('button', { name: '更正完工服務日期' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '更正開始日並重排' })).not.toBeInTheDocument();
    fireEvent.click(button);
    expect(screen.getByRole('region', { name: '操作面板 reopen' })).toBeInTheDocument();
  });

  it('結果未明時 close／Escape／backdrop 皆不卸載，不能切換到其他受控操作', async () => {
    const onClose = vi.fn();
    const view = render(<OrderWorkbenchV2Drawer caseNo={CASE} branchType="normal" onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: '案件異動' }));
    const entry = screen.getByRole('button', { name: '取消／補登取消服務事實' });
    await waitFor(() => expect(entry).toBeEnabled()); fireEvent.click(entry);
    fireEvent.click(screen.getByRole('button', { name: '模擬結果未明' }));
    const close = screen.getByRole('button', { name: '← 返回待辦看板' });
    expect(close).toBeDisabled();
    expect(screen.getByRole('button', { name: '更正開始日並重排' })).toBeDisabled();
    fireEvent.click(close); fireEvent.keyDown(document, { key: 'Escape' });
    expect(view.container.querySelector('.order-v2-drawer-backdrop')).toBeNull();
    expect(onClose).not.toHaveBeenCalled(); expect(screen.getByRole('region', { name: '操作面板 cancellation' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '模擬收據與正式回讀完成' }));
    await waitFor(() => expect(close).toBeEnabled());
    fireEvent.click(close); expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('取消跨支線後依 exact-case GET 回讀，刷新四個 owner query 與 context，不抹掉面板完成狀態', async () => {
    const onObserved = vi.fn(); render(<OrderWorkbenchV2Drawer caseNo={CASE} branchType="normal" onClose={vi.fn()} onObserved={onObserved} />);
    fireEvent.click(screen.getByRole('button', { name: '案件異動' }));
    const entry = screen.getByRole('button', { name: '取消／補登取消服務事實' });
    await waitFor(() => expect(entry).toBeEnabled()); fireEvent.click(entry);
    const input = screen.getByLabelText('受控操作草稿'); fireEvent.change(input, { target: { value: '保留收據' } });
    let resolve!: (value: ReturnType<typeof page>) => void;
    mocks.core.mockImplementationOnce(() => new Promise<ReturnType<typeof page>>((done) => { resolve = done; }));
    mocks.detail.mockResolvedValue({ case_no: CASE, client_name: '測試客戶', client_id: 1, order_status: '訂單取消', identity_status: null, actual_start_date: '2026-09-01' });
    fireEvent.click(screen.getByRole('button', { name: '模擬收據與正式回讀完成' }));
    await waitFor(() => expect(mocks.core).toHaveBeenCalledTimes(2));
    expect(mocks.core).toHaveBeenLastCalledWith({ page_size: 20, lifecycle_scope: 'all', case_no_search: CASE }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(mocks.detail).toHaveBeenCalledTimes(2); expect(mocks.terms).toHaveBeenCalledTimes(2); expect(mocks.assignment).toHaveBeenCalledTimes(2);
    expect(onObserved).toHaveBeenCalledTimes(1); expect(input).toHaveValue('保留收據');
    expect(screen.getByText('此面板已觀察完成')).toBeInTheDocument();
    expect(screen.getByText('Owner context revision 1')).toBeInTheDocument();
    await act(async () => { resolve(page(true)); });
    await waitFor(() => expect(entry).toBeEnabled());
    expect(screen.queryByText('正常完工操作入口')).not.toBeInTheDocument();
    expect(screen.getAllByText('訂單取消').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('受控操作草稿')).toBe(input);
  });
});
