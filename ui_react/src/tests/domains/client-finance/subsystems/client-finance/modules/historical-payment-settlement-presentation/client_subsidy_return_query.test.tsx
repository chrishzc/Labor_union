import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ClientSubsidyReturnQueryPanel } from '../../../../../../../components/ClientSubsidyReturnQueryPanel';
import { clientSubsidyReturnQueryClient, type ClientSubsidyReturnQuery } from '../../../../../../../api/client_finance/client_subsidy_return_query_client';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';

const props = { targetMonth: '2026-10', onMonthChange: vi.fn(), onOpenPayables: vi.fn() };
const data: ClientSubsidyReturnQuery = { rows: [
  { case_no: 'CASE-A', client_name: '補助客戶甲', order_status: '訂單完成', amount_ntd: 12000, due_date: '2026-08-15', is_estimate: true },
  { case_no: 'CASE-B', client_name: '補助客戶乙', order_status: '服務中', amount_ntd: null, due_date: null, is_estimate: true },
], next_cursor: null };
const response = (value: unknown) => new Response(JSON.stringify({ success: true, message: 'ok', data: value, error: null }), { headers: { 'content-type': 'application/json' } });

describe('case-based customer subsidy query', () => {
  beforeEach(() => { vi.restoreAllMocks(); vi.spyOn(sessionClient, 'getToken').mockReturnValue('test-query-session'); });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('loads the owner GET without a default month gate or posted obligation requirement', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(data));
    vi.stubGlobal('fetch', fetchMock);
    render(<ClientSubsidyReturnQueryPanel {...props} />);
    expect(await screen.findByText('CASE-A')).toBeInTheDocument();
    expect(screen.getByText('CASE-B')).toBeInTheDocument();
    const table = screen.getByRole('table');
    expect(within(table).getByRole('columnheader', { name: '應退款日期' })).toBeInTheDocument();
    expect(within(table).getByText('2026-08-15')).toBeInTheDocument();
    expect(within(table).getByText('預估')).toBeInTheDocument();
    expect(within(table).getByText('待確認')).toBeInTheDocument();
    expect(within(table).getByText('待結案')).toBeInTheDocument();
    expect(within(table).queryByRole('columnheader', { name: /到期狀態|已退|還欠|剩餘/ })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/finance-reports/client-subsidy-returns?page_size=100', expect.objectContaining({ method: 'GET', headers: expect.objectContaining({ Authorization: 'Bearer test-query-session' }) }));
  });

  it('searches the owner and makes month filtering optional, then clears both for all cases', async () => {
    const query = vi.spyOn(clientSubsidyReturnQueryClient, 'query').mockResolvedValue(data);
    render(<ClientSubsidyReturnQueryPanel {...props} />);
    await screen.findByText('CASE-A');
    fireEvent.change(screen.getByLabelText('客戶姓名或案件編號'), { target: { value: ' 客戶乙 ' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢' }));
    await waitFor(() => expect(query).toHaveBeenLastCalledWith(expect.objectContaining({ search: '客戶乙', targetMonth: undefined, afterCaseNo: undefined })));
    fireEvent.click(screen.getByLabelText('依應退款月份篩選'));
    await waitFor(() => expect(query).toHaveBeenLastCalledWith(expect.objectContaining({ targetMonth: '2026-10' })));
    fireEvent.click(screen.getByRole('button', { name: '查看全部應退案件' }));
    await waitFor(() => expect(query).toHaveBeenLastCalledWith(expect.objectContaining({ search: undefined, targetMonth: undefined })));
  });

  it('automatically continues when a scanned page has no eligible results', async () => {
    const query = vi.spyOn(clientSubsidyReturnQueryClient, 'query').mockResolvedValueOnce({ rows: [], next_cursor: 'CASE-Z' }).mockResolvedValue(data);
    render(<ClientSubsidyReturnQueryPanel {...props} />);
    expect(await screen.findByText('CASE-A')).toBeInTheDocument();
    expect(query).toHaveBeenLastCalledWith(expect.objectContaining({ afterCaseNo: 'CASE-Z' }));
    expect(query).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('button', { name: /下一頁|返回第一頁/ })).not.toBeInTheDocument();
  });

  it('shows all 13 October matches and the full total when the owner returns 11 then 2', async () => {
    const rows = Array.from({ length: 13 }, (_, index) => ({ ...data.rows[0],
      case_no: `OCT-${String(index + 1).padStart(3, '0')}`, amount_ntd: (index + 1) * 1000, due_date: '2026-10-15' }));
    const fetchMock = vi.fn().mockResolvedValueOnce(response({ rows: [], next_cursor: null }))
      .mockResolvedValueOnce(response({ rows: rows.slice(0, 11), next_cursor: 'OCT-011' }))
      .mockResolvedValueOnce(response({ rows: rows.slice(11), next_cursor: null }));
    vi.stubGlobal('fetch', fetchMock);
    render(<ClientSubsidyReturnQueryPanel {...props} />);
    await screen.findByText(/沒有符合條件/);
    fireEvent.click(screen.getByLabelText('依應退款月份篩選'));
    expect(await screen.findByText('OCT-013')).toBeInTheDocument();
    const table = screen.getByRole('table');
    expect(within(table).getAllByRole('row')).toHaveLength(14);
    const summary = screen.getByRole('group', { name: '補助退款案件摘要' });
    expect(summary).toHaveTextContent('13 筆');
    expect(summary).toHaveTextContent('NT$ 91,000');
    expect(summary).toHaveTextContent('符合條件案件數');
    expect(screen.queryByRole('button', { name: /下一頁|返回第一頁/ })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.slice(1).map(call => call[0])).toEqual([
      '/api/v1/finance-reports/client-subsidy-returns?page_size=100&target_month=2026-10',
      '/api/v1/finance-reports/client-subsidy-returns?page_size=100&target_month=2026-10&after_case_no=OCT-011',
    ]);
  });

  it('does not present a partial result when a later request fails', async () => {
    vi.spyOn(clientSubsidyReturnQueryClient, 'query')
      .mockResolvedValueOnce({ rows: [data.rows[0]], next_cursor: 'CASE-A' })
      .mockRejectedValueOnce(new ApiHttpError(503, 'unavailable', 'private detail'))
      .mockResolvedValue(data);
    render(<ClientSubsidyReturnQueryPanel {...props} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('補助退款資料暫時無法取得');
    expect(screen.queryByText('CASE-A')).not.toBeInTheDocument();
    expect(screen.queryByRole('group', { name: '補助退款案件摘要' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新查詢' }));
    expect(await screen.findByText('CASE-B')).toBeInTheDocument();
  });

  it('aborts stale results and keeps safe errors retryable', async () => {
    let finishOld!: (value: ClientSubsidyReturnQuery) => void;
    const query = vi.spyOn(clientSubsidyReturnQueryClient, 'query').mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve; })).mockRejectedValueOnce(new ApiHttpError(403, 'forbidden', 'private detail')).mockResolvedValue({ rows: [], next_cursor: null });
    render(<ClientSubsidyReturnQueryPanel {...props} />);
    const signal = query.mock.calls[0][0]!.signal!;
    fireEvent.click(screen.getByLabelText('依應退款月份篩選'));
    expect(await screen.findByRole('alert')).toHaveTextContent('目前帳號沒有查詢');
    expect(signal.aborted).toBe(true);
    await act(async () => finishOld(data));
    expect(screen.queryByText('CASE-A')).not.toBeInTheDocument();
    expect(screen.queryByText('private detail')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新查詢' }));
    expect(await screen.findByText(/沒有符合條件/)).toBeInTheDocument();
  });

  it('preserves exact case entry and rejects wrong, duplicate, or private response fields', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(response({ rows: [data.rows[0]], next_cursor: null }));
    vi.stubGlobal('fetch', fetchMock);
    render(<ClientSubsidyReturnQueryPanel {...props} initialCaseNo="CASE-A" />);
    await screen.findByText('CASE-A');
    expect(fetchMock.mock.calls[0][0]).toContain('case_no=CASE-A');
    fetchMock.mockResolvedValueOnce(response(data));
    await expect(clientSubsidyReturnQueryClient.query({ caseNo: 'CASE-A' })).rejects.toThrow('案件不一致');
    fetchMock.mockResolvedValueOnce(response({ rows: [data.rows[0], data.rows[0]], next_cursor: null }));
    await expect(clientSubsidyReturnQueryClient.query()).rejects.toThrow('案件重複');
    fetchMock.mockResolvedValueOnce(response({ rows: [{ ...data.rows[0], bank_account: 'private' }], next_cursor: null }));
    await expect(clientSubsidyReturnQueryClient.query()).rejects.toThrow();
    vi.mocked(sessionClient.getToken).mockReturnValue(null);
    await expect(clientSubsidyReturnQueryClient.query()).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });
});
