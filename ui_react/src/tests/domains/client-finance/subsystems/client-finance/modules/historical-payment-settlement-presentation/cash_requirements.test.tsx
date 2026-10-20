/** CASHPLAN-05/06: complete typed loading, unknown facts, refresh and existing payable tab. */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { transport } from '../../../../../../../api/shared/transport';
import { cashRequirementsQueryClient, type CashRequirementRow } from '../../../../../../../api/accounts_payable/cash_requirements_query_client';
import { accountsPayableQueryClient } from '../../../../../../../api/accounts_payable/accounts_payable_query_client';
import { accountsPayableExportClient } from '../../../../../../../api/accounts_payable/accounts_payable_export_client';
import { CashRequirementsPanel } from '../../../../../../../components/CashRequirementsPanel';
import { FinancePage } from '../../../../../../../pages/FinancePage';
import { ACCOUNTS_PAYABLE_RESPONSE } from '../../../../../../fixtures/finance/finance_query_contract_fixtures';

function row(changes: Partial<CashRequirementRow> = {}): CashRequirementRow {
  return { row_id: 'C-1:staff:1', case_no: 'C-1', recipient_name: '月嫂甲', payment_type: 'staff_payable',
    certainty: 'confirmed', source: 'staff_obligation', payment_status: 'pending' as const, source_amount_ntd: 24000, unpaid_amount_ntd: 18000,
    payment_date: '2026-11-15', date_is_estimate: false, pending_reasons: [], ...changes };
}
function response(rows: CashRequirementRow[], next_cursor: string | null = null) {
  return { success: true, message: '預估資金需求', data: { rows, next_cursor }, error: null };
}

beforeEach(() => { vi.restoreAllMocks(); window.location.hash = ''; });
afterEach(() => vi.unstubAllGlobals());

describe('cash requirements typed query', () => {
  it('reads every bounded page using only authenticated GET and preserves unknowns', async () => {
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('mock-token');
    const get = vi.spyOn(transport, 'get').mockResolvedValueOnce(response([], 'C-1'))
      .mockResolvedValueOnce(response([row({ row_id: 'C-2:unknown', case_no: 'C-2', unpaid_amount_ntd: null, payment_date: null })]));
    const post = vi.spyOn(transport, 'post');
    const rows = await cashRequirementsQueryClient.queryAll();
    expect(rows).toHaveLength(1); expect(rows[0].unpaid_amount_ntd).toBeNull();
    expect(get).toHaveBeenCalledTimes(2);
    expect(get.mock.calls[1][1]).toMatchObject({ token: 'mock-token', params: { after_case_no: 'C-1', page_size: 100 } });
    expect(post).not.toHaveBeenCalled();
  });

  it('rejects unauthenticated access, duplicate identities, stalled cursors and partial failure', async () => {
    vi.spyOn(sessionClient, 'getToken').mockReturnValue(null);
    const get = vi.spyOn(transport, 'get');
    await expect(cashRequirementsQueryClient.queryAll()).rejects.toMatchObject({ status: 401 });
    expect(get).not.toHaveBeenCalled();
    vi.mocked(sessionClient.getToken).mockReturnValue('mock-token');
    get.mockResolvedValueOnce(response([row(), row()]));
    await expect(cashRequirementsQueryClient.queryAll()).rejects.toThrow('重複');
    get.mockResolvedValueOnce(response([], 'C-1')).mockResolvedValueOnce(response([], 'C-1'));
    await expect(cashRequirementsQueryClient.queryAll()).rejects.toThrow('游標');
    get.mockResolvedValueOnce(response([row()], 'C-1')).mockRejectedValueOnce(new Error('第二批失敗'));
    await expect(cashRequirementsQueryClient.queryAll()).rejects.toThrow('第二批失敗');
  });

  it('strictly rejects retired sources and cancels the entire query before a next page', async () => {
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('mock-token');
    const get = vi.spyOn(transport, 'get').mockResolvedValueOnce(response([row({ payment_type: 'government_overpayment_return' as never })]));
    await expect(cashRequirementsQueryClient.queryAll()).rejects.toThrow();
    const controller = new AbortController();
    get.mockImplementationOnce(async () => { controller.abort(); return response([], 'C-1'); });
    await expect(cashRequirementsQueryClient.queryAll(controller.signal)).rejects.toThrow();
    expect(get).toHaveBeenCalledTimes(2);
  });
});

