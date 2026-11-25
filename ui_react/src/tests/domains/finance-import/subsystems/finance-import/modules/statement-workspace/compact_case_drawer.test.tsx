/**
 * File: compact_case_drawer.test.tsx
 * Description: 案件精簡抽屜之帳務呈現、方案確認、退款沖抵與核對整合測試。
 */
import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {readFileSync} from 'node:fs';
import {z} from 'zod';
import {transport} from '../../../../../../../api/shared/transport';
import {sessionClient} from '../../../../../../../api/auth/session_client';
import {beforeEach,describe,expect,it,vi} from 'vitest';
import {FinanceCaseAccounting} from '../../../../../../../components/FinanceCaseAccounting';
import {ClientRegistryAccountingSummary} from '../../../../../../../components/ClientRegistryAccountingSummary';
import {subsidyPeriodClient} from '../../../../../../../api/government_subsidy/period_reconciliation_client';
import {FinanceCaseNotice} from '../../../../../../../components/FinanceCaseNotice';
import {FinanceSubsidyPlanForm} from '../../../../../../../components/FinanceSubsidyPlanForm';
import {UnsavedChangesProvider} from '../../../../../../../components/UnsavedChanges';
import {financeAccountingClient,type CaseAccounting} from '../../../../../../../api/finance_import/finance_accounting_client';
import {paymentOverdueReminderClient,type CasePaymentReminder} from '../../../../../../../api/line_order_groups/payment_overdue_reminder_client';
import {ordersQueryClient} from '../../../../../../../api/orders/order_query_client';
import {clientRegistryClient} from '../../../../../../../api/client_registry/client_registry_client';
import {caseVirtualAccountClient} from '../../../../../../../api/client_finance/case_virtual_account_client';
import {accountingPricingClient} from '../../../../../../../api/client_finance/accounting_pricing_client';
import {clientReceiptQueryClient} from '../../../../../../../api/client_finance/client_receipt_query_client';
import {ApiHttpError} from '../../../../../../../api/shared/typed_errors';
import {notifyCaseAccountingChanged} from '../../../../../../../api/shared/case_accounting_changes';
import {financeImportQueryClient} from '../../../../../../../api/finance_import/finance_import_query_client';
import {clientReceiptReconciliationClient} from '../../../../../../../api/client_finance/client_receipt_reconciliation_client';
import {clientRefundReturnClient,clientSettlementRemediationClient} from '../../../../../../../api/client_finance/client_settlement_remediation_client';
import {financeImportCorrectionClient} from '../../../../../../../api/finance_import/finance_import_correction_client';
import {orderCancellationClient,type OrderCancellationQuery} from '../../../../../../../api/orders/order_cancellation_client';
import {orderMutationFlowStore} from '../../../../../../../adapters/orders/order_mutation_flow_store';
import type {FinanceBankTransaction} from '../../../../../../../api/finance_import/finance_import_query_schemas';
import {differenceResolutionClient} from '../../../../../../../api/client_finance/difference_resolution_client';
vi.mock('../../../../../../../api/finance_import/finance_import_query_client',()=>({financeImportQueryClient:{listBankTransactions:vi.fn(),pairBankTransaction:vi.fn()}}));
vi.mock('../../../../../../../api/client_finance/client_receipt_reconciliation_client',()=>({clientReceiptReconciliationClient:{preview:vi.fn(),apply:vi.fn()}}));
vi.mock('../../../../../../../api/finance_import/finance_accounting_client',()=>({financeAccountingClient:{query:vi.fn(),saveSubsidyPlan:vi.fn(),subsidyPlan:vi.fn(),previewSubsidyPlan:vi.fn()}}));
vi.mock('../../../../../../../api/line_order_groups/payment_overdue_reminder_client',()=>({paymentOverdueReminderClient:{case:vi.fn(),sendCase:vi.fn()}}));
vi.mock('../../../../../../../api/orders/order_query_client',()=>({ordersQueryClient:{getOrderDetail:vi.fn()}}));
vi.mock('../../../../../../../api/client_registry/client_registry_client',()=>({clientRegistryClient:{query:vi.fn()}}));
vi.mock('../../../../../../../api/client_finance/case_virtual_account_client',()=>({caseVirtualAccountClient:{query:vi.fn()}}));
vi.mock('../../../../../../../api/client_finance/client_receipt_query_client',()=>({clientReceiptQueryClient:{query:vi.fn()}}));
vi.mock('../../../../../../../api/client_finance/difference_resolution_client',()=>({differenceResolutionClient:{staff:vi.fn().mockResolvedValue({case_no:'115000701',items:[],events:[]}),client:vi.fn().mockResolvedValue({case_no:'115000701',version:0,items:[],events:[]}),apply:vi.fn(),syncHistoricalBaseline:vi.fn()}}));
vi.mock('../../../../../../../api/client_finance/accounting_pricing_client',async importOriginal=>{const actual=await importOriginal<typeof import('../../../../../../../api/client_finance/accounting_pricing_client')>();return {...actual,accountingPricingClient:{...actual.accountingPricingClient,queryCase:vi.fn()}};});
vi.mock('../../../../../../../api/government_subsidy/period_reconciliation_client',()=>({subsidyPeriodClient:{caseCoverage:vi.fn()}}));
vi.mock('../../../../../../../components/StaffOverpaymentRecoveryActions',()=>({StaffOverpaymentRecoveryActions:({recoveryIdentity}:{recoveryIdentity:string})=><section aria-label="月嫂追償核對">{recoveryIdentity}</section>}));
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
 const payments=within(await screen.findByRole('region',{name:'補助退款與政府核銷明細，可左右捲動'}));
 const staff=within(payments.getByRole('row',{name:/補助款轉付月嫂/}));
 expect(staff.getByText(label,{exact:true})).toBeVisible();
 expect(staff.getByText(source==='estimate'?'預估 NT$ 12,000':'NT$ 12,000',{exact:true})).toBeVisible();
 expect(staff.getByText('2026-11-15',{exact:true})).toBeVisible();
});
it('方案未定由政府列顯示已知補助，未列出收款對象',async()=>{
 vi.mocked(financeAccountingClient.query).mockResolvedValue({...facts(),scheme:'waiting',subsidy_payments:[],estimated_subsidy_payment_date:'2027-02-15'});
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 const details=within(await screen.findByRole('region',{name:'補助退款與政府核銷明細，可左右捲動'}));
 const government=within(details.getByRole('row',{name:/政府補助款/}));
 expect(government.getByText('NT$ 12,000',{exact:true})).toBeVisible();
 expect(government.getByText('補助歸屬待確認')).toBeVisible();
 expect(government.getByText('補助給付預估：2027-02-15')).toBeVisible();
 expect(details.queryByRole('row',{name:/補助款退還客戶|補助款轉付月嫂/})).not.toBeInTheDocument();
});
it('方案二已保存但沒有正式退款時，仍指出款項待建立',async()=>{
 vi.mocked(financeAccountingClient.query).mockResolvedValue({...facts(),scheme:'advance',subsidy_ntd:12000,
  client_items:facts().client_items.filter(row=>row.direction!=='payable'),
  subsidy_plan:{case_no:caseNo,version:1,events:[{version:1,scheme:'advance',actor:'synthetic',created_at:'2026-10-01T00:00:00Z'}]},
 });
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 expect(await screen.findByText(/已確認先墊後退，正式補助退款尚未建立/)).toBeVisible();
});
it('正式補助退款只列一次並與一般客戶退款分開',async()=>{
 const subsidy={identity:'subsidy-return',obligation_type:'subsidy_return',label:'補助退款／工會代墊',
  party:'合成客戶',direction:'payable' as const,expected_ntd:12000,actual_ntd:0,has_payment:false,
  version:'v1',due_date:'2027-02-15',remaining_ntd:12000};
 vi.mocked(financeAccountingClient.query).mockResolvedValue({...facts(),scheme:'advance',
  client_items:[subsidy,{...subsidy,identity:'regular-return',obligation_type:'refund',label:'一般退款',expected_ntd:2000}],
  subsidy_payments:[{recipient:'client',party:subsidy.party,amount_ntd:12000,due_date:subsidy.due_date,source:'formal'}],
 });
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 const details=within(await screen.findByRole('region',{name:'補助退款與政府核銷明細，可左右捲動'}));
 expect(details.getAllByRole('row',{name:/補助款退還客戶/})).toHaveLength(1);
 const refund=within(details.getByRole('row',{name:/補助款退還客戶/}));
 expect(refund.getByText('2027-02-15')).toBeVisible();
 expect(refund.getByText('NT$ 12,000',{exact:true})).toBeVisible();
 expect(refund.getByText('待退 NT$ 12,000')).toBeVisible();
 expect(details.getByRole('row',{name:/客戶退款.*一般退款/})).toBeVisible();
 expect(screen.queryByRole('region',{name:'補助款預計給付'})).not.toBeInTheDocument();
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
beforeEach(()=>{vi.clearAllMocks();vi.mocked(differenceResolutionClient.staff).mockResolvedValue({case_no:caseNo,items:[],events:[]});vi.mocked(subsidyPeriodClient.caseCoverage).mockResolvedValue({case_no:caseNo,service_end_date:null,amount_ntd:12000,coverage:[]});vi.mocked(accountingPricingClient.queryCase).mockResolvedValue({case_no:caseNo,revision:0,source:'legacy',terms:{identity_name:'一般市民',rule:'citizen',subsidy_hours:40,client:{covered:300,excess:300},payroll:{covered:300,excess:300}},impact:{covered_hours:40,excess_hours:60,client_amount:30000,staff_covered_amount:12000,staff_excess_amount:18000,staff_total_amount:30000,subsidy_amount:12000,subsidy_return_amount:0}});vi.mocked(financeAccountingClient.previewSubsidyPlan).mockImplementation(async(caseNo,command)=>({case_no:caseNo,scheme:command.scheme,plan_version:command.expected_version,subsidy_ntd:12000,total_ntd:30000,confirmation_only:true,payables:[],blocker:null,preview_fingerprint:'b'.repeat(64)}));vi.mocked(financeAccountingClient.query).mockResolvedValue(facts());vi.mocked(ordersQueryClient.getOrderDetail).mockResolvedValue({case_no:caseNo,actual_start_date:'2026-10-01',actual_end_date:null} as never);vi.mocked(paymentOverdueReminderClient.case).mockResolvedValue(['deposit','first','second'].map(stage=>notice(stage as 'deposit'|'first'|'second')));vi.mocked(clientRegistryClient.query).mockResolvedValue({case_no:caseNo,client:{client_id:1,version:1,values:{name:'合成客戶',phone:'0912345678'}},beclass:{status:'ready',record_id:1,source_kind:'imported',version:1,values:{name:'報名客戶',phone:'0912345678',refund_bank_code:'8120012',refund_account_no:'****5678',refund_account_status:'complete'},field_capabilities:{}},finance:{status:'ready',code:null,values:{virtual_account:'99781699115701'}},order_terms:{status:'ready',code:null,data:null,field_capabilities:{}},order_information:{status:'ready',values:null,field_issues:{}}} as never);vi.mocked(caseVirtualAccountClient.query).mockResolvedValue({case_no:caseNo,imported_virtual_accounts:[],built_in_virtual_account:'99781699115701',mapping_ids:[]});vi.mocked(clientReceiptQueryClient.query).mockResolvedValue({case_no:caseNo,account_version:0,bank_facts:[],obligations:[]});});
describe('精簡案件抽屜',()=>{
 it.each([
  [null, 'NT$ 48,000'],
  [0, 'NT$ 0'],
  [42000, 'NT$ 42,000'],
 ] as const)('帳務總額為 %s 時直接顯示金額，缺應付明細時保留核銷狀態',async(accountingTotal,amount)=>{
  vi.mocked(financeAccountingClient.query).mockResolvedValue({
   ...facts(), staff_receivable_ntd:accountingTotal, staff_items:[], payable_ntd:null, paid_ntd:null,
  });
  const pricing = vi.spyOn(accountingPricingClient, 'queryCase').mockResolvedValueOnce({
   case_no:caseNo, revision:0, source:'legacy',
   terms:{identity_name:'一般市民',rule:'citizen',subsidy_hours:40,client:{covered:300,excess:300},payroll:{covered:300,excess:300}},
   impact:{covered_hours:40,excess_hours:120,client_amount:48000,staff_covered_amount:12000,
    staff_excess_amount:36000,staff_total_amount:48000,subsidy_amount:12000,subsidy_return_amount:0},
  });
  try {
   wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
   const summary=within(await screen.findByLabelText('案件精簡摘要'));
   expect(summary.getByText(amount,{exact:true})).toBeVisible();
   const staffSummary=within(screen.getByLabelText('月嫂薪資匯總'));
   expect(staffSummary.getByText('月嫂薪資金額',{exact:true})).toBeVisible();
   expect(staffSummary.getByText(amount,{exact:true})).toBeVisible();
   expect(staffSummary.getAllByText('待確認',{exact:true})).toHaveLength(2);
   expect(staffSummary.queryByText('已付齊')).not.toBeInTheDocument();
   expect(screen.getByText(/尚未建立月嫂應付明細/)).toBeVisible();
  } finally {
   pricing.mockRestore();
  }
 });
 it.each([null,0])('成立後未服務且正式月嫂總額為 %s 時，不以原登記計價回復薪資',async(accountingTotal)=>{
  vi.mocked(financeAccountingClient.query).mockResolvedValue({
   ...facts(),staff_receivable_ntd:accountingTotal,staff_items:[],payable_ntd:null,paid_ntd:null,
  });
  vi.mocked(ordersQueryClient.getOrderDetail).mockResolvedValue({
   case_no:caseNo,order_status:'成立後未服務',staff_id:null,service_days:5,service_hours_per_day:8,
  } as never);
  const pricing=vi.spyOn(accountingPricingClient,'queryCase').mockResolvedValueOnce({
   case_no:caseNo,revision:0,source:'legacy',
   terms:{identity_name:'一般市民',rule:'citizen',subsidy_hours:40,client:{covered:300,excess:300},payroll:{covered:300,excess:300}},
   impact:{covered_hours:40,excess_hours:0,client_amount:12000,staff_covered_amount:12000,
    staff_excess_amount:0,staff_total_amount:12000,subsidy_amount:12000,subsidy_return_amount:0},
  });
  try {
   wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
   const summary=within(await screen.findByLabelText('案件精簡摘要'));
   expect(summary.getByText('NT$ 0',{exact:true})).toBeVisible();
   expect(screen.getByLabelText('帳務計價依據與核心參數')).toHaveTextContent('月嫂基準應付 NT$ 0');
   const staffSummary=within(screen.getByLabelText('月嫂薪資匯總'));
   expect(staffSummary.getByText('NT$ 0',{exact:true})).toBeVisible();
   expect(staffSummary.getAllByText('待確認',{exact:true})).toHaveLength(2);
   expect(staffSummary.queryByText('不需出款',{exact:true})).not.toBeInTheDocument();

   expect(screen.getByText('尚未建立月嫂應付明細。原因、預計撥款日、已核銷與待出款金額待確認。')).toBeVisible();
   expect(screen.queryByText(/缺少計薪依據/)).not.toBeInTheDocument();
   expect(screen.queryByRole('button',{name:'更新帳務計算'})).not.toBeInTheDocument();
  } finally {
   pricing.mockRestore();
  }
 });
 it.each([null,1000])('成立後未服務仍保留正式月嫂應付明細與已核銷金額，總額 %s',async(accountingTotal)=>{
  vi.mocked(financeAccountingClient.query).mockResolvedValue({
   ...facts(),staff_receivable_ntd:accountingTotal,
   staff_items:[{...facts().staff_items[0],expected_ntd:1000,actual_ntd:200,remaining_ntd:800,has_payment:true}],
  });
  vi.mocked(ordersQueryClient.getOrderDetail).mockResolvedValue({case_no:caseNo,order_status:'成立後未服務'} as never);
  wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
  const summary=within(await screen.findByLabelText('案件精簡摘要'));
  expect(summary.getByText('NT$ 1,000',{exact:true})).toBeVisible();
  expect(screen.getByLabelText('帳務計價依據與核心參數')).toHaveTextContent('月嫂基準應付 NT$ 1,000');
  const staffSummary=within(screen.getByLabelText('月嫂薪資匯總'));
  expect(staffSummary.getByText('應付月嫂總額',{exact:true})).toBeVisible();
  expect(staffSummary.getByText('NT$ 1,000',{exact:true})).toBeVisible();
  expect(staffSummary.getByText('NT$ 200',{exact:true})).toBeVisible();
  expect(staffSummary.getByText('NT$ 800',{exact:true})).toBeVisible();
  const staffDetails=within(screen.getByRole('region',{name:'月嫂薪資與核銷明細，可左右捲動'}));
  expect(staffDetails.getByText('合成月嫂',{exact:true})).toBeVisible();
  expect(staffDetails.getByText('待付 NT$ 800',{exact:true})).toBeVisible();
  expect(screen.queryByText('本案成立後未服務，沒有月嫂應付明細。')).not.toBeInTheDocument();
 });
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
    expect(screen.getByRole('button',{name:'查看訂金通知'})).toBeEnabled();
    expect(screen.getByRole('button',{name:'查看第二期通知'})).toBeEnabled();
    expect(screen.getByRole('button',{name:'設定補助退款方案'})).toBeEnabled();
  });
 it('已繳齊仍可開啟同一期通知紀錄，不能再寄送',async()=>{
  const rows=[notice('deposit'),notice(),notice('second')];
  rows[0].history=[{task_id:9,requested_at:'2026-11-03T01:00:00Z',sent_at:'2026-11-03T02:30:00Z',status:'sent',content:'原訂金提醒',actor:'合成人員'}];
  vi.mocked(paymentOverdueReminderClient.case).mockResolvedValue(rows);
  wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
  fireEvent.click(await screen.findByRole('button',{name:'查看訂金通知'}));
  expect(screen.getByRole('region',{name:'本期繳款通知'})).toBeVisible();
  expect(screen.getByText('原訂金提醒')).toBeVisible();
  expect(screen.getByText('本期已繳齊')).toBeVisible();
  expect(screen.getByRole('button',{name:'發送通知'})).toBeDisabled();
  expect(paymentOverdueReminderClient.sendCase).not.toHaveBeenCalled();
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
  expect(screen.getByRole('button',{name:'查看第一期通知'})).toBeEnabled();
  fireEvent.click(screen.getByRole('button',{name:'查看第一期通知'}));
  expect(screen.getByText('本期通知來源待確認。')).toBeVisible();
  expect(screen.queryByRole('button',{name:'發送通知'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'返回案件'}));
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
  it('永豐待核對薪資可用原流水預覽同案取消結算的客戶退款',async()=>{
   const refundId='client-cancellation:create_refund:synthetic';
   const data=facts();
   data.client_items.push({...data.client_items[0],identity:refundId,direction:'payable',
    obligation_type:'refund',label:'取消結算退款',expected_ntd:2385,actual_ntd:0,remaining_ntd:2385});
   vi.mocked(financeAccountingClient.query).mockResolvedValue(data);
   const row:FinanceBankTransaction={row_id:7,row_identity:'finance-import-row:7',bank:'sinopac',direction:'outgoing',
    transaction_date:'2026-10-15',reference:'原流水 7',amount_ntd:2385,status:'pending',classification_type:'staff_salary',
    disposition:'business_pending',review_reason:null,available_actions:[],counterparty_name:null,cases:[caseNo],
    reconciliation_target:{case_no:caseNo,staff_id:12,obligation_identities:[],requires_selection:true}};
   vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({items:[row],pending_count:1,next_before_row_id:null});
   const refunds=vi.spyOn(clientSettlementRemediationClient,'query').mockResolvedValue({
    case_no:caseNo,account_version:1,as_of:'2026-10-15',receivable_obligations:[],
    refund_obligations:[{obligation_identity:refundId,
     obligation_type:'refund',amount_due_ntd:2385,due_date:'2026-10-15'}],subsidy_return_obligations:[],
    incoming_bank_facts:[],refund_bank_facts:[],subsidy_return_bank_facts:[],
   });
   const preview=vi.spyOn(financeImportCorrectionClient,'preview').mockRejectedValue(new Error('測試預覽'));
   try {
    wrapper(<FinanceCaseAccounting initialCase={caseNo} bankReconciliation={{row,onPosted:vi.fn(),onBusyChange:vi.fn()}}/>);
    fireEvent.click(await screen.findByRole('button',{name:'改核對客戶退款'}));
    fireEvent.click(screen.getByRole('button',{name:'查詢待核銷款項'}));
    fireEvent.click(await screen.findByRole('checkbox',{name:/客戶退款.*2,385/}));
    fireEvent.click(screen.getByRole('button',{name:'預覽核銷'}));
    await waitFor(()=>expect(preview).toHaveBeenCalledWith(expect.objectContaining({
     row_identity:row.row_identity,classification_type:'client_refund',target_obligation_identities:[refundId],
    })));
   } finally {
    refunds.mockRestore();
    preview.mockRestore();
   }
  });
   it.each([false,true])('在永豐核對頁預覽並確認實際服務日，完成後重查同一筆流水（歷史補登 %s）',async(historical)=>{
    const row:FinanceBankTransaction={row_id:7,row_identity:'finance-import-row:7',bank:'sinopac',direction:'outgoing',
     transaction_date:'2026-10-15',reference:'原流水 7',amount_ntd:2385,status:'pending',classification_type:'staff_salary',
     disposition:'business_pending',review_reason:null,available_actions:[],counterparty_name:null,cases:[caseNo],
     reconciliation_target:{case_no:caseNo,staff_id:12,obligation_identities:[],requires_selection:true}};
    let committed=false;
    const data=facts();
    data.staff_items=[{...data.staff_items[0],expected_ntd:2400,remaining_ntd:2400}];
    vi.mocked(financeAccountingClient.query).mockImplementation(async()=>committed ? data : {...data,staff_items:[]});
    vi.mocked(financeImportQueryClient.listBankTransactions).mockImplementation(async()=>({items:[committed ? {
     ...row,reconciliation_target:{...row.reconciliation_target!,obligation_identities:['staff']},
    } : row],pending_count:1,next_before_row_id:null}));
    const dates=[{service_date:'2026-10-10',staff_id:12,reason:null}];
    const factsBefore:OrderCancellationQuery={case_no:caseNo,lifecycle_status:historical?'訂單取消':'服務中',
     actual_start_date:historical?null:'2026-10-10',contracted_service_days:20,service_hours_per_day:8,
     service_started:!historical,historical_mid_service_confirmation_available:historical,service_data_locked:false,
     order_version:1,scheduling_version:1,scheduling_generation:1,client_finance_version:1,payroll_version:1,
     confirmed_service_days:dates,caregiver_options:[{staff_id:12,display_name:'合成月嫂'}]};
    const fingerprint='c'.repeat(64);
    const query=vi.spyOn(orderCancellationClient,'query').mockImplementation(async()=>committed ? {
     ...factsBefore,lifecycle_status:'訂單取消',historical_mid_service_confirmation_available:false,
     order_version:2,scheduling_version:2,client_finance_version:2,payroll_version:2,
    } : factsBefore);
    const preview=vi.spyOn(orderCancellationClient,'preview').mockResolvedValue({
     ...factsBefore,cancellation_date:'2026-10-11',actual_end_date:'2026-10-10',official_service_day_count:1,
     official_service_hours:8,scheduling:null,client_finance_impact:null,payroll_impact:null,
     historical_unserved_correction:null,
     lifecycle_impact:{case_no:caseNo,before_status:factsBefore.lifecycle_status,after_status:'訂單取消',
      actual_end_date:'2026-10-10',cancellation_effective:true,fingerprint},preview_fingerprint:fingerprint,
    });
    const apply=vi.spyOn(orderCancellationClient,'apply').mockImplementation(async()=>{
     committed=true;
     notifyCaseAccountingChanged(caseNo);
     return {case_no:caseNo,lifecycle_status:'訂單取消',order_version:2,scheduling_version:2,scheduling_generation:2,
      client_finance_version:2,payroll_version:2,actual_end_date:'2026-10-10',official_service_day_count:1,
      official_service_hours:8,cancelled_assignment_ids:[],created_assignment_keys:[],preview_fingerprint:fingerprint};
    });
    const onPosted=vi.fn();
    try {
     wrapper(<FinanceCaseAccounting initialCase={caseNo} bankReconciliation={{row,onPosted,onBusyChange:vi.fn()}}/>);
     fireEvent.click(await screen.findByRole('button',{name:'取消結算'}));
     expect(await screen.findByLabelText('取消實際服務日 1')).toHaveValue('2026-10-10');
     fireEvent.click(screen.getByRole('button',{name:'預覽取消帳務'}));
     const confirm=await screen.findByRole('button',{name:historical?'確認補登與結算':'確認取消'});
     expect(apply).not.toHaveBeenCalled();
     expect(preview).toHaveBeenCalledWith(caseNo,dates,expect.any(AbortSignal));
     fireEvent.click(confirm);
     expect(await screen.findByText('取消結算已完成，請核對原流水與最新款項。')).toBeVisible();
     expect(await screen.findByRole('checkbox',{name:'核銷款項 staff'})).toBeVisible();
     expect(financeImportQueryClient.listBankTransactions).toHaveBeenCalledTimes(2);
     expect(financeImportQueryClient.listBankTransactions).toHaveBeenLastCalledWith({transaction_status:'all',row_id:7},expect.anything());
     expect(onPosted).not.toHaveBeenCalled();
    } finally {
     query.mockRestore(); preview.mockRestore(); apply.mockRestore(); orderMutationFlowStore.clearAll();
    }
   });
   it.each(['client_refund','client_refund_return'])('銀行核對 %s 僅在退匯時顯示名冊退款戶名與帳號',async(classification)=>{
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
   const recipient = '名冊退款戶名：報名客戶 · 名冊退款帳號：000000009876';
   if (classification === 'client_refund_return') {
     expect(await screen.findByText(recipient)).toBeVisible();
   } else {
     expect(screen.queryByText(recipient)).not.toBeInTheDocument();
   }
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
describe('帳務核對之 E2E、黑箱、猴子與探索性測試', () => {
  it('台新退款流水從無待退款項到已有款項時，保留單一取消結算入口並切換可用操作', async () => {
    const refundObligationId = 'client-cancellation:refund:taishin';
    const row: FinanceBankTransaction = {
      row_id: 88,
      row_identity: 'finance-import-row:88',
      bank: 'taishin',
      direction: 'outgoing',
      transaction_date: '2026-11-15',
      reference: '台新退款 88',
      amount_ntd: 5000,
      status: 'pending',
      classification_type: 'client_refund',
      disposition: 'business_pending',
      review_reason: null,
      available_actions: [],
      counterparty_name: null,
      cases: [caseNo],
      reconciliation_target: {
        case_no: caseNo,
        staff_id: null,
        obligation_identities: [],
        requires_selection: true,
      },
    };

    let settled = false;
    const initialData = facts();
    initialData.client_items = initialData.client_items.filter(item => item.direction !== 'payable');
    const settledData = facts();
    settledData.client_items.push({
      identity: refundObligationId,
      direction: 'payable',
      obligation_type: 'refund',
      label: '取消結算服務天數退款',
      party: '合成客戶',
      expected_ntd: 5000,
      actual_ntd: 0,
      remaining_ntd: 5000,
      payment_stage: null,
      has_payment: false,
      version: '1',
      due_date: '2026-11-15',
    });

    vi.mocked(financeAccountingClient.query).mockImplementation(async () => settled ? settledData : initialData);
    vi.mocked(financeImportQueryClient.listBankTransactions).mockImplementation(async () => ({
      items: [settled ? {
        ...row,
        reconciliation_target: { ...row.reconciliation_target!, obligation_identities: [refundObligationId] },
      } : row],
      pending_count: 1,
      next_before_row_id: null,
    }));

    const dates = [{ service_date: '2026-10-10', staff_id: 12, reason: null }];
    const cancellationQuery: OrderCancellationQuery = {
      case_no: caseNo,
      lifecycle_status: '服務中',
      actual_start_date: '2026-10-10',
      contracted_service_days: 20,
      service_hours_per_day: 8,
      service_started: true,
      historical_mid_service_confirmation_available: false,
      service_data_locked: false,
      order_version: 1,
      scheduling_version: 1,
      scheduling_generation: 1,
      client_finance_version: 1,
      payroll_version: 1,
      confirmed_service_days: dates,
      caregiver_options: [{ staff_id: 12, display_name: '合成月嫂' }],
    };
    const fingerprint = 'e'.repeat(64);

    const querySpy = vi.spyOn(orderCancellationClient, 'query').mockImplementation(async () => settled ? {
      ...cancellationQuery,
      lifecycle_status: '訂單取消',
      order_version: 2,
      scheduling_version: 2,
      scheduling_generation: 2,
      client_finance_version: 2,
      payroll_version: 2,
    } : cancellationQuery);
    const previewSpy = vi.spyOn(orderCancellationClient, 'preview').mockResolvedValue({
      ...cancellationQuery,
      historical_unserved_correction: null,
      cancellation_date: '2026-10-11',
      actual_end_date: '2026-10-10',
      official_service_day_count: 1,
      official_service_hours: 8,
      scheduling: null,
      client_finance_impact: null,
      payroll_impact: null,
      lifecycle_impact: {
        case_no: caseNo,
        before_status: '服務中',
        after_status: '訂單取消',
        actual_end_date: '2026-10-10',
        cancellation_effective: true,
        fingerprint,
      },
      preview_fingerprint: fingerprint,
    });
    const applySpy = vi.spyOn(orderCancellationClient, 'apply').mockImplementation(async () => {
      settled = true;
      notifyCaseAccountingChanged(caseNo);
      return {
        case_no: caseNo,
        lifecycle_status: '訂單取消',
        order_version: 2,
        scheduling_version: 2,
        scheduling_generation: 2,
        client_finance_version: 2,
        payroll_version: 2,
        actual_end_date: '2026-10-10',
        official_service_day_count: 1,
        official_service_hours: 8,
        cancelled_assignment_ids: [],
        created_assignment_keys: [],
        preview_fingerprint: fingerprint,
      };
    });

    try {
      wrapper(<FinanceCaseAccounting initialCase={caseNo} bankReconciliation={{ row, onPosted: vi.fn(), onBusyChange: vi.fn() }} />);
      expect(await screen.findByText('本案目前沒有可選待退款項')).toBeVisible();
      expect(screen.getAllByRole('button', { name: /取消結算/ })).toHaveLength(1);
      expect(screen.getAllByRole('button', { name: /查看本案帳務/ })).toHaveLength(1);
      expect(screen.queryByText(/請點選「前往本案帳務」/)).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: '更正款項用途／重新歸屬' }));
      expect(screen.getByRole('combobox', { name: '款項用途' })).toHaveValue('client_refund');
      fireEvent.click(screen.getByRole('button', { name: '收合更正表單' }));
      expect(screen.queryByRole('combobox', { name: '款項用途' })).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: '查看本案帳務' }));
      expect(await screen.findByText('調整本案服務條件／計價')).toBeVisible();
      expect(screen.getByRole('button', { name: '手動補登款項' })).toBeVisible();
      fireEvent.click(screen.getByRole('button', { name: '返回對核交易' }));

      fireEvent.click(await screen.findByRole('button', { name: /取消結算/ }));
      expect(await screen.findByLabelText('取消實際服務日 1')).toHaveValue('2026-10-10');

      fireEvent.click(screen.getByRole('button', { name: '預覽取消帳務' }));
      const confirmBtn = await screen.findByRole('button', { name: '確認取消' });
      fireEvent.click(confirmBtn);

      expect(await screen.findByText('取消結算已完成，請核對原流水與最新款項。')).toBeVisible();
      const refundOption = await screen.findByRole('checkbox', { name: `核銷款項 ${refundObligationId}` });
      expect(refundOption).toBeEnabled();
      expect(screen.queryByText('本案目前沒有可選待退款項')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: '查看本案帳務' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: '更正款項用途／重新歸屬' })).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /取消結算/ }));
      fireEvent.click(await screen.findByRole('button', { name: '返回核對交易' }));
      const optionAfterReturn = await screen.findByRole('checkbox', { name: `核銷款項 ${refundObligationId}` });
      fireEvent.click(optionAfterReturn);
      expect(optionAfterReturn).toBeChecked();
      expect(screen.getByRole('heading', { name: '核銷處置與預覽確認' })).toBeVisible();
    } finally {
      querySpy.mockRestore();
      previewSpy.mockRestore();
      applySpy.mockRestore();
      orderMutationFlowStore.clearAll();
    }
  });

  it('核對交易時，服務條件折疊區及計價參數抽屜使用各自的入口', async () => {
    const row: FinanceBankTransaction = {
      row_id: 11,
      row_identity: 'finance-import-row:11',
      bank: 'sinopac',
      direction: 'incoming',
      transaction_date: '2026-11-15',
      reference: '永豐入帳 11',
      amount_ntd: 6000,
      status: 'pending',
      classification_type: 'client_receipt',
      disposition: 'business_pending',
      review_reason: null,
      available_actions: [],
      counterparty_name: null,
      cases: [caseNo],
      reconciliation_target: { case_no: caseNo, staff_id: null, obligation_identities: ['deposit'], requires_selection: false },
    };

    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [row],
      pending_count: 1,
      next_before_row_id: null,
    });

    wrapper(<FinanceCaseAccounting initialCase={caseNo} bankReconciliation={{ row, onPosted: vi.fn(), onBusyChange: vi.fn() }} />);
    const details = await screen.findByText('調整本案服務條件');
    fireEvent.click(details);

    expect(await screen.findByText('目前無法讀取正式服務條件，請重新查詢案件後再更正。')).toBeVisible();
    expect(screen.queryByText(/本案帳務計價參數（胎數、補助上限、時薪）已整合於下方/)).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: '更正本案計價參數' }));
    expect(screen.getByRole('dialog', { name: '調整本案帳務參數抽屜' })).toBeVisible();
  });

  it('猴子測試：快速隨機連點切換取消結算與核對視圖，無例外崩潰且狀態穩定', async () => {
    const row: FinanceBankTransaction = {
      row_id: 12,
      row_identity: 'finance-import-row:12',
      bank: 'taishin',
      direction: 'outgoing',
      transaction_date: '2026-11-15',
      reference: '台新出款 12',
      amount_ntd: 1000,
      status: 'pending',
      classification_type: 'client_refund',
      disposition: 'business_pending',
      review_reason: null,
      available_actions: [],
      counterparty_name: null,
      cases: [caseNo],
      reconciliation_target: { case_no: caseNo, staff_id: null, obligation_identities: [], requires_selection: true },
    };

    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [row],
      pending_count: 1,
      next_before_row_id: null,
    });

    const dates = [{ service_date: '2026-10-10', staff_id: 12, reason: null }];
    const cancellationQuery: OrderCancellationQuery = {
      case_no: caseNo,
      lifecycle_status: '服務中',
      actual_start_date: '2026-10-10',
      contracted_service_days: 20,
      service_hours_per_day: 8,
      service_started: true,
      historical_mid_service_confirmation_available: false,
      service_data_locked: false,
      order_version: 1,
      scheduling_version: 1,
      scheduling_generation: 1,
      client_finance_version: 1,
      payroll_version: 1,
      confirmed_service_days: dates,
      caregiver_options: [{ staff_id: 12, display_name: '合成月嫂' }],
    };

    const querySpy = vi.spyOn(orderCancellationClient, 'query').mockResolvedValue(cancellationQuery);

    try {
      wrapper(<FinanceCaseAccounting initialCase={caseNo} bankReconciliation={{ row, onPosted: vi.fn(), onBusyChange: vi.fn() }} />);
      for (let i = 0; i < 6; i++) {
        const openBtn = await screen.findByRole('button', { name: /取消結算（調整服務天數產生退款）/ });
        fireEvent.click(openBtn);
        const backBtn = await screen.findByRole('button', { name: '返回核對交易' });
        fireEvent.click(backBtn);
      }
      expect(await screen.findByRole('button', { name: /取消結算（調整服務天數產生退款）/ })).toBeEnabled();
    } finally {
      querySpy.mockRestore();
    }
  });

  it('探索性測試：取消結算預覽遇到網路 500 時，保留草稿狀態並顯示錯誤提示，可安全重試', async () => {
    const row: FinanceBankTransaction = {
      row_id: 13,
      row_identity: 'finance-import-row:13',
      bank: 'taishin',
      direction: 'outgoing',
      transaction_date: '2026-11-15',
      reference: '台新出款 13',
      amount_ntd: 3000,
      status: 'pending',
      classification_type: 'client_refund',
      disposition: 'business_pending',
      review_reason: null,
      available_actions: [],
      counterparty_name: null,
      cases: [caseNo],
      reconciliation_target: { case_no: caseNo, staff_id: null, obligation_identities: [], requires_selection: true },
    };

    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [row],
      pending_count: 1,
      next_before_row_id: null,
    });

    const dates = [{ service_date: '2026-10-10', staff_id: 12, reason: null }];
    const cancellationQuery: OrderCancellationQuery = {
      case_no: caseNo,
      lifecycle_status: '服務中',
      actual_start_date: '2026-10-10',
      contracted_service_days: 20,
      service_hours_per_day: 8,
      service_started: true,
      historical_mid_service_confirmation_available: false,
      service_data_locked: false,
      order_version: 1,
      scheduling_version: 1,
      scheduling_generation: 1,
      client_finance_version: 1,
      payroll_version: 1,
      confirmed_service_days: dates,
      caregiver_options: [{ staff_id: 12, display_name: '合成月嫂' }],
    };

    const querySpy = vi.spyOn(orderCancellationClient, 'query').mockResolvedValue(cancellationQuery);
    const previewSpy = vi.spyOn(orderCancellationClient, 'preview').mockRejectedValueOnce(new Error('網路連線逾時'));

    try {
      wrapper(<FinanceCaseAccounting initialCase={caseNo} bankReconciliation={{ row, onPosted: vi.fn(), onBusyChange: vi.fn() }} />);
      fireEvent.click(await screen.findByRole('button', { name: /取消結算（調整服務天數產生退款）/ }));
      expect(await screen.findByLabelText('取消實際服務日 1')).toHaveValue('2026-10-10');
      fireEvent.click(screen.getByRole('button', { name: '預覽取消帳務' }));

      expect(await screen.findByRole('alert')).toHaveTextContent('網路連線逾時');
      expect(screen.getByLabelText('取消實際服務日 1')).toHaveValue('2026-10-10');
      expect(screen.getByRole('button', { name: '預覽取消帳務' })).toBeEnabled();
    } finally {
      querySpy.mockRestore();
      previewSpy.mockRestore();
      orderMutationFlowStore.clearAll();
    }
  });

  it('E2E 與黑箱：永豐出款付月嫂無應付明細時，無死胡同引導、可查看本案帳務並返回、且可更正用途為客戶退款', async () => {
    const candidate = { case_no: caseNo, purpose: 'client_refund' as const, person_id: 5, person_name: '合成客戶' };
    const row = {
      row_id: 91,
      row_identity: 'finance-import-row:91',
      reference: '工作表1#91',
      bank: 'sinopac' as const,
      direction: 'outgoing' as const,
      amount_ntd: 37485,
      transaction_date: '2026-10-15',
      status: 'pending' as const,
      disposition: 'business_pending' as const,
      classification_type: 'staff_payout' as const,
      review_reason: null,
      available_actions: [],
      counterparty_name: null,
      cases: [caseNo],
      pairing_memo: 'HC115001',
      purpose_review: {
        classification_version: 1,
        candidates: [candidate],
      },
      reconciliation_target: {
        case_no: caseNo,
        staff_id: 12,
        obligation_identities: [],
        requires_selection: true,
      },
    };

    const pairSpy = vi.spyOn(financeImportQueryClient, 'pairBankTransaction').mockResolvedValue(91);
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [row],
      pending_count: 1,
      next_before_row_id: null,
    });
    const onPosted = vi.fn();
    const onBusyChange = vi.fn();

    try {
      wrapper(<FinanceCaseAccounting initialCase={caseNo} bankReconciliation={{ row, onPosted, onBusyChange }} />);
      expect(await screen.findByRole('button', { name: '更正出款用途' })).toBeVisible();
      expect(screen.getByText(/本案目前沒有可選款項/)).toBeVisible();
      expect(screen.getByRole('button', { name: '查看本案帳務' })).toBeVisible();

      // 黑箱：點擊查看本案帳務，切換至帳務檢視
      fireEvent.click(screen.getByRole('button', { name: '查看本案帳務' }));
      expect(await screen.findByText('調整本案服務條件／計價')).toBeVisible();
      expect(screen.getByRole('button', { name: '手動補登款項' })).toBeVisible();

      // 黑箱：點擊返回核對交易，返回對核視圖
      fireEvent.click(screen.getByRole('button', { name: '返回對核交易' }));
      expect(await screen.findByRole('button', { name: '更正出款用途' })).toBeVisible();

      // 黑箱：更正出款用途並切換客戶退款
      fireEvent.click(screen.getByRole('button', { name: '更正出款用途' }));
      const fieldset = screen.getByRole('region', { name: '更正出款用途' });
      expect(within(fieldset).getByText(/客戶退款/)).toBeVisible();

      const confirmBtn = within(fieldset).getByRole('button', { name: '確認用途' });
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(pairSpy).toHaveBeenCalledWith(91, candidate, 1);
        expect(onPosted).toHaveBeenCalled();
      });
    } finally {
      pairSpy.mockRestore();
    }
  });

  it('E2E 與黑箱異常處理：更正出款用途之取消收合與衝突錯誤提示', async () => {
    const candidate = { case_no: caseNo, purpose: 'client_refund' as const, person_id: 5, person_name: '合成客戶' };
    const row = {
      row_id: 92,
      row_identity: 'finance-import-row:92',
      reference: '工作表1#92',
      bank: 'sinopac' as const,
      direction: 'outgoing' as const,
      amount_ntd: 20000,
      transaction_date: '2026-10-15',
      status: 'pending' as const,
      disposition: 'business_pending' as const,
      classification_type: 'staff_payout' as const,
      review_reason: null,
      available_actions: [],
      counterparty_name: null,
      cases: [caseNo],
      purpose_review: {
        classification_version: 2,
        candidates: [candidate],
      },
      reconciliation_target: {
        case_no: caseNo,
        staff_id: 12,
        obligation_identities: [],
        requires_selection: true,
      },
    };

    const pairSpy = vi.spyOn(financeImportQueryClient, 'pairBankTransaction').mockRejectedValue(new Error('版本衝突：流水分類已被其他人員更新'));
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [row],
      pending_count: 1,
      next_before_row_id: null,
    });
    const onPosted = vi.fn();
    const onBusyChange = vi.fn();

    try {
      wrapper(<FinanceCaseAccounting initialCase={caseNo} bankReconciliation={{ row, onPosted, onBusyChange }} />);
      const correctBtn = await screen.findByRole('button', { name: '更正出款用途' });
      fireEvent.click(correctBtn);

      const fieldset = screen.getByRole('region', { name: '更正出款用途' });
      expect(within(fieldset).getByRole('button', { name: '取消' })).toBeVisible();

      // 測試取消收合
      fireEvent.click(within(fieldset).getByRole('button', { name: '取消' }));
      expect(screen.queryByRole('region', { name: '更正出款用途' })).not.toBeInTheDocument();

      // 再次開啟並觸發衝突錯誤
      fireEvent.click(screen.getByRole('button', { name: '更正出款用途' }));
      const fieldsetAgain = screen.getByRole('region', { name: '更正出款用途' });
      fireEvent.click(within(fieldsetAgain).getByRole('button', { name: '確認用途' }));

      expect(await within(fieldsetAgain).findByRole('alert')).toHaveTextContent('版本衝突：流水分類已被其他人員更新');
      expect(onPosted).not.toHaveBeenCalled();
    } finally {
      pairSpy.mockRestore();
    }
  });

  it('E2E 與黑箱：台新出款由客戶退款切換為月嫂薪資', async () => {
    const candidate = { case_no: caseNo, purpose: 'staff_salary' as const, person_id: 12, person_name: '合成月嫂' };
    const row = {
      row_id: 93,
      row_identity: 'finance-import-row:93',
      reference: '台新出款 93',
      bank: 'taishin' as const,
      direction: 'outgoing' as const,
      amount_ntd: 15000,
      transaction_date: '2026-10-15',
      status: 'pending' as const,
      disposition: 'business_pending' as const,
      classification_type: 'client_refund' as const,
      review_reason: null,
      available_actions: [],
      counterparty_name: null,
      cases: [caseNo],
      purpose_review: {
        classification_version: 1,
        candidates: [candidate],
      },
      reconciliation_target: {
        case_no: caseNo,
        staff_id: null,
        obligation_identities: [],
        requires_selection: true,
      },
    };

    const pairSpy = vi.spyOn(financeImportQueryClient, 'pairBankTransaction').mockResolvedValue(93);
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [row],
      pending_count: 1,
      next_before_row_id: null,
    });
    const onPosted = vi.fn();
    const onBusyChange = vi.fn();

    try {
      wrapper(<FinanceCaseAccounting initialCase={caseNo} bankReconciliation={{ row, onPosted, onBusyChange }} />);
      const correctBtn = await screen.findByRole('button', { name: '更正出款用途' });
      fireEvent.click(correctBtn);

      const fieldset = screen.getByRole('region', { name: '更正出款用途' });
      expect(within(fieldset).getByText(/月嫂薪資/)).toBeVisible();

      fireEvent.click(within(fieldset).getByRole('button', { name: '確認用途' }));

      await waitFor(() => {
        expect(pairSpy).toHaveBeenCalledWith(93, candidate, 1);
        expect(onPosted).toHaveBeenCalled();
      });
    } finally {
      pairSpy.mockRestore();
    }
  });

  it.each(['洽談中','訂單成立','歷史訂單－服務完成'])('狀態%s與主檔不能證明計薪缺項或重算資格',async status=>{
    vi.mocked(financeAccountingClient.query).mockResolvedValue({...facts(),staff_items:[],staff_receivable_ntd:null});
    vi.mocked(ordersQueryClient.getOrderDetail).mockResolvedValue({case_no:caseNo,order_status:status,staff_id:null,service_days:0,service_hours_per_day:0} as never);
    wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
    expect(await screen.findByText('尚未建立月嫂應付明細。原因、預計撥款日、已核銷與待出款金額待確認。')).toBeVisible();
    expect(screen.queryByText(/未指派服務人員|缺少計薪依據|本案具備計算條件/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button',{name:'更新帳務計算'})).not.toBeInTheDocument();
    expect(differenceResolutionClient.syncHistoricalBaseline).not.toHaveBeenCalled();
  });
});

