import {ClientReceiptReconciliationPanel} from '../../../../../../../components/ClientReceiptReconciliationPanel';
import {AccountingDifferencePanel} from '../../../../../../../components/AccountingDifferencePanel';
import {paymentOverdueReminderClient} from '../../../../../../../api/line_order_groups/payment_overdue_reminder_client';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FinanceCaseAccounting, FinanceAccountingWarnings, AccountingWarningList } from '../../../../../../../components/FinanceCaseAccounting';
import { UnsavedChangesProvider } from '../../../../../../../components/UnsavedChanges';
import { FinanceCaseArrangementPanel } from '../../../../../../../components/FinanceCaseArrangementPanel';
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

vi.mock('../../../../../../../api/finance_import/finance_accounting_client', async importOriginal => ({ ...await importOriginal<typeof import('../../../../../../../api/finance_import/finance_accounting_client')>(), financeAccountingClient: { arrangement:vi.fn(),confirmArrangement:vi.fn(),query: vi.fn(), warnings: vi.fn(), dismiss: vi.fn(), manual: vi.fn(), duplicate: vi.fn(), download: vi.fn() } }));

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
  it.each(['支出', '存入'] as const)('saves a minimal %s statement through the drawer and maps only the selected amount column', async direction => {
    vi.mocked(financeAccountingClient.manual).mockResolvedValue({ identity: 'manual:1', saved_count: 1, excluded_count: 0 });
    render(<FinanceStatementArchive />);
    const trigger = screen.getByRole('button', { name: '新增人工明細' });
    trigger.focus(); fireEvent.click(trigger);
    expect(screen.getByRole('dialog', { name: '新增人工明細' })).toBeInTheDocument();
    expect(screen.getByLabelText('金額（必填）')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('交易方向（必填）'), { target: { value: direction === '存入' ? '支出' : '存入' } });
    fireEvent.change(screen.getByLabelText('金額（必填）'), { target: { value: '9970' } });
    fireEvent.change(screen.getByLabelText('交易方向（必填）'), { target: { value: direction } });
    fireEvent.change(screen.getByLabelText('交易日（必填）'), { target: { value: '2026-10-29' } });
    fireEvent.change(screen.getByLabelText('備註'), { target: { value: 'HC115001退款' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存明細' }));
    await waitFor(() => expect(financeAccountingClient.manual).toHaveBeenCalledWith({ 交易日: '2026-10-29', [direction]: '9970', 備註: 'HC115001退款' }, expect.any(String)));
    expect(await screen.findByRole('status')).toHaveTextContent('人工明細已保存');
    expect(screen.queryByRole('dialog', { name: '新增人工明細' })).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(screen.queryByLabelText('案件編號')).not.toBeInTheDocument();
    expect(screen.queryByText('處理已確認的重複明細')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/明細識別/)).not.toBeInTheDocument();
    expect(financeAccountingClient.duplicate).not.toHaveBeenCalled();
  });

  it('shows field errors before saving and preserves optional original values', async () => {
    vi.mocked(financeAccountingClient.manual).mockResolvedValue({ identity: 'manual:1', saved_count: 1, excluded_count: 0 });
    render(<FinanceStatementArchive />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '新增人工明細' }));
    fireEvent.click(screen.getByRole('button', { name: '儲存明細' }));
    expect(screen.getByText('請填寫交易日。')).toBeInTheDocument();
    expect(screen.getByText('請選擇存入或支出。')).toBeInTheDocument();
    expect(screen.getByText('銷帳編號或備註至少填寫一項。')).toBeInTheDocument();
    expect(financeAccountingClient.manual).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('交易日（必填）'), { target: { value: '2026-10-30' } });
    fireEvent.change(screen.getByLabelText('交易方向（必填）'), { target: { value: '存入' } });
    fireEvent.change(screen.getByLabelText('金額（必填）'), { target: { value: '12.5' } });
    fireEvent.change(screen.getByLabelText('銷帳編號'), { target: { value: '00123456' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存明細' }));
    expect(screen.getByText('請填寫大於 0 的整數金額。')).toBeInTheDocument();
    expect(financeAccountingClient.manual).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('金額（必填）'), { target: { value: '1250' } });
    fireEvent.click(screen.getByText('其他資料（選填）'));
    fireEvent.change(screen.getByLabelText('帳號'), { target: { value: '0000123456' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存明細' }));
    await waitFor(() => expect(financeAccountingClient.manual).toHaveBeenCalledWith({ 交易日: '2026-10-30', 存入: '1250', 銷帳編號: '00123456', 帳號: '0000123456' }, expect.any(String)));
    expect(await screen.findByRole('status')).toHaveTextContent('人工明細已保存');
  });

  it('keeps an uncertain save locked in the drawer and retries the same payload and key', async () => {
    vi.mocked(financeAccountingClient.manual).mockRejectedValueOnce(new Error('timeout')).mockResolvedValue({ identity: 'manual:1', saved_count: 1, excluded_count: 0 });
    render(<FinanceStatementArchive />);
    fireEvent.click(screen.getByRole('button', { name: '新增人工明細' }));
    fireEvent.change(screen.getByLabelText('交易日（必填）'), { target: { value: '2026-10-30' } });
    fireEvent.change(screen.getByLabelText('交易方向（必填）'), { target: { value: '支出' } });
    fireEvent.change(screen.getByLabelText('金額（必填）'), { target: { value: '1500' } });
    fireEvent.change(screen.getByLabelText('備註'), { target: { value: '合成測試明細' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存明細' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('儲存結果尚未確認');
    expect(screen.getByLabelText('金額（必填）')).toBeDisabled();
    expect(screen.getByLabelText('交易方向（必填）')).toBeDisabled();
    expect(screen.getByRole('button', { name: '取消' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '關閉人工新增明細' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '匯出 Excel' })).toBeDisabled();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.getByRole('dialog', { name: '新增人工明細' })).toBeInTheDocument();
    const original = vi.mocked(financeAccountingClient.manual).mock.calls[0];
    fireEvent.click(screen.getByRole('button', { name: '重新確認儲存結果' }));
    expect(await screen.findByRole('status')).toHaveTextContent('人工明細已保存');
    expect(vi.mocked(financeAccountingClient.manual).mock.calls[1]).toEqual(original);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('closes an empty drawer with Escape and asks before discarding an edited draft', async () => {
    render(<UnsavedChangesProvider><FinanceStatementArchive /></UnsavedChangesProvider>);
    const trigger = screen.getByRole('button', { name: '新增人工明細' });
    trigger.focus(); fireEvent.click(trigger);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: '新增人工明細' })).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());
    fireEvent.click(trigger);
    fireEvent.change(screen.getByLabelText('交易方向（必填）'), { target: { value: '存入' } });
    fireEvent.change(screen.getByLabelText('金額（必填）'), { target: { value: '2500' } });
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    const guard = await screen.findByRole('dialog', { name: '尚有未儲存的變更' });
    fireEvent.click(within(guard).getByRole('button', { name: '繼續編輯' }));
    expect(screen.getByLabelText('金額（必填）')).toHaveValue('2500');
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    fireEvent.click(screen.getByRole('button', { name: '捨棄變更並離開' }));
    expect(screen.queryByRole('dialog', { name: '新增人工明細' })).not.toBeInTheDocument();
    fireEvent.click(trigger);
    expect(screen.getByLabelText('交易方向（必填）')).toHaveValue('');
    expect(screen.getByLabelText('金額（必填）')).toHaveValue('');
    expect(financeAccountingClient.manual).not.toHaveBeenCalled();
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


it('filters the complete ongoing scope with six columns and twenty-row display pages',async()=>{
 const cases=Array.from({length:21},(_,i)=>'115'+String(i+1).padStart(6,'0'));
 vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValueOnce(orderPage(cases.slice(0,20),'Synthetic',cases[19])).mockResolvedValueOnce(orderPage(cases.slice(20)));
 vi.mocked(financeAccountingClient.query).mockImplementation(async caseNo=>({...detail(caseNo),collection_progress:{stage:caseNo===cases[20]?'scheme':'deposit',sources_complete:true,expected_ntd:6000,received_ntd:0,remaining_ntd:6000,due_date:'2099-11-05'}}));
 render(<FinanceCaseList onCase={vi.fn()}/>);
 await screen.findByText(/搜尋範圍共 21 案/);
 expect(screen.getAllByRole('columnheader').map(cell=>cell.textContent)).toEqual(['案件／客戶','實際開始／結束日','相關月嫂','案件總額 T','應操作／目前狀態','操作']);
 expect(screen.queryByRole('button',{name:cases[20]})).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'下一頁'}));expect(screen.getByRole('button',{name:cases[20]})).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('目前階段'),{target:{value:'scheme'}});
 expect(screen.getByRole('button',{name:cases[20]})).toBeInTheDocument();
 expect(screen.getByText(/搜尋範圍共 1 案/)).toBeInTheDocument();
 expect(screen.getByRole('button',{name:'上一頁'})).toBeDisabled();
 const actions=within(screen.getByRole('row',{name:new RegExp(cases[20])})).getAllByRole('button');
 expect(actions.slice(-2).map(button=>button.textContent)).toEqual(['查看案件','發出提醒']);
 fireEvent.change(screen.getByLabelText('目前階段'),{target:{value:'all'}});
 fireEvent.change(screen.getByLabelText('時效篩選'),{target:{value:'future'}});
 expect(screen.getByText(/搜尋範圍共 20 案/)).toBeInTheDocument();
});


describe('逐案直付安排保存',()=>{
 const event={version:1,action:'confirm_direct' as const,reason:'本案直接撥付依據',actor:'admin_user_id:9',created_at:'2026-11-04T12:00:00+00:00'};
 const data=()=>({...detail(),arrangement:{case_no:'115000701',version:0,events:[]},can_confirm_direct:true,scheme:'unknown' as const});
 function edit(){fireEvent.click(screen.getByText('確認／更正本案安排'));fireEvent.change(screen.getByLabelText('安排操作'),{target:{value:'confirm_direct'}});fireEvent.change(screen.getByLabelText('確認依據／更正原因'),{target:{value:'本案直接撥付依據'}});}
 it('saves confirmation and withdrawal with full server history, without requiring customer subsidy receipt proof',async()=>{
  const onChanged=vi.fn();
  vi.mocked(financeAccountingClient.confirmArrangement).mockResolvedValueOnce({case_no:'115000701',applied_version:1,arrangement:{case_no:'115000701',version:1,events:[event]}}).mockResolvedValueOnce({case_no:'115000701',applied_version:2,arrangement:{case_no:'115000701',version:2,events:[event,{...event,version:2,action:'withdraw_direct',reason:'更正為工會經手',actor:'admin_user_id:10'}]}});
  render(<UnsavedChangesProvider><FinanceCaseArrangementPanel data={data()} onChanged={onChanged}/></UnsavedChangesProvider>);edit();
  expect(screen.queryByLabelText(/客戶.*收款證明/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'儲存本案安排'}));
  await screen.findByText('政府直付安排已確認',{exact:false});expect(screen.getByText('admin_user_id:9')).toBeInTheDocument();
  expect(onChanged).toHaveBeenCalledTimes(1);expect(screen.getByText('2026/11/04 20:00:00')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('安排操作'),{target:{value:'withdraw_direct'}});fireEvent.change(screen.getByLabelText('確認依據／更正原因'),{target:{value:'更正為工會經手'}});fireEvent.click(screen.getByRole('button',{name:'儲存本案安排'}));
  await screen.findByText('政府直付安排已撤回',{exact:false});expect(screen.getByText('admin_user_id:9')).toBeInTheDocument();expect(screen.getByText('admin_user_id:10')).toBeInTheDocument();
  expect(financeAccountingClient.confirmArrangement).toHaveBeenLastCalledWith('115000701',{action:'withdraw_direct',reason:'更正為工會經手',expected_version:1},expect.any(String));
 });
 it('keeps an unknown outcome locked and confirms only the original command/key',async()=>{
  const onChanged=vi.fn();vi.mocked(financeAccountingClient.confirmArrangement).mockRejectedValueOnce(new ApiHttpError(503,'unknown','unknown')).mockResolvedValueOnce({case_no:'115000701',applied_version:1,arrangement:{case_no:'115000701',version:1,events:[event]}});
  render(<UnsavedChangesProvider><FinanceCaseArrangementPanel data={data()} onChanged={onChanged}/></UnsavedChangesProvider>);edit();fireEvent.click(screen.getByRole('button',{name:'儲存本案安排'}));
  const retry=await screen.findByRole('button',{name:'確認原操作結果'});expect(onChanged).not.toHaveBeenCalled();expect(screen.getByLabelText('確認依據／更正原因')).toBeDisabled();
  fireEvent.click(retry);await screen.findByText('政府直付安排已確認',{exact:false});
  expect(vi.mocked(financeAccountingClient.confirmArrangement).mock.calls[1]).toEqual(vi.mocked(financeAccountingClient.confirmArrangement).mock.calls[0]);expect(onChanged).toHaveBeenCalledTimes(1);
 });
 it('preserves edits on stale data and requires an explicit read before submitting a new version',async()=>{
  vi.mocked(financeAccountingClient.confirmArrangement).mockRejectedValueOnce(new ApiHttpError(409,'arrangement_source_changed','stale')).mockResolvedValueOnce({case_no:'115000701',applied_version:2,arrangement:{case_no:'115000701',version:2,events:[event,{...event,version:2}]}});
  vi.mocked(financeAccountingClient.arrangement).mockResolvedValue({case_no:'115000701',version:1,events:[event]});
  render(<FinanceCaseArrangementPanel data={data()} onChanged={vi.fn()}/>);edit();fireEvent.click(screen.getByRole('button',{name:'儲存本案安排'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('輸入已保留');expect(screen.getByLabelText('確認依據／更正原因')).toHaveValue('本案直接撥付依據');
  fireEvent.click(screen.getByRole('button',{name:'重新讀取安排'}));await screen.findByText(/已重新讀取安排/);
  fireEvent.click(screen.getByRole('button',{name:'儲存本案安排'}));await screen.findByText(/已保存安排版本 2/);
  const calls=vi.mocked(financeAccountingClient.confirmArrangement).mock.calls;
  expect(calls[1][1].expected_version).toBe(1);expect(calls[1][2]).not.toBe(calls[0][2]);
 });
 it('shows a later cash conflict while preserving the recorded arrangement evidence',()=>{
  render(<FinanceCaseArrangementPanel data={{...data(),arrangement:{case_no:'115000701',version:1,events:[event]},scheme_conflict:true,can_confirm_direct:false}} onChanged={vi.fn()}/>);
  expect(screen.getByRole('alert')).toHaveTextContent('方案待確認');expect(screen.getByText('admin_user_id:9')).toBeInTheDocument();
 });
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
