import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {beforeEach,describe,expect,it,vi} from 'vitest';
import {FinanceCaseAccounting} from '../../../../../../../components/FinanceCaseAccounting';
import {FinanceCaseNotice} from '../../../../../../../components/FinanceCaseNotice';
import {FinanceSubsidyPlanForm} from '../../../../../../../components/FinanceSubsidyPlanForm';
import {UnsavedChangesProvider} from '../../../../../../../components/UnsavedChanges';
import {financeAccountingClient,type CaseAccounting} from '../../../../../../../api/finance_import/finance_accounting_client';
import {paymentOverdueReminderClient,type CasePaymentReminder} from '../../../../../../../api/line_order_groups/payment_overdue_reminder_client';
import {ordersQueryClient} from '../../../../../../../api/orders/order_query_client';
import {clientRegistryClient} from '../../../../../../../api/client_registry/client_registry_client';
import {caseVirtualAccountClient} from '../../../../../../../api/client_finance/case_virtual_account_client';
import {clientReceiptQueryClient} from '../../../../../../../api/client_finance/client_receipt_query_client';
import {ApiHttpError} from '../../../../../../../api/shared/typed_errors';
import {notifyCaseAccountingChanged} from '../../../../../../../api/shared/case_accounting_changes';
import {financeImportQueryClient} from '../../../../../../../api/finance_import/finance_import_query_client';
import {clientReceiptReconciliationClient} from '../../../../../../../api/client_finance/client_receipt_reconciliation_client';
import {clientRefundReturnClient} from '../../../../../../../api/client_finance/client_settlement_remediation_client';
import type {FinanceBankTransaction} from '../../../../../../../api/finance_import/finance_import_query_schemas';
vi.mock('../../../../../../../api/finance_import/finance_import_query_client',()=>({financeImportQueryClient:{listBankTransactions:vi.fn()}}));
vi.mock('../../../../../../../api/client_finance/client_receipt_reconciliation_client',()=>({clientReceiptReconciliationClient:{preview:vi.fn(),apply:vi.fn()}}));
vi.mock('../../../../../../../api/finance_import/finance_accounting_client',()=>({financeAccountingClient:{query:vi.fn(),saveSubsidyPlan:vi.fn(),subsidyPlan:vi.fn(),previewSubsidyPlan:vi.fn()}}));
vi.mock('../../../../../../../api/line_order_groups/payment_overdue_reminder_client',()=>({paymentOverdueReminderClient:{case:vi.fn(),sendCase:vi.fn()}}));
vi.mock('../../../../../../../api/orders/order_query_client',()=>({ordersQueryClient:{getOrderDetail:vi.fn()}}));
vi.mock('../../../../../../../api/client_registry/client_registry_client',()=>({clientRegistryClient:{query:vi.fn()}}));
vi.mock('../../../../../../../api/client_finance/case_virtual_account_client',()=>({caseVirtualAccountClient:{query:vi.fn()}}));
vi.mock('../../../../../../../api/client_finance/client_receipt_query_client',()=>({clientReceiptQueryClient:{query:vi.fn()}}));
vi.mock('../../../../../../../api/client_finance/difference_resolution_client',()=>({differenceResolutionClient:{client:vi.fn().mockResolvedValue({case_no:'115000701',version:0,items:[],events:[]}),apply:vi.fn()}}));
const caseNo='115000701';
const plan={case_no:caseNo,version:0,events:[]};
it.each([['taishin','台新銀行'],['sinopac','永豐銀行']])('退款回讀分開顯示 %s 實付與內扣手續費，不計為月嫂已核銷',async(bank,bankLabel)=>{
 const data={...facts(),subsidy_ntd:12000,paid_ntd:12000,
  staff_items:[{...facts().staff_items[0],expected_ntd:30000,actual_ntd:0,remaining_ntd:30000}],
  client_items:[{...facts().client_items[0],identity:'refund:1',direction:'payable' as const,
   label:'補助退款',expected_ntd:12000,actual_ntd:12000,remaining_ntd:0,has_payment:true}],
  transactions:[{identity:'client-entry:1:refund:1',item_identity:'refund:1',occurred_on:'2026-11-15',
   kind:'subsidy_return',amount_ntd:12000,bank,bank_amount_ntd:11970,transfer_fee_ntd:30}]};
 vi.mocked(financeAccountingClient.query).mockResolvedValue(data);
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 expect(await screen.findByText('整筆銀行實付 NT$ 11,970；內扣手續費 NT$ 30')).toBeVisible();
 expect(screen.getByText(`2026-11-15 · ${bankLabel}`,{exact:true})).toBeVisible();
 expect(within(screen.getByLabelText('月嫂薪資匯總')).getByText('NT$ 0')).toBeVisible();
});
it('未成立補助退款不顯示已結清，也不把自動推算代碼當成已確認方案',async()=>{
 const data={...facts(),subsidy_ntd:12000,scheme:'advance' as const,
  client_items:facts().client_items.filter(row=>row.direction!=='payable')};
 vi.mocked(financeAccountingClient.query).mockResolvedValue(data);
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 const section=await screen.findByRole('region',{name:'補助退款與政府核銷明細，可左右捲動'});
 expect(section.closest('details')?.querySelector('.finance-refund-summary-bar')).toHaveTextContent('補助歸屬待確認');
 expect(within(section).queryByText('advance',{exact:true})).not.toBeInTheDocument();
});
it.each([
 ['歷史訂單－服務中','estimate','服務中，金額尚未確認'],
 ['歷史訂單－服務完成','estimate','服務已結束，金額待核對'],
 ['歷史訂單－服務完成','formal','服務已結束，金額已確認'],
] as const)('補助給付依 %s 和 %s 顯示金額確認進度',async(orderStatus,source,label)=>{
 const data:CaseAccounting={...facts(),scheme:'split',subsidy_payments:[
  {recipient:'staff',party:'合成月嫂',amount_ntd:12000,due_date:'2026-11-15',source},
 ]};
 vi.mocked(financeAccountingClient.query).mockResolvedValue(data);
 vi.mocked(ordersQueryClient.getOrderDetail).mockResolvedValue({case_no:caseNo,order_status:orderStatus} as never);
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 const payments=within(await screen.findByRole('region',{name:'補助款預計給付'}));
 expect(payments.getByText(label,{exact:true})).toBeVisible();
 expect(payments.getByText(source==='estimate'?'預估 NT$ 12,000':'NT$ 12,000',{exact:true})).toBeVisible();
 expect(payments.getByText('2026-11-15',{exact:true})).toBeVisible();
});
it('方案未定仍顯示補助，預檢缺件只阻擋建款且先說明本次保存範圍',async()=>{
 vi.mocked(financeAccountingClient.previewSubsidyPlan).mockResolvedValue({case_no:caseNo,scheme:'advance',plan_version:0,
  subsidy_ntd:12000,total_ntd:30000,confirmation_only:false,payables:[],blocker:'客戶實際墊款依據不足',preview_fingerprint:'c'.repeat(64)});
 wrapper(<FinanceSubsidyPlanForm caseNo={caseNo} source={plan} subsidyAmount={12000} onSaved={vi.fn()} onBack={vi.fn()}/>);
 expect(screen.getByText(/本案補助金額：12,000 元/)).toBeVisible();
 fireEvent.click(screen.getByRole('radio',{name:/客戶先墊後退/}));
 await screen.findByRole('alert');
 expect(screen.getByRole('alert')).toHaveTextContent('仍可儲存補助方案');
 expect(screen.getByRole('alert')).toHaveTextContent('給付金額待核對');
 expect(financeAccountingClient.saveSubsidyPlan).not.toHaveBeenCalled();
});