it('逐期正式零額證據只免除指定一期，歷史缺漏不補零',async()=>{
 vi.mocked(financeAccountingClient.query).mockResolvedValue({...facts(),client_items:[],customer_amount_ntd:null,customer_fully_received:null,zero_stages:['deposit']});
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 const table=within(await screen.findByRole('region',{name:'各期繳款與通知，可左右捲動'}));
 const deposit=within(table.getByRole('row',{name:/訂金/}));
 expect(deposit.getByText('免繳')).toBeVisible();
 expect(deposit.getByText('NT$ 0',{exact:true})).toBeVisible();
 for(const name of [/第一期/,/第二期/]){const row=within(table.getByRole('row',{name}));expect(row.queryByText('免繳')).not.toBeInTheDocument();expect(row.queryByText('NT$ 0',{exact:true})).not.toBeInTheDocument();}
 expect(screen.queryByRole('button',{name:'發送通知'})).not.toBeInTheDocument();
});
it('有效全額補助且尚無應付不以主檔空指派誤判，保留人工確認階段',async()=>{
 vi.mocked(financeAccountingClient.query).mockResolvedValue({...facts(),scheme:'split',full_subsidy:true,zero_stages:['deposit','first','second'],subsidy_plan:plan,client_items:[],staff_items:[],customer_amount_ntd:0,customer_fully_received:true,ongoing_completed:false});
 vi.mocked(ordersQueryClient.getOrderDetail).mockResolvedValue({case_no:caseNo,staff_id:null,order_status:'歷史訂單－服務完成'} as never);
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 expect(await screen.findByText('全額補助，三期免繳')).toBeVisible();
 const periods=within(screen.getByRole('region',{name:'各期繳款與通知，可左右捲動'}));
 for(const name of [/訂金/,/第一期/,/第二期/]){const row=within(periods.getByRole('row',{name}));expect(row.getByText('免繳')).toBeVisible();expect(row.getByText('NT$ 0',{exact:true})).toBeVisible();}
 expect(within(screen.getByLabelText('月嫂薪資匯總')).getByText('NT$ 30,000',{exact:true})).toBeVisible();
 expect(screen.queryByRole('button',{name:'發送通知'})).not.toBeInTheDocument();
 expect(screen.queryByRole('row',{name:/補助款退還客戶/})).not.toBeInTheDocument();
 expect(differenceResolutionClient.syncHistoricalBaseline).not.toHaveBeenCalled();
 expect(screen.getByText(/尚未建立月嫂應付/)).toBeVisible();
 expect(screen.queryByText(/未指派服務人員|本案具備計算條件/)).not.toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'更新帳務計算'})).not.toBeInTheDocument();
 expect(financeAccountingClient.saveSubsidyPlan).not.toHaveBeenCalled();
});
it('同期多筆沿款項ID分列，保留到期日餘額與沖正',async()=>{
 const base=facts();const first=base.client_items.find(item=>item.payment_stage==='first')!;
 vi.mocked(financeAccountingClient.query).mockResolvedValue({...base,client_items:[{...first,identity:'first-a',due_date:'2026-10-10',remaining_ntd:1000},{...first,identity:'first-b',due_date:'2026-11-10',remaining_ntd:2000}],transactions:[{identity:'receipt-a',item_identity:'first-a',occurred_on:'2026-10-11',kind:'receipt',amount_ntd:3000,bank:'sinopac'},{identity:'reversal-a',item_identity:'first-a',occurred_on:'2026-10-12',kind:'reversal',amount_ntd:-1000,bank:'sinopac'}]});
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 const table=within(await screen.findByRole('region',{name:'各期繳款與通知，可左右捲動'}));
 const rows=table.getAllByRole('row',{name:/第一期/});expect(rows).toHaveLength(2);
 expect(within(rows[0]).getByText('2026-10-10')).toBeVisible();expect(within(rows[1]).getByText('2026-11-10')).toBeVisible();
 expect(within(rows[0]).getByText('待收 NT$ 1,000')).toBeVisible();expect(within(rows[1]).getByText('待收 NT$ 2,000')).toBeVisible();
 expect(within(rows[0]).getByText(/沖正.*1,000/)).toBeInTheDocument();expect(within(rows[1]).queryByText(/沖正.*1,000/)).not.toBeInTheDocument();
});
it('正式撥款日期缺值不推次月15日，分段保留各自日期',async()=>{
 const base=facts();vi.mocked(financeAccountingClient.query).mockResolvedValue({...base,staff_items:[{...base.staff_items[0],funding_portions:[{funding_kind:'client',amount_ntd:18000,settled_ntd:0,remaining_ntd:18000,due_date:'2026-11-01'},{funding_kind:'subsidy',amount_ntd:12000,settled_ntd:0,remaining_ntd:12000,due_date:null}]}]});
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 const table=await screen.findByRole('region',{name:'月嫂薪資與核銷明細，可左右捲動'});
 expect(table).not.toHaveTextContent('服務結束次月15日');expect(table).toHaveTextContent('日期待確認');expect(table).toHaveTextContent('2026-11-01');
});
it('退款正式日期缺值保留待確認，不以市府核撥代替',async()=>{
 vi.mocked(financeAccountingClient.query).mockResolvedValue({...facts(),client_items:[{identity:'refund-date',direction:'payable',label:'一般退款',party:'合成客戶',expected_ntd:1000,actual_ntd:0,remaining_ntd:1000,has_payment:false,version:'1',due_date:null,obligation_type:'refund'}]});
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 const row=await screen.findByRole('row',{name:/客戶退款.*一般退款/});expect(row).toHaveTextContent('日期待確認');expect(row).not.toHaveTextContent('市府核撥後退款');
});

