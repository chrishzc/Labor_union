/** Group observation acceptance: real component, bounded typed reads and no mutations. */
import { useState } from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LineOrderGroupWorkbench } from '../../../../../../components/LineOrderGroupWorkbench';
import { LineOrderGroupQueryError } from '../../../../../../api/line_order_groups/line_order_group_query_errors';
import type { LineOrderGroupWorkspaceClient } from '../../../../../../api/line_order_groups/line_order_group_query_client';
import { lineOrderGroupQueryClient } from '../../../../../../api/line_order_groups/line_order_group_query_client';
import { sessionClient } from '../../../../../../api/auth/session_client';
import type { LineOrderGroupStatus, LineOrderGroupWorkspaceRecord, LineOrderGroupWorkspaceEvent } from '../../../../../../api/line_order_groups/line_order_group_query_schemas';

const event: LineOrderGroupWorkspaceEvent = { event_key: 'runtime:1', case_no: 'CASE-1', event_type: 'member_left', occurred_at: '2026-10-15T02:00:00Z', participant_role: 'staff', participant_name: '測試月嫂' };
const record: LineOrderGroupWorkspaceRecord = { case_no: 'CASE-1', status: 'attention', customer_name: '測試客戶', bound_at: '2026-10-14T02:00:00Z', last_invitation_at: '2026-10-14T03:00:00Z', members: [{ role: 'customer', name: '測試客戶', membership_status: 'joined' }, { role: 'staff', name: '測試月嫂', membership_status: 'left' }], latest_event: event };
const page = (items: LineOrderGroupWorkspaceRecord[] = [record], number = 1, total = items.length) => ({ items, page: number, page_size: 25, total, total_pages: Math.ceil(total / 25) });
function client(): LineOrderGroupWorkspaceClient {
  return { workspaceList: vi.fn().mockResolvedValue(page()), workspaceDetail: vi.fn().mockResolvedValue(record), workspaceEvents: vi.fn().mockResolvedValue({ items: [event], page: 1, page_size: 25, total: 1, total_pages: 1 }) };
}
function mount(api = client(), startPage = 1) {
  function Workspace() {
    const [search, setSearch] = useState(''); const [status, setStatus] = useState<LineOrderGroupStatus | 'all'>('all'); const [number, setNumber] = useState(startPage);
    return <LineOrderGroupWorkbench client={api} search={search} status={status} page={number} onSearchChange={setSearch} onStatusChange={setStatus} onPageChange={setNumber} />;
  }
  return { api, ...render(<Workspace />) };
}
function expandHistory() {
  const details = screen.getByText('群組歷程').closest('details')!;
  act(() => { details.open = true; fireEvent(details, new Event('toggle')); });
}
afterEach(() => vi.restoreAllMocks());

