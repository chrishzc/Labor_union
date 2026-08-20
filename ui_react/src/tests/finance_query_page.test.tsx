/**
 * File: finance_query_page.test.tsx
 * Description: 驗證FinancePage active-tab query budget、server資料與native-disabled mutations。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { clientReceiptQueryClient } from '../api/client_finance/client_receipt_query_client';
import { staffPayablesQueryClient } from '../api/staff_payables/staff_payables_query_client';
import { accountsPayableQueryClient } from '../api/accounts_payable/accounts_payable_query_client';
import { financeImportQueryClient } from '../api/finance_import/finance_import_query_client';
import { FinancePage } from '../pages/FinancePage';
import { RECEIPT_RESPONSE, STAFF_PAYABLES_RESPONSE, ACCOUNTS_PAYABLE_RESPONSE, FINANCE_BATCH_RESPONSE, FINANCE_MANIFEST_RESPONSE } from './fixtures/finance/finance_query_contract_fixtures';

describe('FinancePage query-only presentation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({ items: [{ case_no: 'CASE-FIN-001', client_name: '去敏客戶', order_status: '服務中', staff_name: null, identity_status: null, start_date: null, end_date: null, actual_start_date: null, actual_end_date: null, service_days: null, total_employer_self_pay_payable: null }], next_cursor: null, etag: 'c'.repeat(64) });
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ items: [{ id: 11, name: '去敏人員', phone: null }], next_cursor: null });
    vi.spyOn(clientReceiptQueryClient, 'query').mockResolvedValue(RECEIPT_RESPONSE.data);
    vi.spyOn(staffPayablesQueryClient, 'query').mockResolvedValue(STAFF_PAYABLES_RESPONSE.data);
    vi.spyOn(accountsPayableQueryClient, 'query').mockResolvedValue(ACCOUNTS_PAYABLE_RESPONSE.data);
    vi.spyOn(financeImportQueryClient, 'listBatches').mockResolvedValue(FINANCE_BATCH_RESPONSE.data);
    vi.spyOn(financeImportQueryClient, 'getManifest').mockResolvedValue(FINANCE_MANIFEST_RESPONSE.data);
  });

  it('loads only the active tab and keeps mutation controls disabled', async () => {
    render(<FinancePage />);
    await waitFor(() => expect(screen.getByText('OBL-C-1')).toBeInTheDocument());
    expect(ordersQueryClient.getOrderSummaries).toHaveBeenCalledTimes(1);
    expect(clientReceiptQueryClient.query).toHaveBeenCalledTimes(1);
    expect(staffDirectoryClient.queryPage).not.toHaveBeenCalled();
    expect(document.querySelector('[data-control-id="finance.client-receipt.settle"]')).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: '月嫂應付款' }));
    await waitFor(() => expect(screen.getByText('OBL-S-1')).toBeInTheDocument());
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(1);
    expect(staffPayablesQueryClient.query).toHaveBeenCalledTimes(1);
    expect(document.querySelector('[data-control-id="finance.staff-payable.mark-paid"]')).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: '應付帳款' }));
    await waitFor(() => expect(screen.getByText(/\*{8}9012/)).toBeInTheDocument());
    expect(accountsPayableQueryClient.query).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('123456789012')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="finance.accounts-payable.export-xlsx"]')).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Finance Import' }));
    await waitFor(() => expect(screen.getAllByText('BATCH-FIN-021').length).toBeGreaterThan(0));
    expect(financeImportQueryClient.listBatches).toHaveBeenCalledTimes(1);
    expect(financeImportQueryClient.getManifest).toHaveBeenCalledTimes(1);
    expect(document.querySelector('[data-control-id="finance.finance-import.apply"]')).toBeDisabled();
  });
});