it.each([false,true])('政府整期%s核銷狀態與銀行來自正式來源，不拆共享入款',async settled=>{
 vi.mocked(subsidyPeriodClient.caseCoverage).mockResolvedValue({case_no:caseNo,service_end_date:'2026-11-01',amount_ntd:12000,coverage:[{receipt_id:77,label:'115年11月',amount_ntd:50000,recorded_case_amount_ntd:12000,recorded_service_end_date:'2026-11-01',recovered_advance_ntd:0,settled}]});
 vi.mocked(financeAccountingClient.query).mockResolvedValue({...facts(),scheme:'split',cash_by_flow:null,bank_facts:[{identity:'whole',occurred_on:'2026-11-10',direction:'in',amount_ntd:5000,cases:[caseNo,'OTHER'],bank:'taishin',cash_flow:'G'}]});
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 const row=await screen.findByRole('row',{name:/政府補助款/});await waitFor(()=>expect(row).toHaveTextContent(settled?'已核銷':'已納入本期'));
 expect(row).toHaveTextContent('整期');expect(row).toHaveTextContent('台新');expect(row).not.toHaveTextContent('永豐');expect(row).not.toHaveTextContent(/已全額沖正|部分撥入沖正|實撥 NT\$ 5,000/);
});
it.each([false,true])('正式直付且衝突%s時，保留正確工會處理狀態',async conflict=>{
 vi.mocked(financeAccountingClient.query).mockResolvedValue({...facts(),scheme:'direct',scheme_conflict:conflict,arrangement:{case_no:caseNo,version:1,events:[{version:1,action:'confirm_direct',actor:'synthetic',created_at:'2026-11-01T00:00:00Z',reason:'正式確認'}]},bank_facts:conflict?[{identity:'gov',occurred_on:'2026-11-11',direction:'in',amount_ntd:5000,cases:[caseNo],bank:'taishin',cash_flow:'G'}]:[]});
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 const row=await screen.findByRole('row',{name:/政府補助款/});expect(row).toHaveTextContent(conflict?'衝突':'工會不經手');if(conflict)expect(row).not.toHaveTextContent('工會不經手');
});
it.each([null,0])('政府補助%s區分未知與不適用，不以缺來款補零',async subsidy=>{
 vi.mocked(financeAccountingClient.query).mockResolvedValue({...facts(),subsidy_ntd:subsidy,scheme:'unknown',cash_by_flow:null,bank_facts:[]});wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 const row=await screen.findByRole('row',{name:/政府補助款/});expect(row).toHaveTextContent(subsidy===null?'待確認':'不適用');expect(row).not.toHaveTextContent('實撥 NT$ 0');
});

