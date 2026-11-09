import {ClientReceiptReconciliationPanel} from '../../../../../../../components/ClientReceiptReconciliationPanel';
import {AccountingDifferencePanel} from '../../../../../../../components/AccountingDifferencePanel';
import {paymentOverdueReminderClient} from '../../../../../../../api/line_order_groups/payment_overdue_reminder_client';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FinanceCaseAccounting, FinanceAccountingWarnings, AccountingWarningList } from '../../../../../../../components/FinanceCaseAccounting';
import { loadAllCoreStageTimelines } from '../../../../../../../api/orders/load_all_core_stage_timelines';
import { FinanceCaseList } from '../../../../../../../components/FinanceCaseList';
import { FinanceGovernmentSubsidyList } from '../../../../../../../components/FinanceGovernmentSubsidyList';
import { weeklyOperationsReportQueryClient } from '../../../../../../../api/reports/weekly_operations_report_query_client';
import { WEEKLY_OPERATIONS_REPORT } from '../../../../../../fixtures/reports/weekly_operations_report_contract_fixtures';
import { FinanceStatementArchive } from '../../../../../../../components/FinanceStatementArchive';
import { financeAccountingClient, type CaseAccounting } from '../../../../../../../api/finance_import/finance_accounting_client';
import { ordersQueryClient } from '../../../../../../../api/orders/order_query_client';
import { clientReceiptQueryClient } from '../../../../../../../api/client_finance/client_receipt_query_client';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
import { differenceResolutionClient, type ClientDifferenceView } from '../../../../../../../api/client_finance/difference_resolution_client';
import { clientReceiptReconciliationClient, type ReceiptPreview } from '../../../../../../../api/client_finance/client_receipt_reconciliation_client';
vi.mock('../../../../../../../api/line_order_groups/payment_overdue_reminder_client',()=>({paymentOverdueReminderClient:{case:vi.fn(async()=>[]),sendCase:vi.fn()}}));
vi.mock('../../../../../../../api/orders/load_all_core_stage_timelines',()=>({loadAllCoreStageTimelines:vi.fn()}));
vi.mock('../../../../../../../api/reports/subsidy_report_query_client',()=>({subsidyReportQueryClient:{query:vi.fn()}}));
vi.mock('../../../../../../../api/client_finance/client_receipt_reconciliation_client',()=>({clientReceiptReconciliationClient:{preview:vi.fn(),apply:vi.fn()}}));
vi.mock('../../../../../../../api/client_finance/difference_resolution_client',()=>({differenceResolutionClient:{client:vi.fn(async(case_no:string)=>({case_no,version:0,items:[],events:[]})),payroll:vi.fn(async(case_no:string)=>({case_no,version:0,items:[],events:[]})),staff:vi.fn(async(case_no:string)=>({case_no,items:[],events:[]}))}}));
vi.mock('../../../../../../../api/client_finance/client_receipt_query_client',()=>({clientReceiptQueryClient:{query:vi.fn()}}));
vi.mock('../../../../../../../api/orders/order_query_client', async importOriginal => ({ ...await importOriginal<typeof import('../../../../../../../api/orders/order_query_client')>(), ordersQueryClient: { getOrderSummaries: vi.fn(), getOrderDetail: vi.fn().mockResolvedValue({case_no:'115000701',actual_start_date:'2026-10-01',actual_end_date:'2026-10-31'}) } }));

vi.mock('../../../../../../../api/finance_import/finance_accounting_client', async importOriginal => ({ ...await importOriginal<typeof import('../../../../../../../api/finance_import/finance_accounting_client')>(), financeAccountingClient: { arrangement:vi.fn(),confirmArrangement:vi.fn(),query: vi.fn(), warnings: vi.fn(), dismiss: vi.fn(), duplicate: vi.fn(), download: vi.fn(), downloadLegacyReferences: vi.fn() } }));

