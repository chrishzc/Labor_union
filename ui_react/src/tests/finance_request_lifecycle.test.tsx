vi.mock('../api/client_finance/difference_resolution_client',()=>({differenceResolutionClient:{client:vi.fn(async(case_no:string)=>({case_no,version:0,items:[],events:[]})),payroll:vi.fn(async(case_no:string)=>({case_no,version:0,items:[],events:[]})),staff:vi.fn(async(case_no:string)=>({case_no,items:[],events:[]}))}}));
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
import { cashRequirementsQueryClient } from '../api/accounts_payable/cash_requirements_query_client';
import { clientFinanceHistoryClient } from '../api/client_finance/client_finance_history_client';
import { FinancePage } from '../pages/FinancePage';
import { historicalCompletionClient } from '../api/orders/historical_completion_client';
import { financeAccountingClient, type CaseAccounting } from '../api/finance_import/finance_accounting_client';
import { monthlyAccountingClient, type MonthlyAccountingReport } from '../api/finance_import/monthly_accounting_client';
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

function caseAccounting(caseNo:string):CaseAccounting{return {case_no:caseNo,client_name:'去敏客戶',receivable_ntd:5000,received_ntd:0,payable_ntd:8000,paid_ntd:0,remaining_in_ntd:5000,remaining_out_ntd:8000,pending_warning_count:0,warnings:[],transactions:[],staff_items:[{identity:'OBL-S-1',direction:'payable',label:'月嫂薪資',party:'去敏人員',expected_ntd:8000,actual_ntd:0,remaining_ntd:8000,has_payment:false,version:'3',due_date:null}],client_items:[{identity:caseNo.endsWith('002')?'OBL-C-2':'OBL-C-1',direction:'receivable',label:'訂金',party:'去敏客戶',expected_ntd:5000,actual_ntd:0,remaining_ntd:5000,has_payment:false,version:'2',due_date:'2026-08-01'}]};}
const monthly:MonthlyAccountingReport={start_month:'2026-08',end_month:'2026-08',category:'subsidy',as_of:'2026-08-31',rows:[],excluded_cases:[],undated_item_count:0};

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
    window.location.hash = '#finance?tab=client-receipts&case_no=CASE-FIN-001';
    vi.spyOn(clientFinanceHistoryClient, 'query').mockResolvedValue({ case_no: 'CASE-FIN-001', account_version: '0', obligations: [], ledger_entries: [] });
    vi.spyOn(cashRequirementsQueryClient, 'queryAll').mockResolvedValue([]);
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue(ORDER_PAGE);
    vi.spyOn(clientReceiptQueryClient, 'query').mockResolvedValue(RECEIPT_RESPONSE.data);
    vi.spyOn(financeAccountingClient,'query').mockImplementation(async caseNo=>caseAccounting(caseNo));
    vi.spyOn(monthlyAccountingClient,'query').mockResolvedValue(monthly);
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ items: [{ id: 11, name: '去敏人員', phone: null, education: null }], next_cursor: null });
    vi.spyOn(staffPayablesQueryClient, 'query').mockResolvedValue(STAFF_PAYABLES_RESPONSE.data);
    vi.spyOn(accountsPayableQueryClient, 'query').mockResolvedValue(ACCOUNTS_PAYABLE_RESPONSE.data);
    vi.spyOn(accountsPayableQueryClient, 'queryCase').mockResolvedValue({
      case_no: 'CASE-FIN-001',
      target_payment_date: '2026-09-15',
      items: [],
    });
    vi.spyOn(financeImportQueryClient, 'listBatches').mockResolvedValue(FINANCE_BATCH_RESPONSE.data);
    vi.spyOn(financeImportQueryClient, 'getManifest').mockResolvedValue(FINANCE_MANIFEST_RESPONSE.data);
    vi.spyOn(financeImportQueryClient, 'listReviewRows').mockResolvedValue({ batch_identity: 'BATCH-FIN-021', source_reviews: [], next_after_source_review_id: null, items: [], next_after_row_id: null });
    vi.spyOn(financeImportQueryClient, 'listReprocessRuns').mockResolvedValue({ items: [], next_before_run_id: null });
  });

  afterEach(() => {
    cleanup();
    window.location.hash = '';
    vi.restoreAllMocks();
  });

  it('opens the exact workbench case and provides a return link to that case', async () => {
    window.location.hash = '#finance?tab=client-receipts&case_no=CASE-FIN-001&from=workbench';
    render(<FinancePage />);
    await waitFor(() => expect(document.querySelector('[data-obligation-id="OBL-C-1"]')).toBeInTheDocument());
    expect(screen.getByRole('link', { name: '← 返回案件處理' })).toHaveAttribute('href', '#order-workbench-v2?case=CASE-FIN-001');
    expect(screen.getByRole('combobox', { name: '選擇案件' })).toHaveValue('CASE-FIN-001');
    expect(financeAccountingClient.query).toHaveBeenCalledWith('CASE-FIN-001', expect.any(AbortSignal));
  });

  it('hosts the existing historical accounting-completion workflow on the selected finance case', async () => {
    vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue({ ...ORDER_PAGE, items: [{ ...ORDER_PAGE.items[0], order_status: '歷史訂單－服務完成' }] });
    const query = vi.spyOn(historicalCompletionClient, 'query').mockRejectedValue(new Error('test owner unavailable'));
    render(<FinancePage />);
    fireEvent.click(await screen.findByText('歷史收付款與既有查證工具'));
    fireEvent.click(screen.getByRole('button',{name:'開啟本案既有帳務工具'}));
    await screen.findByRole('heading', { name: '歷史案件帳務完成' });
    await waitFor(() => expect(query).toHaveBeenCalledWith('CASE-FIN-001', expect.objectContaining({ signal: expect.any(AbortSignal) })));
    expect(await screen.findByRole('alert')).toHaveTextContent('歷史案件完成狀態目前無法載入。');
  });

  it('issues one initial query generation under StrictMode', async () => {
    render(<StrictMode><FinancePage /></StrictMode>);
    await waitFor(() => expect(document.querySelector('[data-obligation-id="OBL-C-1"]')).toBeInTheDocument());

    expect(ordersQueryClient.getOrderSummaries).toHaveBeenCalledTimes(1);
    expect(financeAccountingClient.query).toHaveBeenCalledTimes(1);
    expect(clientReceiptQueryClient.query).toHaveBeenCalledTimes(1);
  });

  it('aborts an inactive tab request and ignores its late result', async () => {
    window.location.hash = '#finance';
    vi.spyOn(clientFinanceHistoryClient, 'queryAll').mockResolvedValue([]);
    const pending = deferred<MonthlyAccountingReport>();
    vi.mocked(monthlyAccountingClient.query).mockReturnValueOnce(pending.promise);
    render(<StrictMode><FinancePage /></StrictMode>);
    await waitFor(() => expect(monthlyAccountingClient.query).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(monthlyAccountingClient.query).mock.calls[0]?.[1];

    fireEvent.click(screen.getByRole('button', { name: '應付款' }));
    await waitFor(() => expect(cashRequirementsQueryClient.queryAll).toHaveBeenCalledTimes(1));
    expect(signal?.aborted).toBe(true);

    await act(async () => {
      pending.resolve(monthly);
      await Promise.resolve();
    });

    expect(clientReceiptQueryClient.query).not.toHaveBeenCalled();
    expect(screen.getByRole('region', { name: '付款清單' })).toBeInTheDocument();
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
    expect(document.querySelector('[data-obligation-id="OBL-C-1"]')).not.toBeInTheDocument();
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

    fireEvent.change(screen.getByRole('combobox', { name: '選擇案件' }), { target: { value: 'CASE-FIN-002' } });
    await waitFor(() => expect(document.querySelector('[data-obligation-id="OBL-C-2"]')).toBeInTheDocument());
    expect(firstSignal?.aborted).toBe(true);

    await act(async () => {
      pending.reject(new Error('stale detail failure'));
      await Promise.resolve();
    });

    expect(document.querySelector('[data-obligation-id="OBL-C-2"]')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