it('正式零額款仍保留原到期日',async()=>{
 const base=facts();vi.mocked(financeAccountingClient.query).mockResolvedValue({...base,client_items:[{...base.client_items[0],expected_ntd:0,actual_ntd:0,remaining_ntd:0,due_date:'2026-10-15'}]});wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 const row=await screen.findByRole('row',{name:/訂金.*2026-10-15/});expect(row).toHaveTextContent('免繳');expect(row).toHaveTextContent('2026-10-15');
});

it('正常未付款只有待付，不以應付減已付顯示差額操作',async()=>{
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);const table=await screen.findByRole('region',{name:'月嫂薪資與核銷明細，可左右捲動'});
 expect(table).toHaveTextContent('待排程出款');expect(within(table).queryByRole('button',{name:'處置差額'})).not.toBeInTheDocument();
});
it.each([false,true])('正式追償來源可定位%s時才進既有核對入口',async located=>{
 vi.mocked(differenceResolutionClient.staff).mockResolvedValue({case_no:caseNo,items:[{identity:'recovery-1',staff_id:11,party:'合成月嫂',original_ntd:1000,remaining_ntd:1000,noncash_ntd:0,version:1,status:'待追償',related_cases:[caseNo],source_obligation_identities:located?['staff']:[],has_source_cash_evidence:located}],events:[]});
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 if(located){fireEvent.click(await screen.findByRole('button',{name:'核對追償'}));expect(screen.getByRole('region',{name:'月嫂追償核對'})).toHaveTextContent('recovery-1');}else{expect(await screen.findByText('差額待查')).toBeVisible();expect(screen.queryByRole('button',{name:'核對追償'})).not.toBeInTheDocument();}
 expect(differenceResolutionClient.apply).not.toHaveBeenCalled();
});
it('退款通知沒有可點擊但無handler的操作',async()=>{
 vi.mocked(financeAccountingClient.query).mockResolvedValue({...facts(),client_items:[{identity:'refund-no-notice',direction:'payable',label:'一般退款',party:'合成客戶',expected_ntd:1000,actual_ntd:0,remaining_ntd:1000,has_payment:false,version:'1',due_date:null,obligation_type:'refund'}]});
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);const row=await screen.findByRole('row',{name:/客戶退款.*一般退款/});expect(within(row).queryByRole('button',{name:'通知'})).not.toBeInTheDocument();
});
it.each(['zero','unknown','pending'] as const)('通知%s即使can_send true也不得放行',async mode=>{
 const source=notice('first');source.can_send=true;if(mode==='zero'&&source.payment)source.payment.remaining_amount_ntd=0;if(mode==='unknown')source.payment=null;if(mode==='pending')source.history=[{task_id:1,requested_at:'2026-11-01T00:00:00Z',sent_at:null,status:'pending',content:'通知',actor:'synthetic'},{task_id:2,requested_at:'2026-10-01T00:00:00Z',sent_at:'2026-10-01T00:01:00Z',status:'sent',content:'舊通知',actor:'synthetic'}];
 wrapper(<FinanceCaseNotice item={source} onBack={vi.fn()} onChanged={vi.fn()}/>);expect(screen.getByRole('button',{name:'發送通知'})).toBeDisabled();
});


