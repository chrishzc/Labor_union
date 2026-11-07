import {cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {UnsavedChangesProvider} from '../../../../../../../components/UnsavedChanges';
import {SubsidyPeriodWorkbench} from '../../../../../../../components/SubsidyPeriodWorkbench';
import {subsidyPeriodClient,type SubsidyPeriod,type SubsidyPeriodView,type GovernmentManualInitialCommand} from '../../../../../../../api/government_subsidy/period_reconciliation_client';
import {sessionClient} from '../../../../../../../api/auth/session_client';
import {ApiHttpError,ApiDecodeError} from '../../../../../../../api/shared/typed_errors';
import {transport} from '../../../../../../../api/shared/transport';
import {governmentManualInitialStorageKey,readPendingGovernmentManualInitial} from '../../../../../../../api/government_subsidy/period_manual_initial_pending';
vi.mock('../../../../../../../api/government_subsidy/period_reconciliation_client',async importOriginal=>({...await importOriginal<typeof import('../../../../../../../api/government_subsidy/period_reconciliation_client')>(),subsidyPeriodClient:{query:vi.fn(),bankRows:vi.fn(),difference:vi.fn(),manualInitialReceipt:vi.fn()}}));
vi.mock('../../../../../../../api/auth/session_client',()=>({sessionClient:{fetchCurrentUser:vi.fn(),getUser:vi.fn(),getToken:vi.fn()}}));
function receiptFor(c:GovernmentManualInitialCommand){return {receipt_id:9,period:{unit:c.unit,year:c.year,index:c.index},amount_ntd:c.amount_ntd,paid_on:c.paid_on,source_label:'人工補登' as const,key:c.key};}
function view(period:SubsidyPeriod):SubsidyPeriodView{return {period,version:3,label:'測試期間',lines:[{case_no:'CASE-1',service_end_date:`${period.year}-01-20`,amount_ntd:6000,unavailable_reason:null}],total_ntd:6000,coverage:[],blocked_cases:[],recorded_lines:[],changed_cases:[],can_reconcile:true,balances:[],amount_controls:[{case_no:'CASE-1',mode:'automatic',computed_ntd:6000,effective_ntd:6000}],operations:[]};}
beforeEach(()=>{window.sessionStorage.clear();vi.mocked(sessionClient.fetchCurrentUser).mockResolvedValue({id:7} as Awaited<ReturnType<typeof sessionClient.fetchCurrentUser>>);vi.mocked(sessionClient.getUser).mockReturnValue({id:7} as ReturnType<typeof sessionClient.getUser>);vi.mocked(sessionClient.getToken).mockReturnValue('test-token');vi.mocked(subsidyPeriodClient.manualInitialReceipt).mockImplementation(async c=>({receipt_id:9,receipt:receiptFor(c),view:{...view(c),can_reconcile:false,coverage:[{receipt_id:9,period:c,label:'原期間',amount_ntd:c.amount_ntd,recovered_advance_ntd:0,settled:true,source_label:'人工補登'}]}}));vi.mocked(subsidyPeriodClient.query).mockImplementation(async p=>view(p));vi.mocked(subsidyPeriodClient.bankRows).mockResolvedValue([{id:1,paid_on:'2026-10-01',amount_ntd:5999},{id:2,paid_on:'2026-10-02',amount_ntd:6000},{id:3,paid_on:'2026-10-03',amount_ntd:6100}]);vi.mocked(subsidyPeriodClient.difference).mockImplementation(async c=>view(c));});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.resetAllMocks();window.sessionStorage.clear();});
async function loaded(){await screen.findByText('本期目前計算應收',{exact:false});}
function chooseBank(id='2'){fireEvent.change(screen.getByLabelText('已匯入銀行對帳單的政府款項'),{target:{value:id}});}
function confirm(){fireEvent.click(screen.getByRole('checkbox',{name:'我已核對款項、金額與處理方式'}));}
describe('whole-period differences',()=>{
 it('states the imported bank source and requires human confirmation of exact cash',async()=>{render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();expect(screen.getByText(/來源是銀行對帳單匯入/)).toBeVisible();chooseBank();const button=screen.getByRole('button',{name:'核銷本期入款'});expect(button).toBeDisabled();confirm();fireEvent.click(button);await waitFor(()=>expect(subsidyPeriodClient.difference).toHaveBeenCalledOnce());expect(vi.mocked(subsidyPeriodClient.difference).mock.calls[0][0]).toMatchObject({action:'initial_receipt',bank_row_id:2,handling:'exact',expected_version:3});});
 it('requires an explicit partial choice and keeps the remaining shortfall for follow-up',async()=>{render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();chooseBank('1');const choice=screen.getByLabelText('本次少撥的下一步');expect(choice).toHaveValue('');confirm();expect(screen.getByRole('button',{name:'確認記錄本次處理'})).toBeDisabled();fireEvent.change(choice,{target:{value:'partial'}});confirm();fireEvent.click(screen.getByRole('button',{name:'確認記錄本次處理'}));await waitFor(()=>expect(subsidyPeriodClient.difference).toHaveBeenCalledOnce());expect(vi.mocked(subsidyPeriodClient.difference).mock.calls[0][0]).toMatchObject({action:'initial_receipt',bank_row_id:1,handling:'partial'});});
 it('requires the excess to be carried as a pending refund without an automatic surplus option',async()=>{render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();chooseBank('3');const choice=screen.getByLabelText('本次多撥的下一步');expect(choice).toHaveValue('');expect(within(choice).queryByRole('option',{name:/盈餘/})).toBeNull();fireEvent.change(choice,{target:{value:'refund_excess'}});confirm();fireEvent.click(screen.getByRole('button',{name:'確認記錄本次處理'}));await waitFor(()=>expect(subsidyPeriodClient.difference).toHaveBeenCalledOnce());expect(vi.mocked(subsidyPeriodClient.difference).mock.calls[0][0].handling).toBe('refund_excess');});
 it('shows included cases and original balance before the period has settled',async()=>{vi.mocked(subsidyPeriodClient.query).mockImplementation(async p=>({...view(p),can_reconcile:false,coverage:[{receipt_id:9,period:p,label:'原期間',amount_ntd:5900,recovered_advance_ntd:0,settled:false}],recorded_lines:view(p).lines,balances:[{identity:'period:9',root_receipt_id:9,kind:'original',case_no:null,direction:'receivable',expected_ntd:6000,received_ntd:5900,recognized_ntd:0,returned_ntd:0,remaining_ntd:100,refund_due_ntd:0,settled:false,status:'待補撥'}]}));render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await screen.findByText('已納入本期，差額尚待處理');expect(screen.queryByText(/涵蓋/)).toBeNull();expect(screen.queryByRole('button',{name:'核銷本期入款'})).toBeNull();fireEvent.change(screen.getByLabelText('款項'),{target:{value:'period:9'}});const action=screen.getByLabelText('處理方式');expect(action).toHaveValue('');fireEvent.change(action,{target:{value:'loss'}});expect(screen.getByLabelText('本次作損失處理金額')).toBeVisible();});
 it('keeps the original command after an unknown result and prevents changing its scope',async()=>{vi.mocked(subsidyPeriodClient.difference).mockRejectedValueOnce(new Error('timeout'));render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();chooseBank();confirm();fireEvent.click(screen.getByRole('button',{name:'核銷本期入款'}));const retry=await screen.findByRole('button',{name:'查回原次處理結果'});expect(screen.getByLabelText('彙總單位')).toBeDisabled();fireEvent.click(retry);await waitFor(()=>expect(subsidyPeriodClient.difference).toHaveBeenCalledTimes(2));const calls=vi.mocked(subsidyPeriodClient.difference).mock.calls;expect(calls[0]).toEqual(calls[1]);});
 it('blocks incomplete calculations and incomplete years without inventing a mismatch',async()=>{vi.mocked(subsidyPeriodClient.query).mockImplementation(async p=>({...view(p),total_ntd:null,can_reconcile:false,lines:[{...view(p).lines[0],amount_ntd:null,unavailable_reason:'scheduling_effective_generation_invalid'}]}));render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();expect(screen.getByText('排班資料待確認')).toBeVisible();chooseBank();confirm();expect(screen.getByRole('button',{name:'確認記錄本次處理'})).toBeDisabled();expect(screen.queryByLabelText('本次多撥的下一步')).toBeNull();fireEvent.change(screen.getByLabelText('年度'),{target:{value:'203'}});expect(screen.getByLabelText('年度')).toHaveValue(203);expect(subsidyPeriodClient.difference).not.toHaveBeenCalled();});
 it('shows latest computation and restores automatic mode only after selection',async()=>{render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();fireEvent.change(screen.getByLabelText('處理範圍'),{target:{value:'correction'}});const choice=screen.getByLabelText('處理方式');expect(choice).toHaveValue('');fireEvent.change(choice,{target:{value:'adopt_calculation'}});fireEvent.change(screen.getByLabelText('處理依據／更正原因'),{target:{value:'核對新計算'}});confirm();fireEvent.click(screen.getByRole('button',{name:'確認更新系統金額'}));await waitFor(()=>expect(subsidyPeriodClient.difference).toHaveBeenCalledOnce());expect(vi.mocked(subsidyPeriodClient.difference).mock.calls[0][0]).toMatchObject({identity:'CASE-1',action:'adopt_calculation',amount_ntd:null});});
 it('saves the original selection before navigating to a newly typed complete year',async()=>{render(<UnsavedChangesProvider><SubsidyPeriodWorkbench onOpenCase={()=>{}}/></UnsavedChangesProvider>);await loaded();const originalYear=new Date().getFullYear();chooseBank();confirm();fireEvent.change(screen.getByLabelText('年度'),{target:{value:'203'}});fireEvent.change(screen.getByLabelText('年度'),{target:{value:'2031'}});const dialog=await screen.findByRole('dialog');fireEvent.click(within(dialog).getByRole('button',{name:'儲存變更並離開'}));await waitFor(()=>expect(vi.mocked(subsidyPeriodClient.query).mock.lastCall?.[0].year).toBe(2031));expect(vi.mocked(subsidyPeriodClient.difference).mock.calls[0][0].year).toBe(originalYear);});
});