describe('三方服務群組精簡工作區', () => {
  it('only shows three useful columns and reads events after expanding the drawer history', async () => {
    const { api } = mount();
    await screen.findByRole('button', { name: '查看案件 CASE-1 群組明細' });
    expect(screen.getAllByRole('columnheader').map(item => item.textContent)).toEqual(['案件', '群組狀態', '最近動態']);
    expect(screen.queryByRole('button', { name: /發送|綁定|解除/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看案件 CASE-1 群組明細' }));
    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByText('測試月嫂');
    expect(within(dialog).getByText('已離開')).toBeInTheDocument();
    expect(api.workspaceEvents).not.toHaveBeenCalled();
    expandHistory(); await waitFor(() => expect(api.workspaceEvents).toHaveBeenCalledTimes(1));
    expect(within(dialog).queryByText('member_left')).not.toBeInTheDocument();
    const help = within(dialog).getByText('綁定與邀請方式').closest('details')!;
    expect(help.open).toBe(false);
    expect(help.textContent).toContain('訂金須已確認核銷');
  });

  it('uses server search and status and resets page instead of filtering the loaded page', async () => {
    const api = client();
    vi.mocked(api.workspaceList).mockImplementation(async query => page([record], query?.page ?? 1, 26));
    mount(api, 2); await screen.findByText('CASE-1');
    fireEvent.change(screen.getByRole('searchbox', { name: '搜尋案件編號' }), { target: { value: 'CASE-26' } });
    await waitFor(() => expect(api.workspaceList).toHaveBeenLastCalledWith({ search: 'CASE-26', status: undefined, page: 1, pageSize: 25 }, expect.any(Object)));
    fireEvent.change(screen.getByRole('combobox', { name: '群組狀態' }), { target: { value: 'attention' } });
    await waitFor(() => expect(api.workspaceList).toHaveBeenLastCalledWith({ search: 'CASE-26', status: 'attention', page: 1, pageSize: 25 }, expect.any(Object)));
  });

  it('keeps unknown information explicit and never invents successful membership', async () => {
    const api = client(); vi.mocked(api.workspaceList).mockResolvedValue(page([{ ...record, customer_name: null, latest_event: null, members: [{ role: 'customer', name: null, membership_status: 'unknown' }] }]));
    mount(api); await screen.findByText('客戶資料待確認');
    expect(screen.getByText('加入狀況待確認')).toBeInTheDocument();
    expect(screen.getByText('尚無群組動態紀錄')).toBeInTheDocument();
    expect(screen.queryByText('客戶與月嫂皆已加入')).not.toBeInTheDocument();
  });

  it('does not expose raw backend errors or treat failed reads as an empty group list', async () => {
    const api = client(); vi.mocked(api.workspaceList).mockRejectedValue(new LineOrderGroupQueryError('PRIVATE_DB_ERROR', 'raw U-sensitive C-group SQL failed', true));
    mount(api); await screen.findByRole('alert');
    expect(screen.queryByText(/PRIVATE_DB_ERROR|U-sensitive|SQL failed/)).not.toBeInTheDocument();
    expect(screen.queryByText('目前沒有服務群組綁定紀錄')).not.toBeInTheDocument();
    vi.mocked(api.workspaceList).mockResolvedValue(page([])); fireEvent.click(screen.getByRole('button', { name: '重試查詢' }));
    await screen.findByText('目前沒有服務群組綁定紀錄');
  });

  it('aborts old list and detail requests and ignores their late responses', async () => {
    const api = client(); let resolveOld!: (value: ReturnType<typeof page>) => void;
    vi.mocked(api.workspaceList).mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve; })).mockResolvedValue(page([{ ...record, case_no: 'CASE-2', latest_event: null }]));
    mount(api); await waitFor(() => expect(api.workspaceList).toHaveBeenCalledTimes(1));
    const oldSignal = vi.mocked(api.workspaceList).mock.calls[0][1]!.signal!;
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'CASE-2' } }); await screen.findByText('CASE-2');
    expect(oldSignal.aborted).toBe(true);
    await act(async () => resolveOld(page())); expect(screen.queryByText('CASE-1')).not.toBeInTheDocument();
    let resolveDetail!: (value: LineOrderGroupWorkspaceRecord) => void;
    vi.mocked(api.workspaceDetail).mockReturnValue(new Promise(resolve => { resolveDetail = resolve; }));
    fireEvent.click(screen.getByRole('button', { name: '查看案件 CASE-2 群組明細' }));
    await waitFor(() => expect(api.workspaceDetail).toHaveBeenCalled());
    const signal = vi.mocked(api.workspaceDetail).mock.calls[0][1]!.signal!;
    fireEvent.click(screen.getByRole('button', { name: '關閉群組明細' })); expect(signal.aborted).toBe(true);
    await act(async () => resolveDetail(record)); expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('preserves detail when the history fails and keeps separate history pagination', async () => {
    const api = client(); vi.mocked(api.workspaceEvents).mockRejectedValueOnce(new Error('provider raw detail')).mockResolvedValue({ items: [event], page: 1, page_size: 25, total: 26, total_pages: 2 });
    mount(api); await screen.findByText('CASE-1'); fireEvent.click(screen.getByRole('button', { name: '查看案件 CASE-1 群組明細' }));
    await within(await screen.findByRole('dialog')).findByText('測試月嫂'); expandHistory();
    await screen.findByRole('button', { name: '重試歷程' });
    expect(screen.getByText('已離開')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重試歷程' })); await screen.findByRole('button', { name: '下一頁群組事件' });
    vi.mocked(api.workspaceEvents).mockResolvedValue({ items: [{ ...event, event_key: 'binding:1', event_type: 'bound' }], page: 2, page_size: 25, total: 26, total_pages: 2 });
    fireEvent.click(screen.getByRole('button', { name: '下一頁群組事件' })); await screen.findByText('已綁定服務群組');
    expect(api.workspaceDetail).toHaveBeenCalledTimes(1);
    expect(api.workspaceEvents).toHaveBeenLastCalledWith('CASE-1', { page: 2, pageSize: 25 }, expect.any(Object));
  });

  it('shows empty search recovery and never calls a write API', async () => {
    const api = client(); vi.mocked(api.workspaceList).mockResolvedValueOnce(page()).mockResolvedValueOnce(page([])).mockResolvedValue(page());
    const fetch = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('unexpected network'));
    mount(api); await screen.findByText('CASE-1'); fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'missing' } });
    await screen.findByText('沒有符合條件的群組'); fireEvent.click(screen.getByRole('button', { name: '清除條件' })); await screen.findByText('CASE-1');
    expect(screen.getByRole('searchbox')).toHaveValue(''); expect(fetch).not.toHaveBeenCalled();
  });
});

