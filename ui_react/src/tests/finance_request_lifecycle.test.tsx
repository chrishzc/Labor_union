/**
 * File: finance_request_lifecycle.test.tsx
 * Description: 驗證Finance查詢在StrictMode與scope切換時維持單次請求並丟棄過期結果。
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { accountsPayableQueryClient } from '../api/accounts_payable/accounts_payable_query_client';
import { clientReceiptQueryClient } from '../api/client_finance/client_receipt_query_client';
import { financeImportQueryClient } from '../api/finance_import/finance_import_query_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { staffPayablesQueryClient } from '../api/staff_payables/staff_payables_query_client';
import { FinancePage } from '../pages/FinancePage';
import {
  ACCOUNTS_PAYABLE_RESPONSE,
  FINANCE_BATCH_RESPONSE,
  FINANCE_MANIFEST_RESPONSE,
  RECEIPT_RESPONSE,
  STAFF_PAYABLES_RESPONSE,
} from './fixtures/finance/finance_query_contract_fixtures';

const ORDER_PAGE = {
  items: [{
    case_no: 'CASE-FIN-001',
    client_name: '去敏客戶',
    order_status: '服務中',
    staff_name: null,
    identity_status: null,
    start_date: null,
    end_date: null,
    actual_start_date: null,
    actual_end_date: null,
    service_days: null,
    total_employer_self_pay_payable: null,
  }],
  next_cursor: null,
  etag: 'c'.repeat(64),
};

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe('Finance query request lifecycle', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue(ORDER_PAGE);
    vi.spyOn(clientReceiptQueryClient, 'query').mockResolvedValue(RECEIPT_RESPONSE.data);
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ items: [{ id: 11, name: '去敏人員', phone: null }], next_cursor: null });
    vi.spyOn(staffPayablesQueryClient, 'query').mockResolvedValue(STAFF_PAYABLES_RESPONSE.data);
    vi.spyOn(accountsPayableQueryClient, 'query').mockResolvedValue(ACCOUNTS_PAYABLE_RESPONSE.data);
    vi.spyOn(financeImportQueryClient, 'listBatches').mockResolvedValue(FINANCE_BATCH_RESPONSE.data);
    vi.spyOn(financeImportQueryClient, 'getManifest').mockResolvedValue(FINANCE_MANIFEST_RESPONSE.data);
    vi.spyOn(financeImportQueryClient, 'listReviewRows').mockResolvedValue({ items: [], next_after_row_id: null });
    vi.spyOn(financeImportQueryClient, 'listReprocessRuns').mockResolvedValue({ items: [], next_before_run_id: null });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('issues one initial query generation under StrictMode', async () => {
    render(<StrictMode><FinancePage /></StrictMode>);
    await waitFor(() => expect(screen.getByText('OBL-C-1')).toBeInTheDocument());

    expect(ordersQueryClient.getOrderSummaries).toHaveBeenCalledTimes(1);
    expect(clientReceiptQueryClient.query).toHaveBeenCalledTimes(1);
  });

  it('aborts an inactive tab request and ignores its late result', async () => {
    const pending = deferred<typeof ORDER_PAGE>();
    vi.mocked(ordersQueryClient.getOrderSummaries).mockReturnValueOnce(pending.promise);
    render(<StrictMode><FinancePage /></StrictMode>);
    await waitFor(() => expect(ordersQueryClient.getOrderSummaries).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(ordersQueryClient.getOrderSummaries).mock.calls[0]?.[1]?.signal;

    fireEvent.click(screen.getByRole('button', { name: '應付帳款' }));
    await waitFor(() => expect(accountsPayableQueryClient.query).toHaveBeenCalledTimes(1));
    expect(signal?.aborted).toBe(true);

    await act(async () => {
      pending.resolve(ORDER_PAGE);
      await Promise.resolve();
    });

    expect(clientReceiptQueryClient.query).not.toHaveBeenCalled();
    expect(screen.getByText(/Masked Accounts Payable Preview/)).toBeInTheDocument();
  });

  it('aborts active detail requests on unmount', async () => {
    const pending = deferred<typeof RECEIPT_RESPONSE.data>();
    vi.mocked(clientReceiptQueryClient.query).mockReturnValueOnce(pending.promise);
    render(<FinancePage />);
    await waitFor(() => expect(clientReceiptQueryClient.query).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(clientReceiptQueryClient.query).mock.calls[0]?.[1]?.signal;

    cleanup();
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      pending.resolve(RECEIPT_RESPONSE.data);
      await Promise.resolve();
    });
    expect(screen.queryByText('OBL-C-1')).not.toBeInTheDocument();
  });

  it('keeps the newly selected case when an aborted detail request rejects late', async () => {
    vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValueOnce({
      ...ORDER_PAGE,
      items: [
        ORDER_PAGE.items[0],
        { ...ORDER_PAGE.items[0], case_no: 'CASE-FIN-002', client_name: '去敏客戶乙' },
      ],
    });
    const pending = deferred<typeof RECEIPT_RESPONSE.data>();
    vi.mocked(clientReceiptQueryClient.query)
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValueOnce({
        ...RECEIPT_RESPONSE.data,
        case_no: 'CASE-FIN-002',
        obligations: [{ ...RECEIPT_RESPONSE.data.obligations[0], obligation_identity: 'OBL-C-2' }],
      });
    render(<FinancePage />);
    await waitFor(() => expect(clientReceiptQueryClient.query).toHaveBeenCalledTimes(1));
    const firstSignal = vi.mocked(clientReceiptQueryClient.query).mock.calls[0]?.[1]?.signal;

    fireEvent.change(screen.getByRole('combobox', { name: '案件' }), { target: { value: 'CASE-FIN-002' } });
    await waitFor(() => expect(screen.getByText('OBL-C-2')).toBeInTheDocument());
    expect(firstSignal?.aborted).toBe(true);

    await act(async () => {
      pending.reject(new Error('stale detail failure'));
      await Promise.resolve();
    });

    expect(screen.getByText('OBL-C-2')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
