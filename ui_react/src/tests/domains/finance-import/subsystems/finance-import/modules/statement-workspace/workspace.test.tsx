import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FinanceCaseAccounting, FinanceAccountingWarnings } from '../../../../../../../components/FinanceCaseAccounting';
import { UnsavedChangesProvider } from '../../../../../../../components/UnsavedChanges';
import { FinanceStatementArchive } from '../../../../../../../components/FinanceStatementArchive';
import { financeAccountingClient, type CaseAccounting } from '../../../../../../../api/finance_import/finance_accounting_client';
import { ordersQueryClient } from '../../../../../../../api/orders/order_query_client';
import { clientReceiptQueryClient } from '../../../../../../../api/client_finance/client_receipt_query_client';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
import { differenceResolutionClient, type ClientDifferenceView } from '../../../../../../../api/client_finance/difference_resolution_client';
import { clientReceiptReconciliationClient, type ReceiptPreview } from '../../../../../../../api/client_finance/client_receipt_reconciliation_client';
vi.mock('../../../../../../../api/client_finance/client_receipt_reconciliation_client',()=>({clientReceiptReconciliationClient:{preview:vi.fn(),apply:vi.fn()}}));
vi.mock('../../../../../../../api/client_finance/difference_resolution_client',()=>({differenceResolutionClient:{client:vi.fn(async(case_no:string)=>({case_no,version:0,items:[],events:[]})),payroll:vi.fn(async(case_no:string)=>({case_no,version:0,items:[],events:[]})),staff:vi.fn(async(case_no:string)=>({case_no,items:[],events:[]}))}}));
vi.mock('../../../../../../../api/client_finance/client_receipt_query_client',()=>({clientReceiptQueryClient:{query:vi.fn()}}));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({ ordersQueryClient: { getOrderSummaries: vi.fn() } }));

vi.mock('../../../../../../../api/finance_import/finance_accounting_client', async importOriginal => ({ ...await importOriginal<typeof import('../../../../../../../api/finance_import/finance_accounting_client')>(), financeAccountingClient: { query: vi.fn(), warnings: vi.fn(), dismiss: vi.fn(), manual: vi.fn(), duplicate: vi.fn(), download: vi.fn() } }));