describe('歷史原款項契約',()=>{
 it('免自備只顯示整案判定，不補三期、日期或月嫂應付',async()=>{
  vi.mocked(financeAccountingClient.query).mockResolvedValue({...facts(),historical_stages:true,
   full_subsidy_eligibility:true,full_subsidy:true,accounting_pending_reasons:[],scheme:'split',
   client_items:[],staff_items:[],transactions:[],customer_amount_ntd:0,customer_fully_received:null,
   receivable_ntd:null,received_ntd:null,remaining_in_ntd:null,payable_ntd:null,paid_ntd:null});
  vi.mocked(ordersQueryClient.getOrderDetail).mockResolvedValue({case_no:caseNo,order_status:'歷史訂單－服務完成'} as never);
  wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
  const periods=within(await screen.findByRole('region',{name:'各期繳款與通知，可左右捲動'}));
  expect(screen.getByText('全額補助／免自備，客戶應付 NT$ 0')).toBeVisible();
  expect(periods.getAllByRole('row')).toHaveLength(1);
  expect(periods.queryByText('不需繳納')).not.toBeInTheDocument();
  expect(screen.getByText('沒有原期款證據；免自備判定不代表原款已付或帳務結清。')).toBeVisible();
  expect(within(screen.getByLabelText('月嫂薪資匯總')).queryByText('NT$ 30,000',{exact:true})).not.toBeInTheDocument();
  expect(paymentOverdueReminderClient.sendCase).not.toHaveBeenCalled();
  expect(differenceResolutionClient.syncHistoricalBaseline).not.toHaveBeenCalled();
 });
 it('未分期、同期多筆及期別未知沿正式識別分列，原日期與餘額不互代',async()=>{
  const base=facts(), first=base.client_items[1];
  vi.mocked(financeAccountingClient.query).mockResolvedValue({...base,historical_stages:true,full_subsidy:false,
   client_items:[{...first,identity:'original-single',payment_stage:null,obligation_type:'adjustment',label:'原未分期款',due_date:'2025-01-19',expected_ntd:8000,actual_ntd:3000,remaining_ntd:5000,source_event_identity:'event-10'},
    {...first,identity:'first-a',due_date:'2025-02-03',remaining_ntd:1000,source_event_identity:'event-11'},
    {...first,identity:'first-b',due_date:'2025-03-08',remaining_ntd:2000,source_event_identity:'event-12'},
    {...first,identity:'unknown-period',payment_stage:null,obligation_type:'adjustment',label:'原帳期別待確認',due_date:null,remaining_ntd:3000,source_event_identity:'event-13'}],
   transactions:[{identity:'original-receipt',item_identity:'original-single',occurred_on:'2025-01-20',kind:'receipt',amount_ntd:4000,bank:'sinopac'},
    {identity:'original-reversal',item_identity:'original-single',occurred_on:'2025-01-21',kind:'reversal',amount_ntd:-1000,bank:'sinopac'}]});
  wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
  const table=within(await screen.findByRole('region',{name:'各期繳款與通知，可左右捲動'}));
  expect(table.getAllByRole('row')).toHaveLength(5);
  const single=table.getByRole('row',{name:/原未分期款/});
  expect(single).toHaveTextContent('2025-01-19');expect(single).toHaveTextContent('待收 NT$ 5,000');
  expect(single).toHaveTextContent('event-10');expect(single).toHaveTextContent('2025-01-20');expect(single).toHaveTextContent('2025-01-21');
  expect(single).toHaveTextContent('沖正');
  expect(table.getByRole('row',{name:/原帳期別待確認/})).toHaveTextContent('日期待確認');
  expect(table.getAllByRole('row',{name:/第一期/})).toHaveLength(2);
  expect(table.queryByRole('row',{name:/訂金/})).not.toBeInTheDocument();
  expect(table.queryByRole('row',{name:/第二期/})).not.toBeInTheDocument();
 });
 it('未分配收款保留日期金額來源，不配成三期期款或免繳',async()=>{
  vi.mocked(financeAccountingClient.query).mockResolvedValue({...facts(),historical_stages:true,full_subsidy:false,
   full_subsidy_eligibility:true,scheme_conflict:true,accounting_pending_reasons:['historical_client_cash_requires_review'],
   client_items:[],transactions:[{identity:'unallocated-receipt-2',item_identity:'unallocated',occurred_on:'2025-04-23',kind:'receipt',amount_ntd:4500,bank:'sinopac'}]});
  wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
  const receipts=within(await screen.findByRole('region',{name:'期別待確認的原收付款'}));
  expect(receipts.getByText(/2025-04-23/)).toBeVisible();expect(receipts.getByText(/4,500/)).toBeVisible();
  expect(receipts.getByText(/永豐/)).toBeVisible();
  expect(screen.queryByText('全額補助／免自備，客戶應付 NT$ 0')).not.toBeInTheDocument();
  expect(screen.getByText('原收付款與免自備判定不相容，請核對原帳。')).toBeVisible();
  expect(paymentOverdueReminderClient.sendCase).not.toHaveBeenCalled();
 });
 it('只有歷史付款證據不稱銀行入帳，未知資格不顯示免自備',async()=>{
  const original=facts().client_items[0];
  vi.mocked(financeAccountingClient.query).mockResolvedValue({...facts(),historical_stages:true,full_subsidy_eligibility:null,
   full_subsidy:false,accounting_pending_reasons:['historical_subsidy_limit_missing'],transactions:[],
   client_items:[{...original,identity:'legacy-marker',payment_evidence:'historical_paid',source_event_identity:'evidence-7'}]});
  wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
  const row=await screen.findByRole('row',{name:/legacy-marker/});
  expect(row).toHaveTextContent('歷史已付證據，非銀行入帳');
  expect(row).not.toHaveTextContent('尚無已核銷入帳');
  expect(screen.getByText('缺少本案有效補助上限，免自備資格待確認。')).toBeVisible();
  expect(screen.queryByText('全額補助／免自備，客戶應付 NT$ 0')).not.toBeInTheDocument();
 });
});


