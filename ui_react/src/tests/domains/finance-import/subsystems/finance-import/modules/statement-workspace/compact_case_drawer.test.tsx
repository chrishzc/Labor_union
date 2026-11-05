import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {beforeEach,describe,expect,it,vi} from 'vitest';
import {FinanceCaseAccounting} from '../../../../../../../components/FinanceCaseAccounting';
import {FinanceCaseNotice} from '../../../../../../../components/FinanceCaseNotice';
import {FinanceSubsidyPlanForm} from '../../../../../../../components/FinanceSubsidyPlanForm';
import {UnsavedChangesProvider} from '../../../../../../../components/UnsavedChanges';
import {financeAccountingClient,type CaseAccounting} from '../../../../../../../api/finance_import/finance_accounting_client';
import {paymentOverdueReminderClient,type CasePaymentReminder} from '../../../../../../../api/line_order_groups/payment_overdue_reminder_client';
import {ordersQueryClient} from '../../../../../../../api/orders/order_query_client';
import {ApiHttpError} from '../../../../../../../api/shared/typed_errors';
vi.mock('../../../../../../../api/finance_import/finance_accounting_client',()=>({financeAccountingClient:{query:vi.fn(),saveSubsidyPlan:vi.fn(),subsidyPlan:vi.fn()}}));
vi.mock('../../../../../../../api/line_order_groups/payment_overdue_reminder_client',()=>({paymentOverdueReminderClient:{case:vi.fn(),sendCase:vi.fn()}}));
vi.mock('../../../../../../../api/orders/order_query_client',()=>({ordersQueryClient:{getOrderDetail:vi.fn()}}));
const caseNo='115000701';
const plan={case_no:caseNo,version:0,events:[]};
function facts():CaseAccounting{return {case_no:caseNo,client_name:'合成客戶',receivable_ntd:30000,received_ntd:20000,payable_ntd:30000,paid_ntd:0,pending_warning_count:0,staff_receivable_ntd:30000,subsidy_ntd:12000,customer_amount_ntd:30000,customer_fully_received:false,scheme:'direct',subsidy_plan:plan,ongoing_completed:false,collection_progress:{stage:'first',sources_complete:true,expected_ntd:15000,received_ntd:14000,remaining_ntd:1000,due_date:'2026-11-01'},client_items:([
 ['deposit',6000,6000,0],['first',15000,14000,1000],['second',9000,0,9000]
] as const).map(([stage,expected,actual,remaining])=>({identity:stage,direction:'receivable',label:stage,party:'合成客戶',expected_ntd:expected,actual_ntd:actual,remaining_ntd:remaining,payment_stage:stage,has_payment:actual>0,version:'1',due_date:stage==='second'?'2099-11-16':'2026-11-01'})),staff_items:[{identity:'staff',direction:'payable',label:'服務費',party:'合成月嫂',expected_ntd:30000,actual_ntd:0,has_payment:false,version:'1',due_date:null}],transactions:[{identity:'receipt',item_identity:'first',occurred_on:'2026-11-02',kind:'receipt',amount_ntd:14000,bank:'sinopac'}],warnings:[]};}
function notice(stage:'deposit'|'first'|'second'='first'):CasePaymentReminder{return {case_no:caseNo,payment_stage:stage,payment:{case_no:caseNo,payment_stage:stage,obligation_identity:stage,projection_version:1,obligation_event_id:1,due_date:'2099-11-16',remaining_amount_ntd:stage==='deposit'?0:1000},recipient_label:'合成客戶（私人LINE）',can_send:stage!=='deposit',unavailable_reason:stage==='deposit'?'本期已繳齊':null,message:'請繳納剩餘 1,000 元。',history:[]};}
function wrapper(ui:React.ReactNode){return render(<UnsavedChangesProvider>{ui}</UnsavedChangesProvider>);}
beforeEach(()=>{vi.clearAllMocks();vi.mocked(financeAccountingClient.query).mockResolvedValue(facts());vi.mocked(ordersQueryClient.getOrderDetail).mockResolvedValue({case_no:caseNo,actual_start_date:'2026-10-01',actual_end_date:null} as never);vi.mocked(paymentOverdueReminderClient.case).mockResolvedValue(['deposit','first','second'].map(stage=>notice(stage as 'deposit'|'first'|'second')));});
describe('精簡案件抽屜',()=>{
 it('只有兩個區塊與七欄；已核銷來源、缺日期、已齊鎖定及未到期通知照實呈現',async()=>{
  wrapper(<FinanceCaseAccounting initialCase={caseNo} embedded/>);
  const table=await screen.findByRole('table');
  expect(within(table).getAllByRole('columnheader').map(e=>e.textContent)).toEqual(['期款','原到期日','應繳','已收／待收','入帳資訊','通知時間','通知']);
  expect(document.querySelectorAll('details.finance-case-block')).toHaveLength(2);
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
  fireEvent.click(screen.getByRole('button',{name:'儲存方案'}));
  await waitFor(()=>expect(onChanged).toHaveBeenCalledOnce());
  expect(financeAccountingClient.saveSubsidyPlan).toHaveBeenCalledWith(caseNo,{scheme:'advance',expected_version:0},expect.any(String));
  await screen.findByRole('table');
  expect(financeAccountingClient.query).toHaveBeenCalledTimes(2);
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
  fireEvent.click(screen.getByRole('button',{name:'儲存方案'}));
  fireEvent.click(await screen.findByRole('button',{name:'重新讀取方案'}));
  await waitFor(()=>expect(financeAccountingClient.subsidyPlan).toHaveBeenCalledOnce());
  await waitFor(()=>expect(screen.getByRole('button',{name:'儲存方案'})).toBeEnabled());
  expect(screen.getByRole('radio',{name:/客戶與政府分別入款/})).toBeChecked();
  fireEvent.click(screen.getByRole('button',{name:'儲存方案'}));
  fireEvent.click(await screen.findByRole('button',{name:'確認原操作結果'}));
  await waitFor(()=>expect(onSaved).toHaveBeenCalledWith(saved));
  const calls=vi.mocked(financeAccountingClient.saveSubsidyPlan).mock.calls;
  expect(calls[1][1]).toEqual({scheme:'split',expected_version:1});expect(calls[2][2]).toBe(calls[1][2]);
 });
});