describe('群組工作區 typed query', () => {
  function session() {
    sessionClient.setSession('isolated-group-token', { id: 7, username: 'reader', display_name: '群組查詢', role: 'system_admin', linked_line_user_id: null, capabilities: [], is_root: false, access_control_version: 1 });
  }
  const response = (value: unknown) => new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } });
  afterEach(() => sessionClient.clearSession());

  it('only sends bounded GET requests with literal search to the new workspace routes', async () => {
    session(); const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(response(page())).mockResolvedValueOnce(response(record)).mockResolvedValueOnce(response({ items: [event], page: 1, page_size: 25, total: 1, total_pages: 1 }));
    await lineOrderGroupQueryClient.workspaceList({ search: 'CASE_%', status: 'attention' });
    await lineOrderGroupQueryClient.workspaceDetail('CASE-1');
    await lineOrderGroupQueryClient.workspaceEvents('CASE-1');
    const urls = fetch.mock.calls.map(([url]) => String(url));
    expect(urls[0]).toContain('/workspace/numbered?search=CASE_%25&status=attention');
    expect(urls.slice(1)).toEqual(['/api/v1/line/order-groups/workspace/CASE-1', '/api/v1/line/order-groups/workspace/CASE-1/events/numbered?page=1&page_size=25']);
    expect(fetch.mock.calls.every(([, options]) => options?.method === 'GET')).toBe(true);
  });

  it('rejects response identity or metadata drift and any unexpected provider identifiers', async () => {
    session(); const fetch = vi.spyOn(globalThis, 'fetch');
    fetch.mockResolvedValueOnce(response({ ...record, case_no: 'OTHER', latest_event: null }));
    await expect(lineOrderGroupQueryClient.workspaceDetail('CASE-1')).rejects.toMatchObject({ code: 'LINE_ORDER_GROUP_IDENTITY_MISMATCH' });
    fetch.mockResolvedValueOnce(response({ ...page(), total_pages: 2 }));
    await expect(lineOrderGroupQueryClient.workspaceList()).rejects.toMatchObject({ code: 'LINE_ORDER_GROUP_PAGE_MISMATCH' });
    fetch.mockResolvedValueOnce(response({ ...record, actor_id: 'raw-provider-id' }));
    await expect(lineOrderGroupQueryClient.workspaceDetail('CASE-1')).rejects.toMatchObject({ code: 'LINE_ORDER_GROUP_SCHEMA_MISMATCH' });
    fetch.mockResolvedValueOnce(response({ items: [{ ...event, case_no: 'OTHER' }], page: 1, page_size: 25, total: 1, total_pages: 1 }));
    await expect(lineOrderGroupQueryClient.workspaceEvents('CASE-1')).rejects.toMatchObject({ code: 'LINE_ORDER_GROUP_IDENTITY_MISMATCH' });
  });
});
