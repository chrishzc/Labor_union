/**
 * File: finance_query_page.test.tsx
 * Description: 驗證FinancePage active-tab query budget、server資料與正常三步匯入邊界。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { clientReceiptQueryClient } from '../api/client_finance/client_receipt_query_client';
import { staffPayablesQueryClient } from '../api/staff_payables/staff_payables_query_client';
import { accountsPayableQueryClient } from '../api/accounts_payable/accounts_payable_query_client';
import { financeImportBlockerMessage } from '../adapters/finance/finance_import_query_adapter';
import { FinancePage } from '../pages/FinancePage';
import { RECEIPT_RESPONSE, STAFF_PAYABLES_RESPONSE, ACCOUNTS_PAYABLE_RESPONSE } from './fixtures/finance/finance_query_contract_fixtures';

describe('FinancePage query and guarded import presentation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({ items: [{ case_no: 'CASE-FIN-001', client_name: '去敏客戶', order_status: '服務中', staff_name: null, identity_status: null, start_date: null, end_date: null, actual_start_date: null, actual_end_date: null, service_days: null, total_employer_self_pay_payable: null }], next_cursor: null, etag: 'c'.repeat(64) });
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ items: [{ id: 11, name: '去敏人員', phone: null }], next_cursor: null });
    vi.spyOn(clientReceiptQueryClient, 'query').mockResolvedValue(RECEIPT_RESPONSE.data);
    vi.spyOn(staffPayablesQueryClient, 'query').mockResolvedValue(STAFF_PAYABLES_RESPONSE.data);
    vi.spyOn(accountsPayableQueryClient, 'query').mockResolvedValue(ACCOUNTS_PAYABLE_RESPONSE.data);
  });

  it('maps import blockers to closed operator messages', () => {
    expect(financeImportBlockerMessage(['fingerprint_collision', 'future_blocker']))
      .toBe('存在可能重複的銀行交易、預覽資料仍有待確認項目');
    expect(financeImportBlockerMessage([])).toBe('預覽未通過，請重新檢查。');
  });

  it('loads only the active tab and requires a selected workbook before import controls appear', async () => {
    render(<FinancePage />);
    await waitFor(() => expect(screen.getByText('OBL-C-1')).toBeInTheDocument());
    expect(ordersQueryClient.getOrderSummaries).toHaveBeenCalledTimes(1);
    expect(clientReceiptQueryClient.query).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/Account Version|Account version/)).not.toBeInTheDocument();
    expect(staffDirectoryClient.queryPage).not.toHaveBeenCalled();
    expect(screen.queryByText(/未開放/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '月嫂應付款' }));
    await waitFor(() => expect(screen.getByText('OBL-S-1')).toBeInTheDocument());
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(1);
    expect(staffPayablesQueryClient.query).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/^Version$|｜Version/)).not.toBeInTheDocument();
    expect(screen.queryByText(/未開放/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '應付帳款' }));
    await waitFor(() => expect(screen.getByText(/\*{8}9012/)).toBeInTheDocument());
    expect(accountsPayableQueryClient.query).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('123456789012')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="finance.accounts-payable.export-xlsx"]')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '銀行流水匯入' }));
    expect(screen.getByText('上傳檔案 → 預覽 → 匯入完成')).toBeInTheDocument();
    expect(screen.queryByText('已載入批次')).not.toBeInTheDocument();
    expect(screen.queryByText('歷史 Reprocess Run（loaded scope）')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="finance.finance-import.upload"]')).toBeDisabled();
    expect(document.querySelector('[data-control-id="finance.finance-import.apply"]')).toBeNull();
  });

  it('searches all server pages so a new case can be selected for receipt review', async () => {
    render(<FinancePage />);
    await waitFor(() => expect(screen.getByText('OBL-C-1')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('搜尋案件'), { target: { value: '116990824' } });

    await waitFor(() => expect(ordersQueryClient.getOrderSummaries).toHaveBeenLastCalledWith(
      { page_size: 200, query_text: '116990824' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
  });

  it('accumulates every case and staff page for finance selectors', async () => {
    const orderItem = {
      case_no: 'CASE-FIN-001', client_name: '去敏客戶', order_status: '服務中', staff_name: null,
      identity_status: null, start_date: null, end_date: null, actual_start_date: null,
      actual_end_date: null, service_days: null, total_employer_self_pay_payable: null,
    };
    vi.mocked(ordersQueryClient.getOrderSummaries)
      .mockResolvedValueOnce({ items: [orderItem], next_cursor: orderItem.case_no, etag: 'a'.repeat(64) })
      .mockResolvedValueOnce({ items: [{ ...orderItem, case_no: 'CASE-FIN-002', client_name: '第二頁客戶' }], next_cursor: null, etag: 'b'.repeat(64) });
    vi.mocked(staffDirectoryClient.queryPage)
      .mockResolvedValueOnce({ items: [{ id: 11, name: '第一頁人員', phone: null }], next_cursor: 11 })
      .mockResolvedValueOnce({ items: [{ id: 12, name: '第二頁人員', phone: null }], next_cursor: null });

    render(<FinancePage />);
    expect(await screen.findByRole('option', { name: /CASE-FIN-002｜第二頁客戶/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '月嫂應付款' }));
    expect(await screen.findByRole('option', { name: '第二頁人員' })).toBeInTheDocument();
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(2);
  });
});
