vi.mock('../api/client_finance/difference_resolution_client',()=>({differenceResolutionClient:{client:vi.fn(async(case_no:string)=>({case_no,version:0,items:[],events:[]})),payroll:vi.fn(async(case_no:string)=>({case_no,version:0,items:[],events:[]})),staff:vi.fn(async(case_no:string)=>({case_no,items:[],events:[]}))}}));
/**
 * File: finance_request_lifecycle.test.tsx
 * Description: 驗證帳務查詢在 StrictMode 與工作區切換時取消過期請求。
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { financeImportQueryClient } from '../api/finance_import/finance_import_query_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { FinancePage } from '../pages/FinancePage';
import { financeAccountingClient, type CaseAccounting } from '../api/finance_import/finance_accounting_client';
import { monthlyAccountingClient, type MonthlyAccountingReport } from '../api/finance_import/monthly_accounting_client';
import { CORE_STAGE_CODES } from '../api/orders/order_core_stage_projection_schemas';
import { orderCoreStageProjectionClient } from '../api/orders/order_core_stage_projection_client';
import { realisticOrderDetail } from './fixtures/orders_real_data_fixtures';

const emptyTimelines = {
  items: [],
  stage_counts: Object.fromEntries(CORE_STAGE_CODES.map(code => [code, 0])) as Awaited<ReturnType<typeof orderCoreStageProjectionClient.getCoreStageTimelines>>["stage_counts"],
  substatus_counts: {},
  historical_lifecycle_counts: { unserved: 0, in_service: 0, service_completed: 0, accounting_completed: 0 },
  next_cursor: null,
  etag: 'c'.repeat(64),
} satisfies Awaited<ReturnType<typeof orderCoreStageProjectionClient.getCoreStageTimelines>>;

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
    window.history.replaceState(null, '', '#finance?tab=case-accounting&case_no=CASE-FIN-001');
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue(ORDER_PAGE);
    vi.spyOn(orderCoreStageProjectionClient, 'getCoreStageTimelines').mockResolvedValue(emptyTimelines);
    vi.spyOn(financeAccountingClient, 'query').mockImplementation(async caseNo => caseAccounting(caseNo));
    vi.spyOn(monthlyAccountingClient, 'query').mockResolvedValue(monthly);
    vi.spyOn(financeImportQueryClient, 'listBankTransactions').mockResolvedValue({ items: [], pending_count: 0, next_before_row_id: null });
  });
  afterEach(() => {
    cleanup();
    window.location.hash = '';
    vi.restoreAllMocks();
  });

  it('opens the exact workbench case and provides a return link to that case', async () => {
    window.history.replaceState(null, '', '#finance?tab=client-receipts&case_no=CASE-FIN-001&from=workbench');
    render(<FinancePage />);
    expect(await screen.findByRole('heading', { name: /CASE-FIN-001/ })).toBeVisible();
    expect(screen.getByRole('link', { name: '← 返回案件處理' })).toHaveAttribute('href', '#order-workbench-v2?case=CASE-FIN-001');
    expect(financeAccountingClient.query).toHaveBeenCalledWith('CASE-FIN-001', expect.any(AbortSignal));
  });

  it('keeps the historical case in the shared accounting drawer without an independent history card', async () => {
    vi.spyOn(ordersQueryClient, 'getOrderDetail').mockResolvedValue({
      ...realisticOrderDetail,
      case_no: 'CASE-FIN-001',
      order_status: '歷史訂單－服務完成',
    });
    render(<FinancePage />);
    await waitFor(() => expect(financeAccountingClient.query).toHaveBeenCalledWith('CASE-FIN-001', expect.any(AbortSignal)));
    expect(await screen.findByRole('region', { name: /各期繳款與通知/ })).toBeVisible();
    expect(screen.queryByText('歷史收付款與既有查證工具')).not.toBeInTheDocument();
  });

  it('cancels the discarded initial generation under StrictMode', async () => {
    window.history.replaceState(null, '', '#finance');
    render(<StrictMode><FinancePage /></StrictMode>);
    expect(await screen.findByText('目前沒有符合條件的進行中案件。')).toBeVisible();
    const signals = vi.mocked(ordersQueryClient.getOrderSummaries).mock.calls.map(([, options]) => options?.signal);
    expect(signals).toHaveLength(2);
    expect(signals.map(signal => signal?.aborted)).toEqual([true, false]);
    expect(financeAccountingClient.query).not.toHaveBeenCalled();
  });

  it('aborts an inactive monthly request and ignores its late result', async () => {
    window.history.replaceState(null, '', '#finance?tab=monthly');
    const pending = deferred<MonthlyAccountingReport>();
    vi.mocked(monthlyAccountingClient.query).mockReturnValue(pending.promise);
    render(<FinancePage />);
    await waitFor(() => expect(monthlyAccountingClient.query).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(monthlyAccountingClient.query).mock.calls[0]?.[1];
    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    expect(signal?.aborted).toBe(true);
    await act(async () => { pending.resolve(monthly); });
    expect(await screen.findByText('目前沒有符合條件的銀行交易資料。')).toBeVisible();
    expect(screen.queryByRole('tab', { name: '已核銷收付款' })).not.toBeInTheDocument();
  });

  it('aborts active case detail requests on unmount', async () => {
    const pending = deferred<CaseAccounting>();
    vi.mocked(financeAccountingClient.query).mockReturnValueOnce(pending.promise);
    render(<FinancePage />);
    await waitFor(() => expect(financeAccountingClient.query).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(financeAccountingClient.query).mock.calls[0]?.[1];
    cleanup();
    expect(signal?.aborted).toBe(true);
    await act(async () => { pending.resolve(caseAccounting('CASE-FIN-001')); });
    expect(screen.queryByRole('heading', { name: /CASE-FIN-001/ })).not.toBeInTheDocument();
  });

  it('keeps the newly selected case when an aborted detail request rejects late', async () => {
    const pending = deferred<CaseAccounting>();
    vi.mocked(financeAccountingClient.query).mockReturnValueOnce(pending.promise);
    render(<FinancePage />);
    await waitFor(() => expect(financeAccountingClient.query).toHaveBeenCalledTimes(1));
    const firstSignal = vi.mocked(financeAccountingClient.query).mock.calls[0]?.[1];
    act(() => {
      window.history.replaceState(null, '', '#finance?tab=case-accounting&case_no=CASE-FIN-002');
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });
    await screen.findByRole('heading', { name: /CASE-FIN-002/ });
    expect(firstSignal?.aborted).toBe(true);
    await act(async () => { pending.reject(new Error('stale detail failure')); });
    expect(screen.getByRole('heading', { name: /CASE-FIN-002/ })).toBeVisible();
    expect(screen.queryByText(/帳務資料暫時無法取得/)).not.toBeInTheDocument();
  });
});