function detail(caseNo = '115000701'): CaseAccounting {
  return { case_no: caseNo, client_name: '測試客戶', receivable_ntd: 10000, received_ntd: 10030, payable_ntd: 10000, paid_ntd: 9970, pending_warning_count: 1,
    client_items: [{ identity: 'client-deposit', direction: 'receivable', label: '訂金', party: '測試客戶', expected_ntd: 10000, actual_ntd: 10030, has_payment: true, version: '1:0:0', due_date: '2026-10-29' }],
    staff_items: [{ identity: 'staff-pay', direction: 'payable', label: '月嫂付款', party: '測試月嫂', expected_ntd: 10000, actual_ntd: 9970, has_payment: true, version: '1:1:1:0', due_date: '2026-10-29' }],
    transactions: [{ identity: 'transaction-1', item_identity: 'staff-pay', occurred_on: '2026-10-29', kind: 'payout', amount_ntd: 9970, bank: 'sinopac' }],
    warnings: [{ item_identity: 'client-deposit', kind: 'over_received', expected_ntd: 10000, actual_ntd: 10030, difference_ntd: -30, source_version: '1:0:0', dismissed: false, dismissed_by: null, dismissed_at: null }],
  };
}
const ongoingTestCases=new Set<string>();
function orderPage(cases: string[], client_name = '測試客戶', next_cursor: string | null = null): Awaited<ReturnType<typeof ordersQueryClient.getOrderSummaries>> {
  cases.forEach(caseNo=>ongoingTestCases.add(caseNo));
  return { items: cases.map(case_no => ({ case_no, client_name, order_status: '訂單完成', staff_name: null, identity_status: null,
    start_date: null, end_date: null, actual_start_date: null, actual_end_date: null, service_days: null, total_employer_self_pay_payable: null })), next_cursor, etag: 'a'.repeat(64) };
}
beforeEach(() => { vi.clearAllMocks(); vi.mocked(paymentOverdueReminderClient.case).mockResolvedValue([]); ongoingTestCases.clear(); vi.mocked(loadAllCoreStageTimelines).mockImplementation(async()=>({items:[...ongoingTestCases].map(case_no=>({case_no,current_core_stage_ordinal:8,historical_current_owner_stage_ordinal:null,core_stages:[]})),next_cursor:null} as unknown as Awaited<ReturnType<typeof loadAllCoreStageTimelines>>)); vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue(orderPage([])); vi.mocked(clientReceiptQueryClient.query).mockResolvedValue({case_no:'115000701',account_version:0,bank_facts:[],obligations:[]}); });
describe('案件帳務及成功明細', () => {
  it('refreshes original difference facts after reconciliation in the owning tools', async () => {
    let received = 0;
    vi.mocked(financeAccountingClient.query).mockImplementation(async () => ({
      ...detail(), receivable_ntd:16000,received_ntd:received,payable_ntd:null,paid_ntd:null,pending_warning_count:0,
      client_items:[{identity:'deposit',direction:'receivable',label:'訂金',party:'Synthetic',expected_ntd:16000,actual_ntd:received,has_payment:received>0,version:String(received),due_date:'2026-11-01'}],
      staff_items:[],transactions:[],warnings:[],
    }));
    vi.mocked(differenceResolutionClient.client).mockImplementation(async case_no => ({
      case_no,version:received?1:0,items:[{identity:'deposit',label:'訂金',kind:'deposit',direction:'receivable_from_client',expected_ntd:16000,actual_ntd:received,remaining_ntd:16000-received,noncash_ntd:0,mode:'automatic',computed_ntd:16000,effective_ntd:16000,status:'待處理',options:['loss']}],events:[],
    } satisfies ClientDifferenceView));
    vi.mocked(clientReceiptQueryClient.query).mockImplementation(async () => ({
      case_no:'115000701',account_version:received?1:0,
      bank_facts:received?[]:[{finance_import_row_id:7,amount_ntd:6000,transaction_date:'2026-11-03',dedup_fingerprint:'a'.repeat(64)}],
      obligations:[{obligation_identity:'deposit',payment_stage:'deposit',amount_due_ntd:16000-received,due_date:'2026-11-01'}],
    }));
    const preview: ReceiptPreview = {account_version:0,preview_fingerprint:'b'.repeat(64),candidate:{status:'review_required',payment_stage:null,bank_total:{amount:6000},obligation_total:{amount:16000},overage_amount:{amount:0},allocations:[],blockers:['client_receipt_underpaid'],settlement_identity:'c'.repeat(64)}};
    vi.mocked(clientReceiptReconciliationClient.preview).mockResolvedValueOnce(preview).mockResolvedValueOnce({...preview,candidate:{...preview.candidate,status:'partial',blockers:[]}});
    vi.mocked(clientReceiptReconciliationClient.apply).mockImplementation(async () => {
      received=6000;
      return {case_no:'115000701',account_version:1,status:'partial',settlement_identity:'c'.repeat(64),ledger_entry_count:1,allocation_count:1,blockers:[]};
    });
    const {unmount}=render(<ClientReceiptReconciliationPanel caseNo="115000701" refreshVersion={0} onChanged={vi.fn()}/>);
    fireEvent.click(await screen.findByRole('button',{name:'核對本案入款'}));
    fireEvent.change(await screen.findByRole('combobox',{name:'選擇差額處理'}),{target:{value:'partial'}});
    fireEvent.click(await screen.findByRole('button',{name:'確認核銷本次收款'}));
    await screen.findByText('已記錄實際收款，剩餘款項繼續待收。');
    unmount();render(<AccountingDifferencePanel caseNo="115000701" refreshVersion={1} onChanged={vi.fn()}/>);
    const panel=await screen.findByRole('region',{name:'差額處理與人工金額更正'});
    await waitFor(()=>{
      const row=within(panel).getByRole('row',{name:/訂金/});
      expect(row.children[2]).toHaveTextContent('NT$ 6,000');
      expect(row.children[4]).toHaveTextContent('NT$ 10,000');
    });
  });
  it.each([
    [404, '找不到此案件，請確認案件編號。'],
    [401, '登入已失效，請重新登入後查詢。'],
    [403, '目前沒有查閱帳務的權限。'],
    [503, '帳務資料暫時無法取得，請稍後重新查詢。'],
  ])('distinguishes case lookup failure status %s', async (status, message) => {
    vi.mocked(financeAccountingClient.query).mockRejectedValue(new ApiHttpError(Number(status), 'query_failed', 'synthetic'));
    render(<FinanceCaseAccounting initialCase="115000701" />);
    expect(await screen.findByRole('alert')).toHaveTextContent(String(message));
  });
  it('preserves warning dismissal and server history in its owning tool',async()=>{const dismissed=detail();dismissed.pending_warning_count=0;dismissed.warnings[0]={...dismissed.warnings[0],dismissed:true,dismissed_by:'operator',dismissed_at:'2026-10-29'};vi.mocked(financeAccountingClient.dismiss).mockResolvedValue(dismissed);const onChange=vi.fn();const {rerender}=render(<AccountingWarningList data={detail()} onChange={onChange}/>);fireEvent.click(screen.getByRole('button',{name:'解除警示'}));await waitFor(()=>expect(onChange).toHaveBeenCalledWith(dismissed));rerender(<AccountingWarningList data={dismissed} onChange={onChange}/>);expect(screen.getByText('帳務警示 · 待檢查 0')).toBeInTheDocument();fireEvent.click(screen.getByRole('checkbox',{name:'顯示已解除'}));expect(screen.getByText(/已解除 · operator/)).toBeInTheDocument();});
  it('keeps the warning visible after failed dismissal',async()=>{vi.mocked(financeAccountingClient.dismiss).mockRejectedValue(Error('conflict'));render(<AccountingWarningList data={detail()} onChange={vi.fn()}/>);fireEvent.click(screen.getByRole('button',{name:'解除警示'}));expect(await screen.findByRole('alert')).toHaveTextContent('解除失敗');expect(screen.getByText('帳務警示 · 待檢查 1')).toBeInTheDocument();});
  it('ignores delayed old case response after source selection changes',async()=>{let finish:(value:CaseAccounting)=>void=()=>{};vi.mocked(financeAccountingClient.query).mockImplementation(caseNo=>caseNo==='115000701'?new Promise(resolve=>{finish=resolve;}):Promise.resolve(detail(caseNo)));const {rerender}=render(<FinanceCaseAccounting initialCase="115000701"/>);rerender(<FinanceCaseAccounting initialCase="115000702"/>);await screen.findByRole('heading',{name:'115000702 · 測試客戶'});finish(detail());await waitFor(()=>expect(screen.queryByRole('heading',{name:'115000701 · 測試客戶'})).not.toBeInTheDocument());});
  it.each([false,true])('offers only separate readonly exports (compact: %s)',async compact=>{
    const create=vi.spyOn(URL,'createObjectURL').mockReturnValue('blob:synthetic');
    const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
    vi.mocked(financeAccountingClient.download).mockResolvedValue(new Blob(['formal']));
    vi.mocked(financeAccountingClient.downloadLegacyReferences).mockResolvedValue(new Blob(['reference']));
    render(<FinanceStatementArchive compact={compact}/>);
    expect(screen.queryByRole('button',{name:'新增人工明細'})).not.toBeInTheDocument();
    expect(screen.queryByRole('form')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:'匯出 Excel'}));
    expect(await screen.findByRole('status')).toHaveTextContent('成功明細已匯出');
    expect(financeAccountingClient.download).toHaveBeenCalledOnce();
    expect(financeAccountingClient.downloadLegacyReferences).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'匯出歷史備查'}));
    expect(await screen.findByRole('status')).toHaveTextContent('不代表已核銷');
    expect(financeAccountingClient.downloadLegacyReferences).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledTimes(2);create.mockRestore();click.mockRestore();
  });

  it('reports reference-export failure without claiming success',async()=>{
    vi.mocked(financeAccountingClient.downloadLegacyReferences).mockRejectedValue(new Error('unavailable'));
    render(<FinanceStatementArchive/>);
    fireEvent.click(screen.getByRole('button',{name:'匯出歷史備查'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('匯出失敗');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('keeps same-name cases distinct until explicit selection',async()=>{vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue(orderPage(['115000701','115000702'],'同名客戶'));vi.mocked(financeAccountingClient.query).mockImplementation(async caseNo=>detail(caseNo));const onCase=vi.fn();render(<FinanceCaseList onCase={onCase}/>);await screen.findByRole('button',{name:'115000702'});expect(onCase).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'115000702'}));expect(onCase).toHaveBeenCalledWith('115000702');});
  it('lists explicitly selectable non-citizen cases',async()=>{vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue(orderPage(['115000701','A115001']));vi.mocked(financeAccountingClient.query).mockImplementation(async caseNo=>detail(caseNo));const onCase=vi.fn();render(<FinanceCaseList onCase={onCase}/>);await screen.findByRole('button',{name:'A115001'});expect(onCase).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'A115001'}));expect(onCase).toHaveBeenCalledWith('A115001');});
  it('continues source pages and filters partial case numbers without auto-selection',async()=>{vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValueOnce(orderPage(['115000701'],'測試客戶','115000701')).mockResolvedValueOnce(orderPage(['A115001'])).mockResolvedValueOnce(orderPage(['115000702','115000703'],'同名客戶'));vi.mocked(financeAccountingClient.query).mockImplementation(async caseNo=>detail(caseNo));const onCase=vi.fn();render(<FinanceCaseList onCase={onCase}/>);await screen.findByRole('button',{name:'A115001'});expect(ordersQueryClient.getOrderSummaries).toHaveBeenNthCalledWith(2,expect.objectContaining({after_case_no:'115000701',page_size:100}),expect.any(Object));fireEvent.change(screen.getByPlaceholderText('案件編號、客戶或月嫂'),{target:{value:'1150007'}});fireEvent.click(screen.getByRole('button',{name:'查詢案件'}));await screen.findByRole('button',{name:'115000703'});expect(screen.queryByRole('button',{name:'A115001'})).not.toBeInTheDocument();expect(onCase).not.toHaveBeenCalled();});
  it('opens an explicit case independently of a failed list query',async()=>{vi.mocked(ordersQueryClient.getOrderSummaries).mockRejectedValue(Error('unavailable'));vi.mocked(financeAccountingClient.query).mockResolvedValue(detail('A115001'));render(<FinanceCaseAccounting initialCase="A115001"/>);expect(await screen.findByRole('heading',{name:'A115001 · 測試客戶'})).toBeInTheDocument();expect(financeAccountingClient.query).toHaveBeenCalledWith('A115001',expect.any(AbortSignal));});
  it('provides shared warnings and a case entry', async () => {
    vi.mocked(financeAccountingClient.warnings).mockResolvedValue([detail()]);
    const onCase = vi.fn(); render(<FinanceAccountingWarnings onCase={onCase} />);
    fireEvent.click(await screen.findByRole('button', { name: /查看案件/ }));
    expect(onCase).toHaveBeenCalledWith('115000701');
  });

  it('reloads the shared deduplicated list after dismissal instead of inserting a full case twice', async () => {
    const first = detail(); const second = detail('115000702');
    second.warnings[0] = { ...second.warnings[0], item_identity: 'other-source' };
    const refreshed = { ...second, pending_warning_count: 0, warnings: [{ ...second.warnings[0], dismissed: true, dismissed_by: 'operator' }] };
    vi.mocked(financeAccountingClient.warnings).mockResolvedValueOnce([first, second]).mockResolvedValue([first, refreshed]);
    vi.mocked(financeAccountingClient.dismiss).mockResolvedValue({ ...refreshed, warnings: [first.warnings[0], ...refreshed.warnings] });
    render(<FinanceAccountingWarnings onCase={vi.fn()} />);
    await screen.findByRole('button', { name: /115000702.*查看案件/ });
    fireEvent.click(screen.getAllByRole('button', { name: '解除警示' })[1]);
    await waitFor(() => expect(financeAccountingClient.warnings).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('帳務警示 · 待檢查 0')).toBeInTheDocument();
    expect(screen.getAllByText('客戶超收')).toHaveLength(1);
  });
});