it('已知補助未選方案仍顯示，缺項原因由後端提供且未知金額不補零',async()=>{
 vi.mocked(financeAccountingClient.query).mockResolvedValue({...facts(),historical_stages:true,
  subsidy_ntd:null,subsidy_pending_reason:'rate_snapshot_missing',scheme:'unknown',subsidy_plan:plan,
  client_items:[],transactions:[]});
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 const government=await screen.findByRole('row',{name:/政府補助款/});
 expect(government).toHaveTextContent('缺少有效費率快照，政府補助金額待確認。');
 expect(government).not.toHaveTextContent('NT$ 0');
 expect(financeAccountingClient.saveSubsidyPlan).not.toHaveBeenCalled();
});
it('方案二未建立正式退款不列客戶待退金額或預估退款款項',async()=>{
 vi.mocked(financeAccountingClient.query).mockResolvedValue({...facts(),scheme:'advance',
  subsidy_plan:{case_no:caseNo,version:1,events:[{version:1,scheme:'advance',actor:'synthetic',created_at:'2026-10-01T00:00:00Z'}]},
  client_items:[],subsidy_payments:[{recipient:'client',party:'合成客戶',amount_ntd:12000,due_date:'2027-02-15',source:'estimate'}]});
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 const region=await screen.findByRole('region',{name:'補助退款與政府核銷明細，可左右捲動'});
 expect(region.closest('details')?.querySelector('.finance-refund-summary-bar')).toHaveTextContent('尚無正式退款');
 expect(within(region).queryByRole('row',{name:/補助款退還客戶/})).not.toBeInTheDocument();
});
it('已保存正式方案三才顯示工會不經手',async()=>{
 vi.mocked(financeAccountingClient.query).mockResolvedValue({...facts(),scheme:'direct',arrangement:null,
  subsidy_plan:{case_no:caseNo,version:1,events:[{version:1,scheme:'direct',actor:'synthetic',created_at:'2026-10-01T00:00:00Z'}]}});
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 expect(await screen.findByRole('row',{name:/政府補助款/})).toHaveTextContent('工會不經手');
});
it('多人中一位來源缺項仍保留他人正式應付與原日期',async()=>{
 const base=facts();
 vi.mocked(financeAccountingClient.query).mockResolvedValue({...base,historical_stages:true,
  staff_items:[{...base.staff_items[0],party:'已確認月嫂',due_date:'2026-11-03',remaining_ntd:30000}],
  staff_accounting_availability:[
   {assignment_id:1,staff_id:1,party:'已確認月嫂',obligation_identities:['staff'],status:'formal',pending_reasons:[],estimated_self_pay_date:null,estimated_subsidy_date:null},
   {assignment_id:2,staff_id:2,party:'缺項月嫂',obligation_identities:[],status:'needs_review',pending_reasons:['service_basis_missing'],estimated_self_pay_date:null,estimated_subsidy_date:null},
  ]});
 wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
 const source=within(await screen.findByRole('region',{name:'歷史月嫂應付依據'}));
 expect(source.getByText('缺項月嫂')).toBeVisible();expect(source.getByText('缺少歷史服務量依據。')).toBeVisible();
 const formal=within(screen.getByRole('region',{name:'月嫂薪資與核銷明細，可左右捲動'})).getByRole('row',{name:/已確認月嫂/});
 expect(formal).toHaveTextContent('2026-11-03');expect(formal).toHaveTextContent('NT$ 30,000');
 expect(differenceResolutionClient.syncHistoricalBaseline).not.toHaveBeenCalled();
});