describe('cash planning panel', () => {
  it('groups known amounts by month and keeps unknown dates visible under any month filter', async () => {
    vi.spyOn(cashRequirementsQueryClient, 'queryAll').mockResolvedValue([
      row(), row({ row_id: 'C-1:subsidy', payment_type: 'client_subsidy_return', certainty: 'estimated', source: 'subsidy_estimate',
        payment_status: 'pending' as const, source_amount_ntd: 12000, unpaid_amount_ntd: 12000, payment_date: '2027-01-15', date_is_estimate: true,
        pending_reasons: ['服務尚未完成'] }),
      row({ row_id: 'C-2:unknown', case_no: 'C-2', payment_status: 'pending' as const, source_amount_ntd: null, unpaid_amount_ntd: null, payment_date: null, pending_reasons: ['金額待確認'] }),
    ]);
    render(<CashRequirementsPanel />);
    expect(await screen.findByRole('region', { name: '2026-11 資金需求' })).toHaveTextContent('NT$ 18,000');
    expect(screen.getByRole('region', { name: '2027-01 資金需求' })).toHaveTextContent('預估付款日 2027-01-15');
    expect(screen.getByText('NT$ 30,000')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('combobox', { name: '付款月份' }), { target: { value: '2026-11' } });
    expect(screen.queryByRole('region', { name: '2027-01 資金需求' })).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: '付款日期待確認項目' })).toHaveTextContent('C-2');
    expect(screen.getByRole('region', { name: '付款日期待確認項目' })).toHaveTextContent('金額待確認');
    expect(screen.queryByRole('button', { name: /下載|付款|建立退款/ })).not.toBeInTheDocument();
  });

  it('requeries updated owner values and discards late results after unmount', async () => {
    let resolve!: (rows: CashRequirementRow[]) => void;
    const query = vi.spyOn(cashRequirementsQueryClient, 'queryAll').mockResolvedValueOnce([row()])
      .mockResolvedValueOnce([row({ unpaid_amount_ntd: 9000 })])
      .mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    const view = render(<CashRequirementsPanel />);
    await screen.findByRole('region', { name: '2026-11 資金需求' });
    fireEvent.click(screen.getByRole('button', { name: '重新查詢預估' }));
    await waitFor(() => expect(screen.getByRole('region', { name: '2026-11 資金需求' })).toHaveTextContent('NT$ 9,000'));
    fireEvent.click(screen.getByRole('button', { name: '重新查詢預估' }));
    await waitFor(() => expect(query).toHaveBeenCalledTimes(3));
    const signal = query.mock.calls[2][0];
    view.unmount(); expect(signal?.aborted).toBe(true);
    await act(async () => resolve([row()]));
    expect(screen.queryByText('C-1')).not.toBeInTheDocument();
  });

  it('shows empty and failed queries explicitly instead of displaying partial totals', async () => {
    vi.spyOn(cashRequirementsQueryClient, 'queryAll').mockResolvedValueOnce([]).mockRejectedValueOnce(new Error('失敗'));
    render(<CashRequirementsPanel />);
    expect(await screen.findByText('目前沒有已排班案件的未付款或預估退款項目。')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新查詢預估' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('預估資金需求暫時無法取得');
    expect(screen.queryByText('已知金額小計')).not.toBeInTheDocument();
  });
});

describe('existing payable composition', () => {
  it('keeps accounting export independent while replacing the old two tabs with filters', async () => {
    window.location.hash = '#finance?tab=accounts-payable';
    const confirmed = vi.spyOn(accountsPayableQueryClient, 'query').mockResolvedValue(ACCOUNTS_PAYABLE_RESPONSE.data);
    const forecast = vi.spyOn(cashRequirementsQueryClient, 'queryAll').mockResolvedValue([row()]);
    const download = vi.spyOn(accountsPayableExportClient, 'download');
    render(<FinancePage />);
    await screen.findByLabelText('付款摘要');
    expect(screen.queryByRole('tablist', { name: '應付帳款檢視' })).not.toBeInTheDocument();
    expect(within(screen.getByRole('navigation', { name: '帳務工作區' })).getAllByRole('button')).toHaveLength(3);
    expect(screen.getByRole('button', { name: '下載應付帳款 Excel' })).toBeEnabled();
    fireEvent.change(screen.getByLabelText('付款狀態'), { target: { value: 'service_pending' } });
    expect(screen.queryByText('月嫂甲')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '下載應付帳款 Excel' })).toBeEnabled();
    expect(forecast).toHaveBeenCalledTimes(1); expect(confirmed).not.toHaveBeenCalled(); expect(download).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '重新整理' }));
    await waitFor(() => expect(forecast).toHaveBeenCalledTimes(2));
    expect(confirmed).not.toHaveBeenCalled(); expect(download).not.toHaveBeenCalled();
  });
});