describe('正式案件與政府清單',()=>{
 it('allows the same query to retry after a failure without changing the search',async()=>{
  vi.mocked(ordersQueryClient.getOrderSummaries).mockRejectedValueOnce(new Error('unavailable')).mockResolvedValue(orderPage(['115000701']));
  vi.mocked(financeAccountingClient.query).mockResolvedValue(detail());
  render(<FinanceCaseList onCase={vi.fn()}/>);
  await screen.findByRole('alert');
  fireEvent.click(screen.getByRole('button',{name:'查詢案件'}));
  expect(await screen.findByRole('button',{name:'115000701'})).toBeInTheDocument();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
 });
 it('keeps missing dates, source failure and zero-net pending cases visible without asserting completion',async()=>{
  const page=orderPage(['115000701','115000702']);page.items[0].actual_start_date='2026-10-01';
  vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue(page);
  vi.mocked(financeAccountingClient.query).mockImplementation(async caseNo=>{
   if(caseNo==='115000702')throw Error('unavailable');
   return {...detail(caseNo),scheme:'unknown',cash_net_ntd:0,customer_fully_received:true,remaining_in_ntd:0,remaining_out_ntd:0,cash_by_flow:{C:10000,G:0,PS:10000,PT:0,RS:0,RT:0}};
  });
  const onCase=vi.fn();render(<FinanceCaseList onCase={onCase}/>);
  await screen.findByRole('button',{name:'115000701'});
  const row=screen.getByRole('row',{name:/115000701/});
  expect(row).toHaveTextContent('開始 2026-10-01');expect(row).toHaveTextContent('結束 待確認');expect(row).toHaveTextContent('帳務來源待確認');
  expect(screen.getByRole('row',{name:/115000702/})).toHaveTextContent('帳務來源待確認');
  expect(within(row).getByRole('button',{name:'發出提醒'})).toBeDisabled();
  fireEvent.click(within(row).getByRole('button',{name:'查看案件'}));expect(onCase).toHaveBeenCalledWith('115000701');
  expect(screen.getByRole('row',{name:/115000702/})).toBeInTheDocument();
 });
 it('uses the existing subsidy reports and opens the original drawer without querying case schemes',async()=>{
  vi.spyOn(weeklyOperationsReportQueryClient,'query').mockResolvedValue(WEEKLY_OPERATIONS_REPORT);
  const open=vi.fn();render(<FinanceGovernmentSubsidyList onCase={open}/>);
  await screen.findByRole('table',{name:'一般市民補助案件統計明細'});
  expect(screen.getByLabelText('報表範圍')).toHaveValue('weekly');
  expect(screen.queryByRole('button',{name:'匯出內部核對 CSV'})).not.toBeInTheDocument();
  expect(financeAccountingClient.query).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'開啟案件 CASE-RPT-001'}));
  expect(open).toHaveBeenCalledWith('CASE-RPT-001');
  expect(screen.getByRole('button',{name:'下載營運報表 XLSX'})).toBeEnabled();
 });
});


