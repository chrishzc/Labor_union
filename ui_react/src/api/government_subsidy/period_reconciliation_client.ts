/** Whole-period government cash; case detail never states an allocated bank amount. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';

export type SubsidyPeriod = { unit: 'month'|'quarter'|'year'; year: number; index: number };
const period = z.object({unit:z.enum(['month','quarter','year']),year:z.number().int(),index:z.number().int()}).strict();
const line = z.object({case_no:z.string(),service_end_date:z.string(),amount_ntd:z.number().int().nullable(),unavailable_reason:z.string().nullable()}).strict();
const view = z.object({period,version:z.number().int(),label:z.string(),lines:z.array(line),total_ntd:z.number().int().nullable(),
  coverage:z.array(z.object({receipt_id:z.number().int(),period,amount_ntd:z.number().int(),recovered_advance_ntd:z.number().int(),label:z.string()}).strict()),
  blocked_cases:z.array(z.string()),recorded_lines:z.array(line),changed_cases:z.array(z.string()),can_reconcile:z.boolean()}).strict();
const banks = z.object({items:z.array(z.object({id:z.number().int(),paid_on:z.string().nullable(),amount_ntd:z.number().int()}).strict())}).strict();
const caseCoverage = z.object({case_no:z.string(),service_end_date:z.string().nullable(),amount_ntd:z.number().int().nullable(),
  coverage:z.array(z.object({receipt_id:z.number().int(),label:z.string(),amount_ntd:z.number().int(),recorded_case_amount_ntd:z.number().int(),
    recorded_service_end_date:z.string(),recovered_advance_ntd:z.number().int()}).strict())}).strict();
export type SubsidyCaseCoverage = z.infer<typeof caseCoverage>;
export type SubsidyPeriodView = z.infer<typeof view>;
export type SubsidyBankRow = z.infer<typeof banks>['items'][number];
const options = () => ({token:sessionClient.getToken() ?? undefined});
export const subsidyPeriodClient = {
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
