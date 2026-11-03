/** Whole-period government cash; case detail never states an allocated bank amount. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';

export type SubsidyPeriod = { unit: 'month'|'quarter'|'year'; year: number; index: number };
const period = z.object({unit:z.enum(['month','quarter','year']),year:z.number().int(),index:z.number().int()}).strict();
const line = z.object({case_no:z.string(),service_end_date:z.string(),amount_ntd:z.number().int().nullable(),unavailable_reason:z.string().nullable()}).strict();
const view = z.object({period,version:z.number().int(),label:z.string(),lines:z.array(line),total_ntd:z.number().int().nullable(),
  coverage:z.array(z.object({receipt_id:z.number().int(),period,amount_ntd:z.number().int(),recovered_advance_ntd:z.number().int(),label:z.string(),settled:z.boolean().optional()}).strict()),
  blocked_cases:z.array(z.string()),recorded_lines:z.array(line),changed_cases:z.array(z.string()),can_reconcile:z.boolean(),amount_changes:z.array(z.strictObject({case_no:z.string(),action:z.string(),before_ntd:z.number().int(),after_ntd:z.number().int(),computed_ntd:z.number().int(),reason:z.string(),actor:z.string(),confirmed_on:z.string()})).optional(),balances:z.array(z.strictObject({identity:z.string(),root_receipt_id:z.number().int(),kind:z.string(),case_no:z.string().nullable(),direction:z.string(),expected_ntd:z.number().int(),received_ntd:z.number().int(),recognized_ntd:z.number().int(),returned_ntd:z.number().int(),remaining_ntd:z.number().int(),refund_due_ntd:z.number().int(),settled:z.boolean(),status:z.string()})).optional(),amount_controls:z.array(z.strictObject({case_no:z.string(),mode:z.string(),computed_ntd:z.number().int().nullable(),effective_ntd:z.number().int().nullable()})).optional(),operations:z.array(z.strictObject({identity:z.number().int(),balance_identity:z.string(),action:z.string(),amount_ntd:z.number().int(),bank_row_id:z.number().int().nullable(),reason:z.string(),actor:z.string(),confirmed_on:z.string()})).optional()}).strict();
const banks = z.object({items:z.array(z.object({id:z.number().int(),paid_on:z.string().nullable(),amount_ntd:z.number().int()}).strict())}).strict();
const caseCoverage = z.object({case_no:z.string(),service_end_date:z.string().nullable(),amount_ntd:z.number().int().nullable(),
  coverage:z.array(z.object({receipt_id:z.number().int(),label:z.string(),amount_ntd:z.number().int(),recorded_case_amount_ntd:z.number().int(),
    recorded_service_end_date:z.string(),recovered_advance_ntd:z.number().int(),settled:z.boolean().optional()}).strict())}).strict();
export type SubsidyCaseCoverage = z.infer<typeof caseCoverage>;
export type SubsidyPeriodView = z.infer<typeof view>;
export type SubsidyBankRow = z.infer<typeof banks>['items'][number];
const options = () => ({token:sessionClient.getToken() ?? undefined});
export type GovernmentDifferenceCommand={unit:SubsidyPeriod['unit'];year:number;index:number;action:'initial_receipt'|'receipt'|'refund'|'loss'|'manual_amount'|'adopt_calculation';identity:string;amount_ntd:number|null;bank_row_id:number|null;handling:''|'exact'|'partial'|'refund_excess';reason:string;expected_version:number;key:string};
export const subsidyPeriodClient = {
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
