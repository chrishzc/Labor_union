/** Whole-period government cash; case detail never states an allocated bank amount. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import {ApiDecodeError} from '../shared/typed_errors';

export type SubsidyPeriod = { unit: 'month'|'quarter'|'year'; year: number; index: number };
const period = z.object({unit:z.enum(['month','quarter','year']),year:z.number().int(),index:z.number().int()}).strict();
const line = z.object({case_no:z.string(),service_end_date:z.string(),amount_ntd:z.number().int().nullable(),unavailable_reason:z.string().nullable()}).strict();
const view = z.object({period,version:z.number().int(),label:z.string(),lines:z.array(line),total_ntd:z.number().int().nullable(),
  coverage:z.array(z.object({receipt_id:z.number().int(),period,amount_ntd:z.number().int(),recovered_advance_ntd:z.number().int(),label:z.string(),settled:z.boolean().optional(),source_label:z.literal('人工補登').nullable().optional()}).strict()),
  blocked_cases:z.array(z.string()),recorded_lines:z.array(line),changed_cases:z.array(z.string()),can_reconcile:z.boolean(),amount_changes:z.array(z.strictObject({case_no:z.string(),action:z.string(),before_ntd:z.number().int(),after_ntd:z.number().int(),computed_ntd:z.number().int(),reason:z.string(),actor:z.string(),confirmed_on:z.string()})).optional(),balances:z.array(z.strictObject({identity:z.string(),root_receipt_id:z.number().int(),kind:z.string(),case_no:z.string().nullable(),direction:z.string(),expected_ntd:z.number().int(),received_ntd:z.number().int(),recognized_ntd:z.number().int(),returned_ntd:z.number().int(),remaining_ntd:z.number().int(),refund_due_ntd:z.number().int(),settled:z.boolean(),status:z.string()})).optional(),amount_controls:z.array(z.strictObject({case_no:z.string(),mode:z.string(),computed_ntd:z.number().int().nullable(),effective_ntd:z.number().int().nullable()})).optional(),operations:z.array(z.strictObject({identity:z.number().int(),balance_identity:z.string(),action:z.string(),amount_ntd:z.number().int(),bank_row_id:z.number().int().nullable(),reason:z.string(),actor:z.string(),confirmed_on:z.string()})).optional()}).strict();
const banks = z.object({items:z.array(z.object({id:z.number().int(),paid_on:z.string().nullable(),amount_ntd:z.number().int()}).strict())}).strict();
const caseCoverage = z.object({case_no:z.string(),service_end_date:z.string().nullable(),amount_ntd:z.number().int().nullable(),
  coverage:z.array(z.object({receipt_id:z.number().int(),label:z.string(),amount_ntd:z.number().int(),recorded_case_amount_ntd:z.number().int(),
    recorded_service_end_date:z.string(),recovered_advance_ntd:z.number().int(),settled:z.boolean().optional(),source_label:z.literal('人工補登').nullable().optional()}).strict())}).strict();
export type SubsidyCaseCoverage = z.infer<typeof caseCoverage>;
export type SubsidyPeriodView = z.infer<typeof view>;
export type SubsidyBankRow = z.infer<typeof banks>['items'][number];
const options = () => ({token:sessionClient.getToken() ?? undefined});
export type GovernmentDifferenceCommand={unit:SubsidyPeriod['unit'];year:number;index:number;action:'initial_receipt'|'receipt'|'refund'|'loss'|'manual_amount'|'adopt_calculation';identity:string;amount_ntd:number|null;bank_row_id:number|null;handling:''|'exact'|'partial'|'refund_excess';reason:string;expected_version:number;key:string};
export const governmentManualInitialCommandSchema = z.strictObject({
  unit:z.enum(['month','quarter','year']), year:z.number().int().min(1912).max(9998), index:z.number().int().positive(),
  amount_ntd:z.number().int().positive().safe(),
  paid_on:z.string().regex(/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/).refine(value=>{
    const time=Date.parse(`${value}T00:00:00Z`);
    return value.slice(0,4)!=='0000'&&Number.isFinite(time)&&new Date(time).toISOString().slice(0,10)===value;
  }),
  handling:z.enum(['exact','partial','refund_excess']), reason:z.string().max(500).default(''),
  expected_version:z.number().int().nonnegative().safe(), key:z.string().regex(/^[a-z0-9][a-z0-9._:-]{0,190}$/),
}).refine(value=>value.index<=(value.unit==='month'?12:value.unit==='quarter'?4:1));
export type GovernmentManualInitialCommand=z.infer<typeof governmentManualInitialCommandSchema>;
const manualInitialResult=z.strictObject({receipt_id:z.number().int().positive().safe(),receipt:z.strictObject({receipt_id:z.number().int().positive().safe(),period,amount_ntd:z.number().int().positive().safe(),paid_on:z.string(),source_label:z.literal('人工補登'),key:z.string().regex(/^[a-z0-9][a-z0-9._:-]{0,190}$/)}),view});
export const subsidyPeriodClient = {
  async manualInitialReceipt(command:GovernmentManualInitialCommand){
    const submitted=governmentManualInitialCommandSchema.parse(command);
    const raw=await transport.post<{data:unknown}>('/api/v1/government-subsidy/periods/manual-initial-receipt',submitted,options());
    const decoded=manualInitialResult.safeParse(raw.data);
    if(!decoded.success)throw new ApiDecodeError('尚未取得原次首次政府實收的完整結果，請保留原操作查回。');
    const result=decoded.data;
    const samePeriod=(value:SubsidyPeriod)=>value.unit===submitted.unit&&value.year===submitted.year&&value.index===submitted.index;
    if(!samePeriod(result.view.period)||result.receipt_id!==result.receipt.receipt_id||!samePeriod(result.receipt.period)||result.receipt.amount_ntd!==submitted.amount_ntd||result.receipt.paid_on!==submitted.paid_on||result.receipt.key!==submitted.key){
      throw new ApiDecodeError('尚未取得原次首次政府實收的完整結果，請保留原操作查回。');
    }
    return result;
  },
  async difference(command:GovernmentDifferenceCommand){const raw=await transport.post<{data:unknown}>('/api/v1/government-subsidy/periods/differences',command,options());return view.parse(raw.data);},
  async caseCoverage(caseNo:string,signal?:AbortSignal) {
    const raw=await transport.get<{data:unknown}>(`/api/v1/government-subsidy/periods/cases/${encodeURIComponent(caseNo)}`,{...options(),signal});
    return caseCoverage.parse(raw.data);
  },
  async query(value:SubsidyPeriod,signal?:AbortSignal) {
    const raw = await transport.get<{data:unknown}>('/api/v1/government-subsidy/periods',{...options(),params:value,signal});
    return view.parse(raw.data);
  },
  async bankRows(signal?:AbortSignal) {
    const raw = await transport.get<{data:unknown}>('/api/v1/government-subsidy/periods/bank-rows',{...options(),signal});
    return banks.parse(raw.data).items;
  },
  async reconcile(value:SubsidyPeriodView,bankRow:number,key:string) {
    const raw = await transport.post<{data:{receipt_id:number}}>('/api/v1/government-subsidy/periods/reconcile',{
      ...value.period,bank_row_id:bankRow,expected_version:value.version,idempotency_key:key},options());
    return raw.data;
  },
  async reverse(receiptId:number,bankRow:number,key:string) {
    const raw = await transport.post<{data:{receipt_id:number}}>('/api/v1/government-subsidy/periods/reverse',{
      receipt_id:receiptId,bank_row_id:bankRow,idempotency_key:key},options());
    return raw.data;
  },
};