function chooseManual(amount='6000',paidOn='2026-10-15'){
 fireEvent.change(screen.getByLabelText('首次實收來源'),{target:{value:'manual'}});
 fireEvent.change(screen.getByLabelText('首次政府實收金額'),{target:{value:amount}});
 fireEvent.change(screen.getByLabelText('實際收款日期'),{target:{value:paidOn}});
}
describe('first government actual receipt',()=>{
 it('requires explicit amount/date, journals the fresh actor before posting, and needs no checkbox or preview',async()=>{
  render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();
  fireEvent.change(screen.getByLabelText('首次實收來源'),{target:{value:'manual'}});
  const submit=screen.getByRole('button',{name:'補登首次政府實收'});
  expect(screen.getByLabelText('首次政府實收金額')).toHaveValue(null);expect(screen.getByLabelText('實際收款日期')).toHaveValue('');expect(submit).toBeDisabled();
  expect(screen.queryByRole('checkbox')).toBeNull();expect(screen.queryByRole('button',{name:/預覽/})).toBeNull();expect(screen.queryByLabelText('已匯入銀行對帳單的政府款項')).toBeNull();
  fireEvent.change(screen.getByLabelText('首次政府實收金額'),{target:{value:'6000'}});expect(submit).toBeDisabled();
  fireEvent.change(screen.getByLabelText('實際收款日期'),{target:{value:'2026-10-15'}});
  vi.mocked(subsidyPeriodClient.manualInitialReceipt).mockImplementationOnce(async command=>{
   expect(sessionClient.fetchCurrentUser).toHaveBeenCalledOnce();
   expect(readPendingGovernmentManualInitial()).toEqual({version:1,actorId:7,command});
   expect(Object.keys(command).sort()).toEqual(['amount_ntd','expected_version','handling','index','key','paid_on','reason','unit','year']);
   return {receipt_id:9,receipt:receiptFor(command),view:{...view(command),coverage:[{receipt_id:9,period:command,label:'原期間',amount_ntd:6000,recovered_advance_ntd:0,source_label:'人工補登'}],can_reconcile:false}};
  });
  fireEvent.click(submit);await screen.findByText('已補登首次政府實收。後續補撥與退款請沿原整期款項處理。');
  expect(vi.mocked(subsidyPeriodClient.manualInitialReceipt).mock.calls[0][0]).toMatchObject({amount_ntd:6000,paid_on:'2026-10-15',handling:'exact',reason:'',expected_version:3});
  expect(screen.getByRole('status')).toHaveTextContent('2026-10-15 · 人工補登');expect(subsidyPeriodClient.difference).not.toHaveBeenCalled();expect(readPendingGovernmentManualInitial()).toBeNull();expect(screen.getByText(/首筆實收 NT\$ 6,000 · 人工補登/)).toBeVisible();
 });
 it.each([{amount:'5900',label:'本次少撥的下一步',handling:'partial'},{amount:'6100',label:'本次多撥的下一步',handling:'refund_excess'}])('requires explicit $handling intent and clears it when the amount changes',async({amount,label,handling})=>{
  render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();chooseManual(amount);
  const button=screen.getByRole('button',{name:'補登首次政府實收'}),choice=screen.getByLabelText(label);
  expect(choice).toHaveValue('');expect(button).toBeDisabled();expect(within(choice).queryByRole('option',{name:/盈餘/})).toBeNull();
  fireEvent.change(choice,{target:{value:handling}});expect(button).toBeEnabled();
  fireEvent.change(screen.getByLabelText('首次政府實收金額'),{target:{value:String(Number(amount)+1)}});expect(choice).toHaveValue('');expect(button).toBeDisabled();
  fireEvent.change(choice,{target:{value:handling}});fireEvent.click(button);
  await waitFor(()=>expect(subsidyPeriodClient.manualInitialReceipt).toHaveBeenCalledOnce());expect(vi.mocked(subsidyPeriodClient.manualInitialReceipt).mock.calls[0][0].handling).toBe(handling);
 });
 it('keeps the explicitly selected period independent of the payment date',async()=>{
  render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();const selected=vi.mocked(subsidyPeriodClient.query).mock.lastCall![0];chooseManual('6000','2020-02-29');
  fireEvent.click(screen.getByRole('button',{name:'補登首次政府實收'}));await waitFor(()=>expect(subsidyPeriodClient.manualInitialReceipt).toHaveBeenCalledOnce());
  expect(vi.mocked(subsidyPeriodClient.manualInitialReceipt).mock.calls[0][0]).toMatchObject({...selected,paid_on:'2020-02-29'});
 });
 it('restores an unresolved command after remount, including its original period/version/key even when now settled',async()=>{
  vi.mocked(subsidyPeriodClient.manualInitialReceipt).mockRejectedValueOnce(new ApiHttpError(503,'subsidy_period_unavailable','unavailable'));
  const first=render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();
  fireEvent.change(screen.getByLabelText('彙總單位'),{target:{value:'month'}});fireEvent.change(screen.getByLabelText('年度'),{target:{value:'2025'}});await waitFor(()=>expect(vi.mocked(subsidyPeriodClient.query).mock.lastCall![0]).toMatchObject({unit:'month',year:2025}));await loaded();chooseManual();
  fireEvent.click(screen.getByRole('button',{name:'補登首次政府實收'}));await screen.findByRole('button',{name:'查回原次處理結果'});await waitFor(()=>expect(screen.getByRole('button',{name:'查回原次處理結果'})).toBeEnabled());
  const original=vi.mocked(subsidyPeriodClient.manualInitialReceipt).mock.calls[0][0];first.unmount();
  vi.mocked(subsidyPeriodClient.query).mockImplementation(async p=>({...view(p),version:99,can_reconcile:false,coverage:[{receipt_id:9,period:p,label:'原期間',amount_ntd:6000,recovered_advance_ntd:0,settled:true,source_label:'人工補登'}]}));
  render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);
  await waitFor(()=>expect(screen.getByRole('button',{name:'查回原次處理結果'})).toBeEnabled());
  expect(screen.getByLabelText('彙總單位')).toHaveValue('month');expect(screen.getByLabelText('年度')).toHaveValue(2025);expect(screen.getByLabelText('年度')).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'查回原次處理結果'}));await waitFor(()=>expect(subsidyPeriodClient.manualInitialReceipt).toHaveBeenCalledTimes(2));
  expect(vi.mocked(subsidyPeriodClient.manualInitialReceipt).mock.calls[1][0]).toEqual(original);
 });
 it('can query the preserved command when the current period query is unavailable',async()=>{
  vi.mocked(subsidyPeriodClient.manualInitialReceipt).mockRejectedValueOnce(new Error('timeout'));
  const first=render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();chooseManual();fireEvent.click(screen.getByRole('button',{name:'補登首次政府實收'}));await waitFor(()=>expect(screen.getByRole('button',{name:'查回原次處理結果'})).toBeEnabled());first.unmount();
  vi.mocked(subsidyPeriodClient.query).mockRejectedValue(new Error('read unavailable'));
  render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await screen.findByText('補助資料暫時無法取得，請重新查詢。');await waitFor(()=>expect(screen.getByRole('button',{name:'查回原次處理結果'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'查回原次處理結果'}));await waitFor(()=>expect(subsidyPeriodClient.manualInitialReceipt).toHaveBeenCalledTimes(2));
  expect(vi.mocked(subsidyPeriodClient.manualInitialReceipt).mock.calls[1]).toEqual(vi.mocked(subsidyPeriodClient.manualInitialReceipt).mock.calls[0]);
 });
 it('clears a restored command only after actual-client validation of its original receipt, even after reversal',async()=>{
  const command:GovernmentManualInitialCommand={unit:'year',year:2025,index:1,amount_ntd:6000,paid_on:'2026-01-01',handling:'exact',reason:'',expected_version:3,key:'original-reversed-key'};
  window.sessionStorage.setItem(governmentManualInitialStorageKey,JSON.stringify({version:1,actorId:7,command}));
  const actual=await vi.importActual<typeof import('../../../../../../../api/government_subsidy/period_reconciliation_client')>('../../../../../../../api/government_subsidy/period_reconciliation_client');
  vi.mocked(subsidyPeriodClient.manualInitialReceipt).mockImplementation(actual.subsidyPeriodClient.manualInitialReceipt);
  const current={...view({unit:command.unit,year:command.year,index:command.index}),version:99,can_reconcile:false,coverage:[]};
  vi.spyOn(transport,'post').mockResolvedValue({data:{receipt_id:9,receipt:receiptFor(command),view:current}});
  render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await waitFor(()=>expect(screen.getByRole('button',{name:'查回原次處理結果'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'查回原次處理結果'}));await screen.findByText('已補登首次政府實收。後續補撥與退款請沿原整期款項處理。');
  expect(readPendingGovernmentManualInitial()).toBeNull();expect(vi.mocked(subsidyPeriodClient.manualInitialReceipt).mock.calls[0][0]).toEqual(command);expect(screen.getByLabelText('年度')).toHaveValue(2025);
 });
 it('never abandons an unknown result because a later retry is denied',async()=>{
  vi.mocked(subsidyPeriodClient.manualInitialReceipt).mockRejectedValueOnce(new Error('timeout')).mockRejectedValueOnce(new ApiHttpError(403,'forbidden','denied'));
  render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();chooseManual();fireEvent.click(screen.getByRole('button',{name:'補登首次政府實收'}));await waitFor(()=>expect(screen.getByRole('button',{name:'查回原次處理結果'})).toBeEnabled());
  const stored=readPendingGovernmentManualInitial();fireEvent.click(screen.getByRole('button',{name:'查回原次處理結果'}));await waitFor(()=>expect(subsidyPeriodClient.manualInitialReceipt).toHaveBeenCalledTimes(2));await waitFor(()=>expect(screen.getByRole('button',{name:'查回原次處理結果'})).toBeEnabled());
  expect(readPendingGovernmentManualInitial()).toEqual(stored);expect(screen.getByLabelText('年度')).toBeDisabled();
 });
 it('retains the same command after an unbound response cannot establish the original result',async()=>{
  vi.mocked(subsidyPeriodClient.manualInitialReceipt).mockRejectedValueOnce(new ApiDecodeError('wrong period'));
  render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();chooseManual();fireEvent.click(screen.getByRole('button',{name:'補登首次政府實收'}));await waitFor(()=>expect(screen.getByRole('button',{name:'查回原次處理結果'})).toBeEnabled());
  const stored=readPendingGovernmentManualInitial();expect(stored?.command).toEqual(vi.mocked(subsidyPeriodClient.manualInitialReceipt).mock.calls[0][0]);expect(screen.getByLabelText('年度')).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'查回原次處理結果'}));await waitFor(()=>expect(subsidyPeriodClient.manualInitialReceipt).toHaveBeenCalledTimes(2));expect(vi.mocked(subsidyPeriodClient.manualInitialReceipt).mock.calls[1][0]).toEqual(stored?.command);
 });
 it('does not POST an amount the browser cannot represent exactly',async()=>{
  render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();chooseManual('9007199254740993');
  expect(screen.getByText('瀏覽器無法準確處理此金額，請核對原資料；本次不會送出。')).toBeVisible();expect(screen.getByRole('button',{name:'補登首次政府實收'})).toBeDisabled();expect(subsidyPeriodClient.manualInitialReceipt).not.toHaveBeenCalled();expect(readPendingGovernmentManualInitial()).toBeNull();
 });
 it.each(['receipt','view'])('retains its exact journal when the actual client rejects unsafe %s output',async part=>{
  const actual=await vi.importActual<typeof import('../../../../../../../api/government_subsidy/period_reconciliation_client')>('../../../../../../../api/government_subsidy/period_reconciliation_client');
  vi.mocked(subsidyPeriodClient.manualInitialReceipt).mockImplementation(actual.subsidyPeriodClient.manualInitialReceipt);
  vi.spyOn(transport,'post').mockImplementation(async(_url,body)=>{
   const command=body as GovernmentManualInitialCommand,receipt=receiptFor(command),current=view({unit:command.unit,year:command.year,index:command.index});
   if(part==='receipt')receipt.amount_ntd=9007199254740992;else current.total_ntd=9007199254740992;
   return {data:{receipt_id:9,receipt,view:current}};
  });
  render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();chooseManual();fireEvent.click(screen.getByRole('button',{name:'補登首次政府實收'}));await waitFor(()=>expect(screen.getByRole('button',{name:'查回原次處理結果'})).toBeEnabled());
  expect(readPendingGovernmentManualInitial()?.command).toEqual(vi.mocked(subsidyPeriodClient.manualInitialReceipt).mock.calls[0][0]);expect(screen.queryByText('已補登首次政府實收。後續補撥與退款請沿原整期款項處理。')).toBeNull();expect(screen.getByLabelText('年度')).toBeDisabled();
 });
 it('keeps an initial typed conflict editable only after clearing its rejected journal',async()=>{
  vi.mocked(subsidyPeriodClient.manualInitialReceipt).mockRejectedValueOnce(new ApiHttpError(409,'subsidy_period_stale','請重新查詢期間'));
  render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();chooseManual();fireEvent.click(screen.getByRole('button',{name:'補登首次政府實收'}));await screen.findByText('請重新查詢期間');
  expect(readPendingGovernmentManualInitial()).toBeNull();expect(screen.queryByRole('button',{name:'查回原次處理結果'})).toBeNull();expect(screen.getByLabelText('年度')).toBeEnabled();
 });
 it('does not post if the authenticated actor changes before retry',async()=>{
  vi.mocked(subsidyPeriodClient.manualInitialReceipt).mockRejectedValueOnce(new Error('timeout'));
  render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();chooseManual();fireEvent.click(screen.getByRole('button',{name:'補登首次政府實收'}));await waitFor(()=>expect(screen.getByRole('button',{name:'查回原次處理結果'})).toBeEnabled());
  const stored=readPendingGovernmentManualInitial();vi.mocked(sessionClient.fetchCurrentUser).mockResolvedValue({id:8} as Awaited<ReturnType<typeof sessionClient.fetchCurrentUser>>);vi.mocked(sessionClient.getUser).mockReturnValue({id:8} as ReturnType<typeof sessionClient.getUser>);
  fireEvent.click(screen.getByRole('button',{name:'查回原次處理結果'}));await screen.findByText('有另一位管理員尚未確認的首次政府實收，請由原管理員登入查回。');
  expect(subsidyPeriodClient.manualInitialReceipt).toHaveBeenCalledOnce();expect(readPendingGovernmentManualInitial()).toEqual(stored);expect(screen.getByRole('button',{name:'查回原次處理結果'})).toBeDisabled();
 });
 it('fails closed before POST if the same-tab journal cannot be written',async()=>{
  render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();chooseManual();const storage=window.sessionStorage;vi.spyOn(window,'sessionStorage','get').mockReturnValue({getItem:(key:string)=>storage.getItem(key),setItem:()=>{throw new Error('quota');}} as unknown as Storage);
  fireEvent.click(screen.getByRole('button',{name:'補登首次政府實收'}));await screen.findByText(/無法安全讀取或保留原首次政府實收/);
  expect(subsidyPeriodClient.manualInitialReceipt).not.toHaveBeenCalled();expect(screen.getByRole('button',{name:'補登首次政府實收'})).toBeDisabled();
 });
 it('locks new operations when a stored command is corrupt rather than deleting it',async()=>{
  window.sessionStorage.setItem(governmentManualInitialStorageKey,'{"version":1,"bad":true}');render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();
  expect(screen.getByText(/無法安全讀取或保留原首次政府實收/)).toBeVisible();expect(screen.getByLabelText('首次實收來源')).toBeDisabled();expect(window.sessionStorage.getItem(governmentManualInitialStorageKey)).toContain('bad');expect(subsidyPeriodClient.manualInitialReceipt).not.toHaveBeenCalled();
 });
 it('blocks restoration when fresh /me cannot verify the original actor',async()=>{
  window.sessionStorage.setItem(governmentManualInitialStorageKey,JSON.stringify({version:1,actorId:7,command:{unit:'year',year:2025,index:1,amount_ntd:6000,paid_on:'2026-01-01',handling:'exact',reason:'',expected_version:3,key:'pending-key'}}));
  vi.mocked(sessionClient.fetchCurrentUser).mockRejectedValue(new Error('offline'));render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await screen.findByText('無法確認原補登的登入管理員，請重新登入後讀取補登狀態。');
  expect(screen.getByRole('button',{name:'查回原次處理結果'})).toBeDisabled();expect(subsidyPeriodClient.manualInitialReceipt).not.toHaveBeenCalled();expect(readPendingGovernmentManualInitial()?.command.key).toBe('pending-key');
 });
 it('uses fresh /me rather than an original cached actor when restoring',async()=>{
  window.sessionStorage.setItem(governmentManualInitialStorageKey,JSON.stringify({version:1,actorId:7,command:{unit:'year',year:2025,index:1,amount_ntd:6000,paid_on:'2026-01-01',handling:'exact',reason:'',expected_version:3,key:'pending-key'}}));
  vi.mocked(sessionClient.fetchCurrentUser).mockResolvedValue({id:8} as Awaited<ReturnType<typeof sessionClient.fetchCurrentUser>>);render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);
  await screen.findByText('有另一位管理員尚未確認的首次政府實收，請由原管理員登入查回。');expect(screen.getByRole('button',{name:'查回原次處理結果'})).toBeDisabled();expect(subsidyPeriodClient.manualInitialReceipt).not.toHaveBeenCalled();expect(readPendingGovernmentManualInitial()?.actorId).toBe(7);
 });
 it('keeps manual first receipt unavailable once an original balance exists',async()=>{
  vi.mocked(subsidyPeriodClient.query).mockImplementation(async p=>({...view(p),balances:[{identity:'period:9',root_receipt_id:9,kind:'original',case_no:null,direction:'receivable',expected_ntd:6000,received_ntd:0,recognized_ntd:0,returned_ntd:0,remaining_ntd:6000,refund_due_ntd:0,settled:false,status:'待補撥'}]}));
  render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();expect(screen.queryByLabelText('首次實收來源')).toBeNull();expect(subsidyPeriodClient.manualInitialReceipt).not.toHaveBeenCalled();
 });
 it('keeps a bank-scoped workspace on the existing bank workflow',async()=>{
  render(<SubsidyPeriodWorkbench onOpenCase={()=>{}} bankSource={{id:8,direction:'incoming',amountNtd:6000}}/>);await loaded();expect(screen.queryByLabelText('首次實收來源')).toBeNull();expect(screen.getByRole('checkbox')).toBeVisible();
 });
});