it('歷史帳務 API 契約經 strict client 解碼後交抽屜呈現，拒絕未定義付款證據',async()=>{
 const {financeAccountingClient:actualClient}=await vi.importActual<typeof import('../../../../../../../api/finance_import/finance_accounting_client')>('../../../../../../../api/finance_import/finance_accounting_client');
 const raw={...facts(),historical_stages:true,full_subsidy_eligibility:null,accounting_pending_reasons:[],
  subsidy_pending_reason:'rate_snapshot_missing',client_items:[{...facts().client_items[0],identity:'contract-source',
   source_event_identity:'event-42',payment_evidence:'historical_paid',payment_date:'2025-11-06'}],transactions:[]};
 const token=vi.spyOn(sessionClient,'getToken').mockReturnValue('synthetic-contract-token');
 const request=vi.spyOn(transport,'get').mockResolvedValue({success:true,message:'ok',data:raw});
 try{
  const decoded=await actualClient.query(caseNo);
  vi.mocked(financeAccountingClient.query).mockResolvedValue(decoded);
  wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
  const row=await screen.findByRole('row',{name:/contract-source/});
  expect(row).toHaveTextContent('event-42');expect(row).toHaveTextContent('歷史付款證據日期 2025-11-06');
  expect(row).toHaveTextContent('歷史已付證據，非銀行入帳');
  request.mockResolvedValue({success:true,message:'ok',data:{...raw,client_items:[{...raw.client_items[0],payment_evidence:'paid'}]}});
  await expect(actualClient.query(caseNo)).rejects.toThrow(/payment_evidence/);
 }finally{request.mockRestore();token.mockRestore();}
});


