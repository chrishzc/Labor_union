/** Verify the real reminder component, typed reader and stale-result boundaries. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LineCustomerServiceReminderWorkbench } from '../../../../../../components/LineCustomerServiceReminderWorkbench';
import { LineManagementPage } from '../../../../../../pages/LineManagementPage';
import { customerServiceClient } from '../../../../../../api/customer_service/customer_service_client';
import { sessionClient } from '../../../../../../api/auth/session_client';
import { transport } from '../../../../../../api/shared/transport';
import { CUSTOMER_SERVICE_REMINDER_PAGE_FIXTURE as page } from './fixtures/customer_service_reminder_fixtures';

afterEach(() => { vi.restoreAllMocks(); window.history.replaceState(null, '', '/'); });

describe('客服案件精簡提醒', () => {
  it('只提供三狀態、搜尋、來源、重新整理與清單，無明細或 mutation', async () => {
    const customer = { listReminders: vi.fn().mockResolvedValue(page), getTicketDetail: vi.fn(), previewResolve: vi.fn(), applyResolve: vi.fn() };
    render(<LineManagementPage customerService={customer} />);
    await screen.findByText('測試客戶');
    const workspace = screen.getByRole('region', { name: '客服案件提醒' });
    expect(within(workspace).getAllByRole('button')).toHaveLength(4);
    expect(within(workspace).getAllByRole('columnheader')).toHaveLength(4);
    expect(within(workspace).queryByRole('button', { name: /已結案|查看明細|開啟處理|繼續處理|預覽情境/ })).not.toBeInTheDocument();
    expect(within(workspace).queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(customer.getTicketDetail).not.toHaveBeenCalled();
    expect(customer.previewResolve).not.toHaveBeenCalled();
    expect(customer.applyResolve).not.toHaveBeenCalled();
    expect(customer.listReminders).toHaveBeenCalledWith(expect.objectContaining({ status: 'open', page: 1 }), expect.objectContaining({ signal: expect.any(AbortSignal) }));
  });

  it('搜尋與來源交給 server，保留後端結果，不在頁面重新猜來源或過濾', async () => {
    const listReminders = vi.fn().mockResolvedValue(page);
    render(<LineCustomerServiceReminderWorkbench client={{ listReminders }} />);
    await screen.findByText('測試客戶');
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: '0031' } });
    fireEvent.change(screen.getByRole('combobox', { name: '篩選客服進件來源' }), { target: { value: 'feedback' } });
    await waitFor(() => expect(listReminders).toHaveBeenLastCalledWith(expect.objectContaining({ source: 'feedback', search: '0031', page: 1 }), expect.any(Object)));
    expect(within(await screen.findByRole('table')).getByText('回答未解決回饋')).toBeInTheDocument();
    expect(screen.queryByText('多個來源')).not.toBeInTheDocument();
  });

  it('依 server total 真實翻頁，改狀態或來源回到第一頁', async () => {
    const listReminders = vi.fn().mockImplementation(async query => ({ ...page, page: query.page, total: 26 }));
    render(<LineCustomerServiceReminderWorkbench client={{ listReminders }} />);
    await screen.findByText('測試客戶');
    fireEvent.click(screen.getByRole('button', { name: '下一頁' }));
    await screen.findByText('第 2／2 頁');
    expect(screen.getByRole('button', { name: '下一頁' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /待接手/ }));
    await waitFor(() => expect(listReminders).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'waiting', page: 1 }), expect.any(Object)));
    await screen.findByText('第 1／2 頁');
  });

  it('loading／failure 不顯示假零或空狀態；重新整理可恢復', async () => {
    const listReminders = vi.fn().mockRejectedValueOnce(new Error('private SQL payload')).mockResolvedValue(page);
    render(<LineCustomerServiceReminderWorkbench client={{ listReminders }} />);
    expect(screen.getByRole('status')).toHaveTextContent('正在載入客服案件');
    expect(screen.queryByText('0')).not.toBeInTheDocument();
    await screen.findByRole('alert');
    expect(screen.queryByText('private SQL payload')).not.toBeInTheDocument();
    expect(screen.queryByText('目前沒有待處理案件')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新整理' }));
    await screen.findByText('測試客戶');
  });

  it('合法零筆有空狀態，未知來源仍保留，無姓名不洩漏 identity', async () => {
    const listReminders = vi.fn().mockResolvedValueOnce({ ...page, items: [], total: 0 }).mockResolvedValue({ ...page, items: [{ ...page.items[0], client_name: null, case_no: null, source: 'unknown', sources: ['unknown'], reason: 'unknown' }] });
    render(<LineCustomerServiceReminderWorkbench client={{ listReminders }} />);
    await screen.findByText('目前沒有待處理案件');
    fireEvent.click(screen.getByRole('button', { name: '重新整理' }));
    await screen.findByText('未具名使用者');
    expect(within(screen.getByRole('table')).getByText('來源待確認')).toBeInTheDocument();
    expect(screen.getByText('#31')).toBeInTheDocument();
  });

  it('取消與晚到回應不得覆蓋新篩選結果', async () => {
    let finish!: (value: typeof page) => void;
    const pending = new Promise<typeof page>(resolve => { finish = resolve; });
    const listReminders = vi.fn().mockReturnValueOnce(pending).mockResolvedValue({ ...page, items: [{ ...page.items[0], client_name: '最新篩選結果' }] });
    render(<LineCustomerServiceReminderWorkbench client={{ listReminders }} />);
    await waitFor(() => expect(listReminders).toHaveBeenCalledTimes(1));
    const signal = listReminders.mock.calls[0][1].signal;
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: '31' } });
    await screen.findByText('最新篩選結果');
    expect(signal.aborted).toBe(true);
    finish(page);
    await waitFor(() => expect(screen.queryByText('測試客戶')).not.toBeInTheDocument());
  });

  it('保留查詢位置，拒絕舊的 resolved 篩選而不打開操作頁', async () => {
    window.history.replaceState(null, '', '/#line-management?ticket_state=resolved&ticket_source=feedback');
    const listReminders = vi.fn().mockResolvedValue(page);
    render(<LineCustomerServiceReminderWorkbench client={{ listReminders }} />);
    await screen.findByText('測試客戶');
    expect(listReminders).toHaveBeenCalledWith(expect.objectContaining({ status: 'open', source: 'feedback' }), expect.any(Object));
    expect(window.location.hash).toContain('ticket_source=feedback');
    expect(window.location.hash).not.toContain('resolved');
  });
});

describe('客服提醒 typed client', () => {
  it('只送 reader GET；嚴格拒絕 raw 或已結案資料', async () => {
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('unit-test-session');
    const get = vi.spyOn(transport, 'get').mockResolvedValue({ success: true, message: 'ok', error: null, data: page });
    const result = await customerServiceClient.listReminders({ status: 'open', source: 'feedback', page: 2 });
    expect(result).toEqual(page);
    expect(get).toHaveBeenCalledWith('/api/v1/customer-service/tickets/reminders', expect.objectContaining({ params: { status: 'open', source: 'feedback', page: 2 } }));
    get.mockResolvedValue({ success: true, message: 'ok', error: null, data: { ...page, items: [{ ...page.items[0], line_user_id: 'not-allowed' }] } });
    await expect(customerServiceClient.listReminders()).rejects.toThrow();
    get.mockResolvedValue({ success: true, message: 'ok', error: null, data: { ...page, items: [{ ...page.items[0], status: 'resolved' }] } });
    await expect(customerServiceClient.listReminders()).rejects.toThrow();
  });
});
