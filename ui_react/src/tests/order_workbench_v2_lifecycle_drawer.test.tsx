import { useState } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderWorkbenchV2Drawer } from '../components/OrderWorkbenchV2Drawer';

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
vi.mock('../components/OrderCancellationPanel', () => ({ OrderCancellationPanel: (props: Omit<OperationProps, 'label'>) => <Operation {...props} label="cancellation" /> }));
vi.mock('../components/OrderControlledReopenPanel', () => ({ OrderControlledReopenPanel: (props: Omit<OperationProps, 'label'>) => <Operation {...props} label="reopen" /> }));
vi.mock('../components/OrderActualStartPanel', () => ({ OrderActualStartPanel: (props: Omit<OperationProps, 'label'>) => <Operation {...props} label="actual-start" /> }));
vi.mock('../components/OrderWorkbenchV2OwnerContext', () => ({ OrderWorkbenchV2OwnerContext: ({ revision }: { revision: number }) => <p>Owner context revision {revision}</p> }));
vi.mock('../components/OrderServiceCompletionActions', () => ({ OrderServiceCompletionActions: () => <p>正常完工操作入口</p> }));
vi.mock('../api/orders/order_core_stage_projection_client', () => ({ orderCoreStageProjectionClient: { getCoreStageTimelines: mocks.core } }));
vi.mock('../api/orders/order_query_client', () => ({ ordersQueryClient: { getOrderDetail: mocks.detail, getOrderTerms: mocks.terms, getAssignmentPlan: mocks.assignment } }));
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
    mocks.assignment.mockResolvedValue({ case_no: CASE, assignments: [] });
  });

  it.each([
    ['取消／補登取消服務事實', 'cancellation'],
    ['受控重開取消案件', 'reopen'],
    ['確認／更正實際開始日', 'actual-start'],
  ])('%s 的明確入口能展開對應正式操作面板', async (entry, label) => {
    render(<OrderWorkbenchV2Drawer caseNo={CASE} branchType="normal" onClose={vi.fn()} />);
    const button = screen.getByRole('button', { name: entry });
    await waitFor(() => expect(button).toBeEnabled());
    expect(screen.queryByLabelText('受控操作草稿')).not.toBeInTheDocument();
    fireEvent.click(button);
    expect(screen.getByRole('region', { name: `操作面板 ${label}` })).toBeInTheDocument();
  });

  it('結果未明時 close／Escape／backdrop 皆不卸載，不能切換到其他受控操作', async () => {
    const onClose = vi.fn();
    const view = render(<OrderWorkbenchV2Drawer caseNo={CASE} branchType="normal" onClose={onClose} />);
    const entry = screen.getByRole('button', { name: '取消／補登取消服務事實' });
    await waitFor(() => expect(entry).toBeEnabled()); fireEvent.click(entry);
    fireEvent.click(screen.getByRole('button', { name: '模擬結果未明' }));
    const close = screen.getByRole('button', { name: '關閉工作 Drawer' });
    expect(close).toBeDisabled();
    expect(screen.getByRole('button', { name: '受控重開取消案件' })).toBeDisabled();
    fireEvent.click(close); fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.mouseDown(view.container.querySelector('.order-v2-drawer-backdrop')!);
    expect(onClose).not.toHaveBeenCalled(); expect(screen.getByRole('region', { name: '操作面板 cancellation' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '模擬收據與正式回讀完成' }));
    await waitFor(() => expect(close).toBeEnabled());
    fireEvent.keyDown(document, { key: 'Escape' }); expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('取消跨支線後依 exact-case GET 回讀，刷新四個 owner query 與 context，不抹掉面板完成狀態', async () => {
    const onObserved = vi.fn(); render(<OrderWorkbenchV2Drawer caseNo={CASE} branchType="normal" onClose={vi.fn()} onObserved={onObserved} />);
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
    expect(screen.getByText('訂單取消')).toBeInTheDocument();
    expect(screen.getByLabelText('受控操作草稿')).toBe(input);
  });
});