const historicalContractPath=process.env.HISTORICAL_ACCOUNTING_CONTRACT_PATH;
it('兩入口保留待核對銀行與過期付款來源，不能視為沒有收付',async()=>{
 const data:CaseAccounting={...facts(),historical_stages:true,full_subsidy:false,full_subsidy_eligibility:true,
  scheme:'unknown',client_items:[],customer_amount_ntd:null,
  accounting_pending_reasons:['historical_client_bank_reconciliation_required','historical_client_payment_evidence_stale'],
  pending_bank_row_identities:['bank-row:original-1'],stale_payment_evidence_identities:['original:stale-payment']};
 vi.mocked(financeAccountingClient.query).mockResolvedValue(data);
 wrapper(<><FinanceCaseAccounting initialCase={caseNo} embedded/><ClientRegistryAccountingSummary caseNo={caseNo} revision={0}/></>);
 await waitFor(()=>expect(screen.getAllByRole('region',{name:'本案銀行收付款待核對'})).toHaveLength(2));
 for(const section of screen.getAllByRole('region',{name:'本案銀行收付款待核對'}))expect(section).toHaveTextContent('bank-row:original-1');
 for(const section of screen.getAllByRole('region',{name:'歷史付款證據待核對'}))expect(section).toHaveTextContent('original:stale-payment');
 expect(screen.queryByText('全額補助／免自備，客戶應付 NT$ 0')).not.toBeInTheDocument();
 expect(screen.queryByText('全額補助／免自備，客戶應付 0 元')).not.toBeInTheDocument();
});
it.skipIf(!historicalContractPath)('隔離 MySQL 帳務 API 原回應經 strict client 呈現歷史免自備、上限與舊帳衝突',async()=>{
 if(!historicalContractPath)throw new Error('缺少 HISTORICAL_ACCOUNTING_CONTRACT_PATH');
 const contracts=z.strictObject({main_case:z.unknown(),exact_cap:z.unknown(),conflict:z.unknown()}).parse(
  JSON.parse(readFileSync(historicalContractPath,'utf8')),
 );
 const actual=await vi.importActual<typeof import('../../../../../../../api/finance_import/finance_accounting_client')>(
  '../../../../../../../api/finance_import/finance_accounting_client',
 );
 const token=vi.spyOn(sessionClient,'getToken').mockReturnValue('synthetic-contract-session');
 const get=vi.spyOn(transport,'get');
 try{
  for(const [scenario,payload] of Object.entries(contracts)){
   const source=z.object({data:z.object({case_no:z.string()})}).parse(payload);
   const currentCase=source.data.case_no;
   get.mockResolvedValueOnce(payload);
   const decoded=await actual.financeAccountingClient.query(currentCase);
   vi.mocked(financeAccountingClient.query).mockResolvedValue(decoded);
   vi.mocked(ordersQueryClient.getOrderDetail).mockResolvedValue({case_no:currentCase,order_status:'歷史訂單－服務完成'} as never);
   const rendered=wrapper(<><FinanceCaseAccounting initialCase={currentCase} embedded/><ClientRegistryAccountingSummary caseNo={currentCase} revision={0}/></>);
   const table=within(await screen.findByRole('region',{name:'各期繳款與通知，可左右捲動'}));
   const incoming=decoded.client_items.filter(item=>item.direction==='receivable');
   expect(table.getAllByRole('row')).toHaveLength(incoming.length+1);
   const registry=within(screen.getByRole('region',{name:'補助及退款方案摘要（唯讀）'}));
   const customerAmount=await registry.findByText('客戶應付',{exact:true});
   expect(customerAmount.parentElement).toHaveTextContent(decoded.customer_amount_ntd==null?'待確認':`${decoded.customer_amount_ntd.toLocaleString('zh-TW')} 元`);
   for(const item of incoming){
    const original=registry.getByText(item.identity,{exact:true}).closest('tr');
    if(item.due_date)expect(original).toHaveTextContent(item.due_date);
    if(item.remaining_ntd!=null)expect(original).toHaveTextContent(`${item.remaining_ntd.toLocaleString('zh-TW')} 元`);
   }
   if(scenario==='conflict'){
    expect(decoded.scheme_conflict).toBe(true);
    expect(screen.queryByText('全額補助／免自備，客戶應付 NT$ 0')).not.toBeInTheDocument();
    for(const item of incoming){
     const original=table.getByText(item.identity,{exact:true});
     expect(original).toBeVisible();
     if(item.due_date)expect(original.closest('tr')).toHaveTextContent(item.due_date);
    }
   }else{
    expect(decoded.full_subsidy).toBe(true);
    expect(await screen.findByText('全額補助／免自備，客戶應付 NT$ 0')).toBeVisible();
    expect(table.queryByText('不需繳納')).not.toBeInTheDocument();
   }
   expect(paymentOverdueReminderClient.sendCase).not.toHaveBeenCalled();
   expect(differenceResolutionClient.syncHistoricalBaseline).not.toHaveBeenCalled();
   rendered.unmount();
  }
 }finally{get.mockRestore();token.mockRestore();}
});