it('filters the complete ongoing scope with six columns and displays all ongoing cases without page limits',async()=>{
 const cases=Array.from({length:21},(_,i)=>'115'+String(i+1).padStart(6,'0'));
 vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValueOnce(orderPage(cases.slice(0,20),'Synthetic',cases[19])).mockResolvedValueOnce(orderPage(cases.slice(20)));
 vi.mocked(financeAccountingClient.query).mockImplementation(async caseNo=>({...detail(caseNo),collection_progress:{stage:caseNo===cases[20]?'scheme':'deposit',sources_complete:true,expected_ntd:6000,received_ntd:0,remaining_ntd:6000,due_date:'2099-11-05'}}));
 render(<FinanceCaseList onCase={vi.fn()}/>);
 await screen.findByText(/搜尋範圍共 21 案/);
 expect(screen.getAllByRole('columnheader').map(cell=>cell.textContent)).toEqual(['案件／客戶','實際開始／結束日','相關月嫂','案件總額 T','應操作／目前狀態','操作']);
 expect(screen.getByRole('button',{name:cases[20]})).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('目前階段'),{target:{value:'scheme'}});
 expect(screen.getByRole('button',{name:cases[20]})).toBeInTheDocument();
 expect(screen.getByText(/搜尋範圍共 1 案/)).toBeInTheDocument();
 const actions=within(screen.getByRole('row',{name:new RegExp(cases[20])})).getAllByRole('button');
 expect(actions.slice(-2).map(button=>button.textContent)).toEqual(['查看案件','發出提醒']);
 fireEvent.change(screen.getByLabelText('目前階段'),{target:{value:'all'}});
 fireEvent.change(screen.getByLabelText('時效篩選'),{target:{value:'future'}});
 expect(screen.getByText(/搜尋範圍共 20 案/)).toBeInTheDocument();
});





