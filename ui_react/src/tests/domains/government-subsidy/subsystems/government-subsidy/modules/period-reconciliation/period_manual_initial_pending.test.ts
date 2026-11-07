import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {subsidyPeriodClient,governmentManualInitialCommandSchema,type GovernmentManualInitialCommand} from '../../../../../../../api/government_subsidy/period_reconciliation_client';
import {transport} from '../../../../../../../api/shared/transport';
import {ApiDecodeError} from '../../../../../../../api/shared/typed_errors';
import {governmentManualInitialStorageKey,GovernmentManualInitialStorageError,readPendingGovernmentManualInitial,savePendingGovernmentManualInitial,clearPendingGovernmentManualInitial,type PendingGovernmentManualInitial} from '../../../../../../../api/government_subsidy/period_manual_initial_pending';
vi.mock('../../../../../../../api/shared/transport',()=>({transport:{post:vi.fn(),get:vi.fn()}}));
vi.mock('../../../../../../../api/auth/session_client',()=>({sessionClient:{getToken:()=> 'test-token'}}));
const command:GovernmentManualInitialCommand={unit:'quarter',year:2026,index:4,amount_ntd:6000,paid_on:'2026-10-15',handling:'exact',reason:'已實收',expected_version:3,key:'manual-1'};
const pending:PendingGovernmentManualInitial={version:1,actorId:7,command};
const responseView=()=>{
 const period={unit:command.unit,year:command.year,index:command.index};
 return {period,version:4,label:'2026 第4季',lines:[],total_ntd:6000,coverage:[{receipt_id:9,period,amount_ntd:6000,recovered_advance_ntd:0,label:'2026 第4季',source_label:'人工補登' as '人工補登'|null}],blocked_cases:[],recorded_lines:[],changed_cases:[],can_reconcile:false};
};
const responseReceipt=()=>({receipt_id:9,period:{unit:command.unit,year:command.year,index:command.index},amount_ntd:6000,paid_on:command.paid_on,source_label:'人工補登' as '人工補登'|null,key:command.key});
beforeEach(()=>window.sessionStorage.clear());
afterEach(()=>{vi.restoreAllMocks();vi.resetAllMocks();window.sessionStorage.clear();});
describe('period-local first receipt journal',()=>{
 it('round trips a closed command and authenticated actor, without credentials',()=>{
  savePendingGovernmentManualInitial(pending,null);expect(readPendingGovernmentManualInitial()).toEqual(pending);
  expect(JSON.parse(window.sessionStorage.getItem(governmentManualInitialStorageKey)!)).toEqual(pending);
  savePendingGovernmentManualInitial(pending,pending);clearPendingGovernmentManualInitial(pending);expect(readPendingGovernmentManualInitial()).toBeNull();
 });
 it('never overwrites or clears another unresolved command',()=>{
  savePendingGovernmentManualInitial(pending,null);const another={...pending,command:{...command,key:'other'}};
  expect(()=>savePendingGovernmentManualInitial(another,null)).toThrow(GovernmentManualInitialStorageError);
  expect(()=>clearPendingGovernmentManualInitial(another)).toThrow(GovernmentManualInitialStorageError);expect(readPendingGovernmentManualInitial()).toEqual(pending);
 });
 it('detects storage acknowledgement failure instead of authorizing a POST',()=>{
  const storage=window.sessionStorage;vi.spyOn(window,'sessionStorage','get').mockReturnValue({getItem:(key:string)=>storage.getItem(key),setItem:()=>{}} as unknown as Storage);expect(()=>savePendingGovernmentManualInitial(pending,null)).toThrow(GovernmentManualInitialStorageError);
 });
 it('preserves corrupt storage for review and fails closed',()=>{
  const raw=JSON.stringify({...pending,token:'must-not-be-stored'});window.sessionStorage.setItem(governmentManualInitialStorageKey,raw);
  expect(()=>readPendingGovernmentManualInitial()).toThrow(GovernmentManualInitialStorageError);expect(window.sessionStorage.getItem(governmentManualInitialStorageKey)).toBe(raw);
 });
 it('does not erase a command if storage removal is unavailable',()=>{
  savePendingGovernmentManualInitial(pending,null);const storage=window.sessionStorage;vi.spyOn(window,'sessionStorage','get').mockReturnValue({getItem:(key:string)=>storage.getItem(key),removeItem:()=>{}} as unknown as Storage);
  expect(()=>clearPendingGovernmentManualInitial(pending)).toThrow(GovernmentManualInitialStorageError);expect(readPendingGovernmentManualInitial()).toEqual(pending);
 });
});
describe('strict manual receipt client',()=>{
 it('posts only the canonical first receipt body to the existing period root and decodes the manual source label',async()=>{
  const view=responseView();
  const receipt=responseReceipt();vi.mocked(transport.post).mockResolvedValue({data:{receipt_id:9,receipt,view}});
  await expect(subsidyPeriodClient.manualInitialReceipt(command)).resolves.toEqual({receipt_id:9,receipt,view});
  expect(transport.post).toHaveBeenCalledWith('/api/v1/government-subsidy/periods/manual-initial-receipt',command,{token:'test-token'});
 });
 it.each(['view-period','receipt-period','receipt','source','amount','date','key','missing','unsafe-result'])('rejects an unbound %s response as an unknown result',async mismatch=>{
  const view=responseView();const receipt=responseReceipt();let receipt_id=9;
  if(mismatch==='view-period')view.period={...view.period,year:2025};
  if(mismatch==='receipt-period')receipt.period={...receipt.period,index:3};
  if(mismatch==='receipt')receipt_id=10;
  if(mismatch==='source')receipt.source_label=null;
  if(mismatch==='amount')receipt.amount_ntd=5999;
  if(mismatch==='date')receipt.paid_on='2026-10-16';
  if(mismatch==='key')receipt.key='another-key';
  if(mismatch==='unsafe-result')view.total_ntd=9007199254740992;
  vi.mocked(transport.post).mockResolvedValue({data:{receipt_id,receipt:mismatch==='missing'?undefined:receipt,view}});
  await expect(subsidyPeriodClient.manualInitialReceipt(command)).rejects.toBeInstanceOf(ApiDecodeError);
 });
 it('accepts a true original receipt replay after reversal without fabricating current coverage',async()=>{
  const view={...responseView(),coverage:[],can_reconcile:true};const receipt=responseReceipt();vi.mocked(transport.post).mockResolvedValue({data:{receipt_id:9,receipt,view}});
  await expect(subsidyPeriodClient.manualInitialReceipt(command)).resolves.toEqual({receipt_id:9,receipt,view});
 });
 it('does not expose an unsafe rounded query total as a usable manual target',async()=>{
  vi.mocked(transport.get).mockResolvedValue({data:{...responseView(),total_ntd:9007199254740992}});
  await expect(subsidyPeriodClient.query(command)).rejects.toThrow();
 });
 it('decodes the same manual source label in original case coverage readback',async()=>{
  const data={case_no:'CASE',service_end_date:'2026-10-20',amount_ntd:6000,coverage:[{receipt_id:9,label:'2026 第4季',amount_ntd:6000,recorded_case_amount_ntd:6000,recorded_service_end_date:'2026-10-20',recovered_advance_ntd:0,source_label:'人工補登'}]};
  vi.mocked(transport.get).mockResolvedValue({data});await expect(subsidyPeriodClient.caseCoverage('CASE')).resolves.toEqual(data);
 });
 it.each(['bank','bank_row_id','actor','action','provider','case_no'])('rejects injected %s before transport',async field=>{
  await expect(subsidyPeriodClient.manualInitialReceipt({...command,[field]:'forged'} as GovernmentManualInitialCommand)).rejects.toThrow();expect(transport.post).not.toHaveBeenCalled();
 });
 it.each([{unit:'year',index:2},{unit:'quarter',index:5},{unit:'month',index:13},{year:1911},{year:9999},{amount_ntd:0},{amount_ntd:1.5},{amount_ntd:9007199254740992},{paid_on:'0000-01-01'},{paid_on:'2026-02-30'},{paid_on:'2025-02-29'},{key:'Uppercase'},{key:'x'.repeat(192)},{expected_version:-1},{reason:'x'.repeat(501)}])('rejects invalid period/cash/date/key facts %j',invalid=>{
  expect(governmentManualInitialCommandSchema.safeParse({...command,...invalid}).success).toBe(false);
 });
 it('accepts a real leap date and defaults the optional reason',()=>{
  const {reason:_reason,...withoutReason}=command;
  expect(governmentManualInitialCommandSchema.parse({...withoutReason,paid_on:'2024-02-29'}).reason).toBe('');
 });
});