function detail(caseNo = '115000701'): CaseAccounting {
  return { case_no: caseNo, client_name: '測試客戶', receivable_ntd: 10000, received_ntd: 10030, payable_ntd: 10000, paid_ntd: 9970, pending_warning_count: 1,
    client_items: [{ identity: 'client-deposit', direction: 'receivable', label: '訂金', party: '測試客戶', expected_ntd: 10000, actual_ntd: 10030, has_payment: true, version: '1:0:0', due_date: '2026-10-29' }],
    staff_items: [{ identity: 'staff-pay', direction: 'payable', label: '月嫂付款', party: '測試月嫂', expected_ntd: 10000, actual_ntd: 9970, has_payment: true, version: '1:1:1:0', due_date: '2026-10-29' }],
    transactions: [{ identity: 'transaction-1', item_identity: 'staff-pay', occurred_on: '2026-10-29', kind: 'payout', amount_ntd: 9970, bank: 'sinopac' }],
    warnings: [{ item_identity: 'client-deposit', kind: 'over_received', expected_ntd: 10000, actual_ntd: 10030, difference_ntd: -30, source_version: '1:0:0', dismissed: false, dismissed_by: null, dismissed_at: null }],
  };
}
function orderPage(cases: string[], client_name = '測試客戶', next_cursor: string | null = null): Awaited<ReturnType<typeof ordersQueryClient.getOrderSummaries>> {
  return { items: cases.map(case_no => ({ case_no, client_name, order_status: '訂單完成', staff_name: null, identity_status: null,
    start_date: null, end_date: null, actual_start_date: null, actual_end_date: null, service_days: null, total_employer_self_pay_payable: null })), next_cursor, etag: 'a'.repeat(64) };
}
beforeEach(() => { vi.clearAllMocks(); vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue(orderPage([])); vi.mocked(clientReceiptQueryClient.query).mockResolvedValue({case_no:'115000701',account_version:0,bank_facts:[],obligations:[]}); });
describe('案件帳務及成功明細', () => {
  it('refreshes the difference facts alongside the case balance after an inline partial receipt', async () => {
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
    render(<FinanceCaseAccounting initialCase="115000701" />);
    const panel=await screen.findByRole('region',{name:'差額處理與人工金額更正'});
    await waitFor(()=>expect(within(panel).getByRole('row',{name:/訂金/}).children[2]).toHaveTextContent('NT$ 0'));
    fireEvent.click(await screen.findByRole('button',{name:'核對本案入款'}));
    fireEvent.change(await screen.findByRole('combobox',{name:'選擇差額處理'}),{target:{value:'partial'}});
    fireEvent.click(await screen.findByRole('button',{name:'確認核銷本次收款'}));
    await screen.findByText('已記錄實際收款，剩餘款項繼續待收。');
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
  it('shows unified owner facts, details and persistent dismissal without inferring bank fees', async () => {
    vi.mocked(financeAccountingClient.query).mockResolvedValue(detail());
    const dismissed = detail(); dismissed.pending_warning_count = 0; dismissed.warnings[0] = { ...dismissed.warnings[0], dismissed: true, dismissed_by: 'operator', dismissed_at: '2026-10-29' };
    vi.mocked(financeAccountingClient.dismiss).mockResolvedValue(dismissed);
    render(<FinanceCaseAccounting initialCase="115000701" />);
    expect(await screen.findByText('本案帳務明細')).toBeInTheDocument();
    expect(screen.queryByText('100 元內 · 手續費參考，請人工檢查')).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: '展開明細' })[1]);
    expect(screen.getByRole('region', { name: '收付款明細' })).toHaveTextContent('永豐');
    fireEvent.click(screen.getByText('金額警示與既有檢查紀錄'));
    fireEvent.click(screen.getByRole('button', { name: '解除警示' }));
    expect(await screen.findByText('帳務警示 · 待檢查 0')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: '顯示已解除' }));
    expect(screen.getByText(/已解除 · operator/)).toBeInTheDocument();
  });

  it('keeps warning visible after failed dismissal and does not replace missing data with zeros', async () => {
    vi.mocked(financeAccountingClient.query).mockResolvedValue(detail());
    vi.mocked(financeAccountingClient.dismiss).mockRejectedValue(new Error('conflict'));
    render(<FinanceCaseAccounting initialCase="115000701" />);
    fireEvent.click(await screen.findByRole('button', { name: '解除警示' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('解除失敗');
    expect(screen.getByText('帳務警示 · 待檢查 1')).toBeInTheDocument();
  });

  it('ignores an old case response after changing cases', async () => {
    let finish: (value: CaseAccounting) => void = () => {};
    vi.mocked(financeAccountingClient.query).mockImplementation(caseNo => caseNo === '115000701' ? new Promise(resolve => { finish = resolve; }) : Promise.resolve(detail(caseNo)));
    render(<FinanceCaseAccounting initialCase="115000701" />);
    fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: '115000702' } });
    fireEvent.click(screen.getByRole('button', { name: '查看案件' }));
    expect(await screen.findByText('測試客戶 · 案件 115000702')).toBeInTheDocument();
    finish(detail());
    await waitFor(() => expect(screen.queryByText('測試客戶 · 案件 115000701')).not.toBeInTheDocument());
  });

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

  it('requires explicit case selection when a name matches multiple cases', async () => {
    vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue({ items: ['115000701', '115000702'].map(case_no => ({
      case_no, client_name: '同名客戶', order_status: '訂單完成', staff_name: null, identity_status: null,
      start_date: null, end_date: null, actual_start_date: null, actual_end_date: null, service_days: null,
      total_employer_self_pay_payable: null,
    })), next_cursor: null, etag: 'a'.repeat(64) });
    vi.mocked(financeAccountingClient.query).mockResolvedValue(detail('115000702'));
    render(<FinanceCaseAccounting />);
    fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: '同名客戶' } });
    fireEvent.click(screen.getByRole('button', { name: '查看案件' }));
    await screen.findByRole('option', { name: '115000702｜同名客戶' });
    expect(financeAccountingClient.query).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('選擇案件'), { target: { value: '115000702' } });
    expect(await screen.findByText('測試客戶 · 案件 115000702')).toBeInTheDocument();
    expect(financeAccountingClient.query).toHaveBeenCalledTimes(1);
  });

  it('loads a case dropdown before typing and opens an explicitly chosen non-citizen case', async () => {
    vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue(orderPage(['115000701', 'A115001']));
    vi.mocked(financeAccountingClient.query).mockImplementation(async caseNo => detail(caseNo));
    render(<FinanceCaseAccounting />);
    await screen.findByRole('option', { name: 'A115001｜測試客戶' });
    expect(financeAccountingClient.query).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('選擇案件'), { target: { value: 'A115001' } });
    await screen.findByText('測試客戶 · 案件 A115001');
    expect(screen.getByLabelText('案件編號')).toHaveValue('A115001');
    expect(financeAccountingClient.query).toHaveBeenCalledTimes(1);
    expect(financeAccountingClient.query).toHaveBeenCalledWith('A115001', expect.any(AbortSignal));
  });

  it('continues dropdown pages and filters by partial case number without auto-selecting', async () => {
    vi.mocked(ordersQueryClient.getOrderSummaries)
      .mockResolvedValueOnce(orderPage(['115000701'], '測試客戶', '115000701'))
      .mockResolvedValueOnce(orderPage(['A115001']))
      .mockResolvedValueOnce(orderPage(['115000702', '115000703'], '同名客戶'));
    render(<FinanceCaseAccounting />);
    fireEvent.click(await screen.findByRole('button', { name: '載入更多案件' }));
    await screen.findByRole('option', { name: 'A115001｜測試客戶' });
    expect(screen.getByRole('option', { name: '115000701｜測試客戶' })).toBeInTheDocument();
    expect(ordersQueryClient.getOrderSummaries).toHaveBeenNthCalledWith(2, { query_text: '', page_size: 50, after_case_no: '115000701' }, { signal: expect.any(AbortSignal) });
    fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: '1150007' } });
    fireEvent.click(screen.getByRole('button', { name: '查看案件' }));
    await screen.findByRole('option', { name: '115000703｜同名客戶' });
    expect(screen.queryByRole('option', { name: 'A115001｜測試客戶' })).not.toBeInTheDocument();
    expect(financeAccountingClient.query).not.toHaveBeenCalled();
    expect(ordersQueryClient.getOrderSummaries).toHaveBeenLastCalledWith({ query_text: '1150007', page_size: 50 }, { signal: expect.any(AbortSignal) });
  });

  it('keeps direct full-number lookup available after a dropdown load failure', async () => {
    vi.mocked(ordersQueryClient.getOrderSummaries).mockRejectedValue(new Error('unavailable'));
    vi.mocked(financeAccountingClient.query).mockResolvedValue(detail('A115001'));
    render(<FinanceCaseAccounting />);
    await screen.findByText('案件搜尋失敗，請稍後再試。');
    fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'A115001' } });
    fireEvent.click(screen.getByRole('button', { name: '查看案件' }));
    await screen.findByText('測試客戶 · 案件 A115001');
    expect(screen.queryByText('案件搜尋失敗，請稍後再試。')).not.toBeInTheDocument();
  });

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