it('uses the canonical step8 projection without treating service dates as entry evidence',async()=>{
 vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue(orderPage(['115000701','115000702']));
 vi.mocked(loadAllCoreStageTimelines).mockResolvedValue({items:[{case_no:'115000701',current_core_stage_ordinal:7,historical_current_owner_stage_ordinal:null,core_stages:[]},{case_no:'115000702',current_core_stage_ordinal:8,historical_current_owner_stage_ordinal:null,core_stages:[]}],next_cursor:null} as unknown as Awaited<ReturnType<typeof loadAllCoreStageTimelines>>);
 vi.mocked(financeAccountingClient.query).mockResolvedValue({...detail('115000702'),collection_progress:{stage:'deposit',sources_complete:true,expected_ntd:6000,received_ntd:0,remaining_ntd:6000,due_date:'2099-11-05'}});
 render(<FinanceCaseList onCase={vi.fn()}/>);
 await screen.findByRole('button',{name:'115000702'});
 expect(screen.queryByRole('button',{name:'115000701'})).not.toBeInTheDocument();
 expect(financeAccountingClient.query).toHaveBeenCalledTimes(1);
 expect(screen.getByText('待收訂金')).toBeInTheDocument();
 expect(screen.getByText('未到期')).toBeInTheDocument();
});