it('已依明細確認的方案直接顯示確認來源，無須再人工選擇',async()=>{
 const data=facts();data.subsidy_plan={case_no:caseNo,version:1,events:[{version:1,scheme:'advance',actor:'synthetic',created_at:'2026-11-09T00:00:00Z',source:'bank',bank_row_identity:'finance-import-row:11'}]};
 vi.mocked(financeAccountingClient.query).mockResolvedValue(data);
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 expect(await screen.findByText('依銀行明細確認方案')).toBeVisible();
 expect(financeAccountingClient.saveSubsidyPlan).not.toHaveBeenCalled();
});
function facts():CaseAccounting{return {case_no:caseNo,client_name:'合成客戶',receivable_ntd:30000,received_ntd:20000,payable_ntd:30000,paid_ntd:0,pending_warning_count:0,staff_receivable_ntd:30000,subsidy_ntd:12000,customer_amount_ntd:30000,customer_fully_received:false,scheme:'direct',subsidy_plan:plan,ongoing_completed:false,collection_progress:{stage:'first',sources_complete:true,expected_ntd:15000,received_ntd:14000,remaining_ntd:1000,due_date:'2026-11-01'},client_items:([
 ['deposit',6000,6000,0],['first',15000,14000,1000],['second',9000,0,9000]
] as const).map(([stage,expected,actual,remaining])=>({identity:stage,direction:'receivable',label:stage,party:'合成客戶',expected_ntd:expected,actual_ntd:actual,remaining_ntd:remaining,payment_stage:stage,has_payment:actual>0,version:'1',due_date:stage==='second'?'2099-11-16':'2026-11-01'})),staff_items:[{identity:'staff',direction:'payable',label:'服務費',party:'合成月嫂',expected_ntd:30000,actual_ntd:0,has_payment:false,version:'1',due_date:null}],transactions:[{identity:'receipt',item_identity:'first',occurred_on:'2026-11-02',kind:'receipt',amount_ntd:14000,bank:'sinopac'}],warnings:[]};}
function notice(stage:'deposit'|'first'|'second'='first'):CasePaymentReminder{return {case_no:caseNo,payment_stage:stage,payment:{case_no:caseNo,payment_stage:stage,obligation_identity:stage,projection_version:1,obligation_event_id:1,due_date:'2099-11-16',remaining_amount_ntd:stage==='deposit'?0:1000},recipient_label:'合成客戶（私人LINE）',can_send:stage!=='deposit',unavailable_reason:stage==='deposit'?'本期已繳齊':null,message:'請繳納剩餘 1,000 元。',history:[]};}
function wrapper(ui:React.ReactNode){return render(<UnsavedChangesProvider>{ui}</UnsavedChangesProvider>);}
beforeEach(()=>{vi.clearAllMocks();vi.mocked(financeAccountingClient.previewSubsidyPlan).mockImplementation(async(caseNo,command)=>({case_no:caseNo,scheme:command.scheme,plan_version:command.expected_version,subsidy_ntd:12000,total_ntd:30000,confirmation_only:true,payables:[],blocker:null,preview_fingerprint:'b'.repeat(64)}));vi.mocked(financeAccountingClient.query).mockResolvedValue(facts());vi.mocked(ordersQueryClient.getOrderDetail).mockResolvedValue({case_no:caseNo,actual_start_date:'2026-10-01',actual_end_date:null} as never);vi.mocked(paymentOverdueReminderClient.case).mockResolvedValue(['deposit','first','second'].map(stage=>notice(stage as 'deposit'|'first'|'second')));vi.mocked(clientRegistryClient.query).mockResolvedValue({case_no:caseNo,client:{client_id:1,version:1,values:{name:'合成客戶',phone:'0912345678'}},beclass:{status:'ready',record_id:1,source_kind:'imported',version:1,values:{name:'報名客戶',phone:'0912345678',refund_bank_code:'8120012',refund_account_no:'****5678',refund_account_status:'complete'},field_capabilities:{}},finance:{status:'ready',code:null,values:{virtual_account:'99781699115701'}},order_terms:{status:'ready',code:null,data:null,field_capabilities:{}},order_information:{status:'ready',values:null,field_issues:{}}} as never);vi.mocked(caseVirtualAccountClient.query).mockResolvedValue({case_no:caseNo,imported_virtual_accounts:[],built_in_virtual_account:'99781699115701',mapping_ids:[]});vi.mocked(clientReceiptQueryClient.query).mockResolvedValue({case_no:caseNo,account_version:0,bank_facts:[],obligations:[]});});
describe('精簡案件抽屜',()=>{
 it('committed changes replace stale bank candidates and previews before reconciling the same original row',async()=>{
  let version=1,identity='first';
  const data=()=>({...facts(),client_items:[{...facts().client_items[1],identity,expected_ntd:1000,actual_ntd:0,remaining_ntd:1000,version:`${version}:1:0`}]});
  const receiptFacts=()=>({case_no:caseNo,account_version:version,
   bank_facts:[{finance_import_row_id:7,amount_ntd:1000,transaction_date:'2026-11-09',dedup_fingerprint:'a'.repeat(64)}],
   obligations:[{obligation_identity:identity,payment_stage:'first' as const,amount_due_ntd:1000,due_date:'2026-11-09'}]});
  const bank=()=>({row_id:7,row_identity:'bank:7',bank:'sinopac',direction:'incoming',transaction_date:'2026-11-09',
   reference:'original-7',amount_ntd:1000,status:'pending',classification_type:'client_receipt',
   reconciliation_target:{case_no:caseNo,staff_id:null,obligation_identities:[identity],requires_selection:false}} as FinanceBankTransaction);
  vi.mocked(financeAccountingClient.query).mockImplementation(async()=>data());
  vi.mocked(clientReceiptQueryClient.query).mockImplementation(async()=>receiptFacts());
  vi.mocked(financeImportQueryClient.listBankTransactions).mockImplementation(async()=>({items:[bank()],pending_count:1,next_before_row_id:null}));
  vi.mocked(clientReceiptReconciliationClient.preview).mockImplementation(async()=>({account_version:version,preview_fingerprint:String(version).repeat(64),candidate:{status:'exact',payment_stage:null,bank_total:{amount:1000},obligation_total:{amount:1000},overage_amount:{amount:0},allocations:[],blockers:[],settlement_identity:'a'.repeat(64)}}));
  vi.mocked(clientReceiptReconciliationClient.apply).mockResolvedValue({case_no:caseNo,account_version:3,status:'exact',settlement_identity:'a'.repeat(64),ledger_entry_count:1,allocation_count:1,blockers:[]});
  const posted=vi.fn();
  wrapper(<FinanceCaseAccounting initialCase={caseNo} bankReconciliation={{row:bank(),onPosted:posted,onBusyChange:vi.fn()}}/>);
  fireEvent.click(await screen.findByRole('button',{name:'核對本案入款'}));
  await screen.findByRole('button',{name:'確認核銷本次收款'});
  version=2;identity='corrected-adjustment';await act(async()=>notifyCaseAccountingChanged(caseNo));
  await waitFor(()=>expect(financeImportQueryClient.listBankTransactions).toHaveBeenCalledTimes(2));
  await screen.findByRole('checkbox',{name:/第一期/});
  expect(screen.queryByRole('button',{name:'確認核銷本次收款'})).not.toBeInTheDocument();
  expect(screen.getByRole('checkbox',{name:'納入銀行款 7'})).toBeChecked();
  fireEvent.click(screen.getByRole('button',{name:'核對本案入款'}));
  fireEvent.click(await screen.findByRole('button',{name:'確認核銷本次收款'}));
  await waitFor(()=>expect(posted).toHaveBeenCalledTimes(1));
  expect(clientReceiptReconciliationClient.apply).toHaveBeenCalledWith(caseNo,expect.objectContaining({expected_account_version:2,
   selection:{payment_stage:null,finance_import_row_ids:[7],obligation_identities:['corrected-adjustment']}}));
 });
 it('原始歷史備註逐筆顯示，人工選擇方案才保存且回讀後仍保留原文',async()=>{
  const original=facts();
  original.bank_memos=[
   {identity:'finance-import-row:1',occurred_on:'2026-11-09',memo:'ＨＣ１１５０３２服務人員薪資'},
   {identity:'finance-import-row:2',occurred_on:'2026-11-09',memo:'ＨＣ１１５０９３雇主補助款'},
  ];
  const saved={case_no:caseNo,version:1,events:[{version:1,scheme:'split' as const,actor:'合成人員',created_at:'2026-11-09T00:00:00Z'}]};
  vi.mocked(financeAccountingClient.query).mockResolvedValueOnce(original).mockResolvedValue({...original,subsidy_plan:saved});
  vi.mocked(financeAccountingClient.saveSubsidyPlan).mockResolvedValue({case_no:caseNo,applied_version:1,plan:saved});
  wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
  expect(await screen.findByText('ＨＣ１１５０３２服務人員薪資')).toBeVisible();
  expect(screen.getByText('ＨＣ１１５０９３雇主補助款')).toBeVisible();
  expect(financeAccountingClient.saveSubsidyPlan).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'設定補助退款方案'}));
  expect(within(screen.getByRole('region',{name:'設定補助退款方案'})).getByText('ＨＣ１１５０３２服務人員薪資')).toBeVisible();
  for(const radio of screen.getAllByRole('radio'))expect(radio).not.toBeChecked();
  fireEvent.click(screen.getByRole('radio',{name:/客戶與政府分別入款/}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'儲存方案'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'儲存方案'}));
  await waitFor(()=>expect(financeAccountingClient.saveSubsidyPlan).toHaveBeenCalledOnce());
  expect(vi.mocked(financeAccountingClient.saveSubsidyPlan).mock.calls[0][1]).toEqual({scheme:'split',expected_version:0,preview_fingerprint:'b'.repeat(64)});
  expect(await screen.findByRole('button',{name:'修改補助退款方案'})).toBeVisible();
  expect(screen.getByText('ＨＣ１１５０３２服務人員薪資')).toBeVisible();
  expect(screen.getByText('ＨＣ１１５０９３雇主補助款')).toBeVisible();
 });
  it('呈現完整四個帳務區塊（客戶繳款、補助方案、月嫂薪資、補助退款核銷）；各項帳務事實照實呈現',async()=>{
    wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
    const periodsTable=await screen.findByLabelText('各期繳款與通知，可左右捲動');
    expect(within(periodsTable).getAllByRole('columnheader').map(e=>e.textContent)).toEqual(['期款','原到期日','應繳','已收／待收','入帳資訊','通知時間','通知']);
    expect(document.querySelectorAll('details.finance-case-block:not(.finance-case-edit-tools)')).toHaveLength(4);
    expect(screen.getByText(/01.*客戶繳款/)).toBeInTheDocument();
    expect(screen.getByText(/02.*補助退款方案/)).toBeInTheDocument();
    expect(screen.getByText(/03.*月嫂薪資/)).toBeInTheDocument();
    expect(screen.getByText(/04.*補助退款與核銷/)).toBeInTheDocument();
    expect(screen.getAllByText('合成月嫂').length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
    expect(screen.queryByText('核對本期收款')).not.toBeInTheDocument();
    expect(screen.queryByText('另有銀行資料待核對，由銀行對帳處理')).not.toBeInTheDocument();
    expect(screen.getByText('2026-11-02 · 永豐')).toBeVisible();
    expect(within(screen.getByLabelText('案件精簡摘要')).getByText('待確認')).toBeVisible();
    expect(screen.getByRole('button',{name:'通知訂金'})).toBeDisabled();
    expect(screen.getByRole('button',{name:'通知第二期'})).toBeEnabled();
    expect(screen.getByRole('button',{name:'設定補助退款方案'})).toBeEnabled();
  });
 it('排隊時間不能冒充成功通知，成功時間以台灣時區顯示',async()=>{
  const rows=[notice('deposit'),notice(),notice('second')];
  rows[1].history=[{task_id:1,requested_at:'2026-11-04T02:00:00Z',sent_at:null,status:'pending',content:'待送',actor:null}];
  rows[2].history=[{task_id:2,requested_at:'2026-11-03T01:00:00Z',sent_at:'2026-11-03T02:30:00Z',status:'sent',content:'已送',actor:'合成人員'}];
  vi.mocked(paymentOverdueReminderClient.case).mockResolvedValue(rows);
  wrapper(<FinanceCaseAccounting initialCase={caseNo}/>);
  expect(await screen.findByText('尚無成功通知')).toBeVisible();
  expect(screen.getByText('排隊中')).toBeVisible();
  expect(screen.getByText('2026-11-03 10:30')).toBeVisible();
  expect(screen.queryByText('2026-11-04 10:00')).not.toBeInTheDocument();
 });
 it('通知來源失敗仍保留帳務；不得當成未通知或可寄送',async()=>{
  vi.mocked(paymentOverdueReminderClient.case).mockRejectedValue(new Error('unavailable'));
  wrapper(<FinanceCaseAccounting initialCase={caseNo}/>);
  expect(await screen.findByText(/通知資料暫時無法取得/)).toBeVisible();
  expect(screen.queryByText('尚未通知')).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'通知第一期'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'設定補助退款方案'})).toBeEnabled();
 });
 it('提前設定人工方案不採自動分類預選，成功返回同案並重讀正式結果',async()=>{
  const onChanged=vi.fn();
  const saved={case_no:caseNo,version:1,events:[{version:1,scheme:'advance' as const,actor:'人員',created_at:'2026-11-05T00:00:00Z'}]};
  vi.mocked(financeAccountingClient.saveSubsidyPlan).mockResolvedValue({case_no:caseNo,applied_version:1,plan:saved});
  wrapper(<FinanceCaseAccounting initialCase={caseNo} onChanged={onChanged}/>);
  fireEvent.click(await screen.findByRole('button',{name:'設定補助退款方案'}));
  expect(screen.getAllByRole('radio').every(input=>!(input as HTMLInputElement).checked)).toBe(true);
  fireEvent.click(screen.getByRole('radio',{name:/客戶先墊後退/}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'儲存方案'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'儲存方案'}));
  await waitFor(()=>expect(onChanged).toHaveBeenCalledOnce());
  expect(financeAccountingClient.saveSubsidyPlan).toHaveBeenCalledWith(caseNo,{scheme:'advance',expected_version:0,preview_fingerprint:'b'.repeat(64)},expect.any(String));
  await screen.findByLabelText('各期繳款與通知，可左右捲動');
  expect(financeAccountingClient.query).toHaveBeenCalledTimes(2);
 });
 it('呈現專屬虛擬帳號、退款帳號與銀行資訊，提供快速複製與對帳依據',async()=>{
  wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
  expect(await screen.findByTestId('virtual-account-display')).toHaveTextContent('99781699115701');
  expect(screen.getByTestId('refund-bank-display')).toHaveTextContent('812 台新銀行（分行 0012）');
  expect(screen.getByTestId('refund-account-display')).toHaveTextContent('****5678');
  expect(screen.getByText('已登錄完整')).toBeVisible();
  expect(screen.getByRole('button',{name:'複製虛擬帳號'})).toBeVisible();
 });
 it('帳務摘要和退款區直接顯示經授權的完整退款帳號與戶名',async()=>{
  const registry=await clientRegistryClient.query(caseNo);
  vi.mocked(clientRegistryClient.query).mockResolvedValueOnce({
   ...registry,beclass:{...registry.beclass,full_refund_account_visible:true,
    values:{...registry.beclass.values!,refund_account_no:'000000009876'}},
  });
  wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
  expect(await screen.findByTestId('refund-account-display')).toHaveTextContent('000000009876');
  expect(screen.getByLabelText('銀行對帳與帳戶資訊')).toHaveTextContent('報名客戶');
  expect(screen.getByText(/\(000000009876\)/)).toBeInTheDocument();
  expect(clientRegistryClient.query).toHaveBeenLastCalledWith(caseNo,expect.any(AbortSignal),true);
 });
 it.each(['client_refund','client_refund_return'])('銀行核對 %s 顯示名冊退款戶名與完整帳號',async(classification)=>{
  const registry=await clientRegistryClient.query(caseNo);
  vi.mocked(clientRegistryClient.query).mockResolvedValueOnce({
   ...registry,beclass:{...registry.beclass,full_refund_account_visible:true,
    values:{...registry.beclass.values!,refund_account_no:'000000009876'}},
  });
  const returnQuery=vi.spyOn(clientRefundReturnClient,'query').mockResolvedValue({
   case_no:caseNo,account_version:0,refund_obligations:[],subsidy_return_obligations:[],
   refund_bank_facts:[],subsidy_return_bank_facts:[],reversal_targets:[],refund_return_targets:[],
  });
  const row:FinanceBankTransaction={row_id:7,row_identity:'bank:7',bank:'sinopac',direction:classification==='client_refund'?'outgoing':'incoming',
   transaction_date:'2026-11-09',reference:'original-7',amount_ntd:1000,status:'pending',classification_type:classification,
   disposition:'pending',review_reason:null,available_actions:[],counterparty_name:null,cases:[caseNo],
   reconciliation_target:{case_no:caseNo,staff_id:null,obligation_identities:[],requires_selection:false}};
  vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({items:[row],pending_count:1,next_before_row_id:null});
  try {
   wrapper(<FinanceCaseAccounting initialCase={caseNo} bankReconciliation={{row,onPosted:vi.fn(),onBusyChange:vi.fn()}}/>);
   expect(await screen.findByText('名冊退款戶名：報名客戶 · 名冊退款帳號：000000009876')).toBeVisible();
  } finally {
   returnQuery.mockRestore();
  }
 });
 it('退款帳號缺漏時明確標示待補齊狀態，便於區分是無資料還是流水未配對',async()=>{
  vi.mocked(clientRegistryClient.query).mockResolvedValueOnce({
    case_no: caseNo,
    client: { client_id: 1, version: 1, values: { name: '合成客戶', phone: null } },
    beclass: {
      status: 'ready',
      record_id: 1,
      source_kind: 'imported',
      version: 1,
      values: {
        name: '報名客戶',
        phone: null,
        refund_bank_code: null,
        refund_account_no: null,
        refund_account_status: 'incomplete',
      },
      field_capabilities: {},
    },
    finance: {
      status: 'ready',
      code: null,
      values: { virtual_account: null },
    },
    order_terms: { status: 'ready', code: null, data: null, field_capabilities: {} },
    order_information: { status: 'ready', values: null, field_issues: {} },
  } as never);
  vi.mocked(caseVirtualAccountClient.query).mockResolvedValueOnce({
    case_no: caseNo,
    imported_virtual_accounts: [],
    built_in_virtual_account: null,
    mapping_ids: [],
  });
  wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
  expect(await screen.findByTestId('refund-bank-missing')).toHaveTextContent('待補齊 / 未填寫銀行代碼');
  expect(screen.getByTestId('refund-account-missing')).toHaveTextContent('待補齊 / 未填寫帳號');
  expect(screen.getByText('未填寫')).toBeVisible();
 });
 it('同月待核對入款不計入期款，案件抽屜保留正式已收與待收',async()=>{
  vi.mocked(clientReceiptQueryClient.query).mockResolvedValue({
    case_no: caseNo,
    account_version: 1,
    obligations: [
      { obligation_identity: 'first', payment_stage: 'first', amount_due_ntd: 15000, due_date: '2026-11-01' }
    ],
    bank_facts: [
      { finance_import_row_id: 101, amount_ntd: 10000, transaction_date: '2026-11-05', dedup_fingerprint: 'fp-1' }
    ]
  });
  wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
  const first = await screen.findByRole('row',{name:/第一期/});
  expect(first).toHaveTextContent('2026-11-02 · 永豐');
  expect(first).toHaveTextContent('已收 NT$ 14,000');
  expect(first).toHaveTextContent('待收 NT$ 1,000');
  expect(first).not.toHaveTextContent(/待核對入款|短少|超收/);
  expect(within(first).queryByRole('button',{name:/處置.*差額/})).not.toBeInTheDocument();
  expect(clientReceiptQueryClient.query).not.toHaveBeenCalled();
  expect(screen.queryByRole('region',{name:'本案待核對客戶入款'})).not.toBeInTheDocument();
 });
});
describe('同案通知與方案保存防重',()=>{
 it('通知結果未知沿原鍵查回；排隊成功不顯示已發送',async()=>{
  vi.mocked(paymentOverdueReminderClient.sendCase).mockRejectedValueOnce(new Error('lost response')).mockResolvedValueOnce({task_id:8,status:'pending'});
  const onChanged=vi.fn();wrapper(<FinanceCaseNotice item={notice()} onBack={vi.fn()} onChanged={onChanged}/>);
  expect(screen.getByText('請繳納剩餘 1,000 元。')).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'發送通知'}));
  fireEvent.click(await screen.findByRole('button',{name:'確認原操作結果'}));
  await waitFor(()=>expect(onChanged).toHaveBeenCalledOnce());
  expect(screen.getByRole('status')).toHaveTextContent('已建立通知工作；仍須等待成功結果，不代表已發送');
  const calls=vi.mocked(paymentOverdueReminderClient.sendCase).mock.calls;
  expect(calls[1][1]).toEqual(calls[0][1]);expect(calls[1][0]).toEqual(calls[0][0]);
  expect(screen.getByRole('button',{name:'已建立寄送工作'})).toBeDisabled();
 });
 it('方案版本衝突保留選擇，重讀版本後明確再存；未知結果沿原鍵',async()=>{
  const saved={case_no:caseNo,version:2,events:[{version:1,scheme:'direct' as const,actor:'甲',created_at:'2026-11-05T00:00:00Z'},{version:2,scheme:'split' as const,actor:'乙',created_at:'2026-11-05T01:00:00Z'}]};
  vi.mocked(financeAccountingClient.saveSubsidyPlan).mockRejectedValueOnce(new ApiHttpError(409,'CONFLICT','stale')).mockRejectedValueOnce(new Error('unknown')).mockResolvedValueOnce({case_no:caseNo,applied_version:2,plan:saved});
  vi.mocked(financeAccountingClient.subsidyPlan).mockResolvedValue({case_no:caseNo,version:1,events:[saved.events[0]]});
  const onSaved=vi.fn();wrapper(<FinanceSubsidyPlanForm caseNo={caseNo} source={plan} onBack={vi.fn()} onSaved={onSaved}/>);
  fireEvent.click(screen.getByRole('radio',{name:/客戶與政府分別入款/}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'儲存方案'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'儲存方案'}));
  fireEvent.click(await screen.findByRole('button',{name:'重新讀取方案'}));
  await waitFor(()=>expect(financeAccountingClient.subsidyPlan).toHaveBeenCalledOnce());
  await waitFor(()=>expect(screen.getByRole('button',{name:'儲存方案'})).toBeEnabled());
  expect(screen.getByRole('radio',{name:/客戶與政府分別入款/})).toBeChecked();
  await waitFor(()=>expect(screen.getByRole('button',{name:'儲存方案'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'儲存方案'}));
  fireEvent.click(await screen.findByRole('button',{name:'確認原操作結果'}));
  await waitFor(()=>expect(onSaved).toHaveBeenCalledWith(saved));
  const calls=vi.mocked(financeAccountingClient.saveSubsidyPlan).mock.calls;
  expect(calls[1][1]).toEqual({scheme:'split',expected_version:1,preview_fingerprint:'b'.repeat(64)});expect(calls[2][2]).toBe(calls[1][2]);
 });
});