it('switches between ongoing cases and all cases tabs in case accounting workspace', async () => {
 const page = orderPage(['115000701', '115000702']);
 vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue(page);
 vi.mocked(financeAccountingClient.query).mockImplementation(async (caseNo) => {
  if (caseNo === '115000702') {
   return {
    ...detail(caseNo),
    ongoing_completed: true,
    collection_progress: null,
   };
  }
  return {
   ...detail(caseNo),
   ongoing_completed: false,
   collection_progress: {
    stage: 'deposit',
    sources_complete: true,
    expected_ntd: 6000,
    received_ntd: 0,
    remaining_ntd: 6000,
    due_date: '2099-11-05',
   },
  };
 });
 render(<FinanceCaseList onCase={vi.fn()} />);

 expect(screen.getByRole('tab', { name: '進行中案件' })).toHaveClass('active');
 expect(screen.getByRole('tab', { name: '所有案件' })).not.toHaveClass('active');

 await screen.findByRole('button', { name: '115000701' });
 expect(screen.queryByRole('button', { name: '115000702' })).not.toBeInTheDocument();
 expect(screen.getByText(/已顯示全部進行中案件/)).toBeInTheDocument();

 fireEvent.click(screen.getByRole('tab', { name: '所有案件' }));
 expect(screen.getByRole('tab', { name: '所有案件' })).toHaveClass('active');
 expect(screen.getByRole('tab', { name: '進行中案件' })).not.toHaveClass('active');

 expect(screen.getByRole('button', { name: '115000701' })).toBeInTheDocument();
 expect(screen.getByRole('button', { name: '115000702' })).toBeInTheDocument();
 expect(screen.getByText('已結清')).toBeInTheDocument();
 expect(screen.getByText(/已顯示全部案件/)).toBeInTheDocument();

 fireEvent.click(screen.getByRole('tab', { name: '進行中案件' }));
 expect(screen.getByRole('button', { name: '115000701' })).toBeInTheDocument();
 expect(screen.queryByRole('button', { name: '115000702' })).not.toBeInTheDocument();
 expect(screen.getByText(/已顯示全部進行中案件/)).toBeInTheDocument();
});
