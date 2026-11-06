/** Typed archive commands and case facts; never infer settlement in the browser. */
import { z } from 'zod';
import { exactNtd } from '../shared/exact_ntd';
import { historicalMarkerSchema } from './monthly_accounting_client';
import { transport } from '../shared/transport';
import { sessionClient } from '../auth/session_client';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';
import { decodePayload } from '../shared/runtime_decoder';

const money = z.number().int();
const arrangementSchema=z.strictObject({case_no:z.string(),version:z.number().int().nonnegative(),events:z.array(z.strictObject({version:z.number().int().positive(),action:z.enum(['confirm_direct','withdraw_direct']),reason:z.string(),actor:z.string(),created_at:z.string().datetime({offset:true})}))});
export type CaseArrangement=z.infer<typeof arrangementSchema>;
export type ArrangementCommand={action:'confirm_direct'|'withdraw_direct';reason:string;expected_version:number};
function verifyArrangement(data:CaseArrangement,caseNo:string){
 if(data.case_no!==caseNo||data.version!==data.events.length||data.events.some((event,i)=>event.version!==i+1))throw new ApiDecodeError('案件安排或歷史版本不一致。');
 return data;
}
const subsidyPlanSchema=z.strictObject({case_no:z.string(),version:z.number().int().nonnegative(),events:z.array(z.strictObject({version:z.number().int().positive(),scheme:z.enum(['split','advance','direct']),actor:z.string(),created_at:z.string().datetime({offset:true})}))});
export type CaseSubsidyPlan=z.infer<typeof subsidyPlanSchema>;
export type SubsidyPlanCommand={scheme:'split'|'advance'|'direct';expected_version:number};
function verifyPlan(plan:CaseSubsidyPlan,caseNo:string){if(plan.case_no!==caseNo||plan.version!==plan.events.length||plan.events.some((row,index)=>row.version!==index+1))throw new ApiDecodeError('人工方案來源或版本不一致。');return plan;}
const item = z.strictObject({ identity: z.string(), direction: z.enum(['receivable', 'payable']), label: z.string(), party: z.string(), expected_ntd: money, actual_ntd: money, has_payment: z.boolean(), version: z.string(), due_date: z.string().nullable(), summary_included: z.boolean().optional(), unallocated_surplus_ntd: money.optional(), remaining_ntd: money.nullable().optional(), noncash_ntd: money.optional(), settled: z.boolean().optional(), recognized_ntd: money.optional(), payment_stage: z.enum(['deposit','first','second']).nullable().optional() });
const warning = z.strictObject({ item_identity: z.string(), kind: z.enum(['over_received', 'over_paid', 'under_paid']), expected_ntd: money, actual_ntd: money, difference_ntd: money, source_version: z.string(), dismissed: z.boolean(), dismissed_by: z.string().nullable(), dismissed_at: z.string().nullable() });
const detail = z.strictObject({ case_no: z.string(), client_name: z.string(), receivable_ntd: money.nullable(), received_ntd: money.nullable(), payable_ntd: money.nullable(), paid_ntd: money.nullable(), pending_warning_count: z.number().int().nonnegative(), client_items: z.array(item), staff_items: z.array(item), transactions: z.array(z.strictObject({ identity: z.string(), item_identity: z.string(), occurred_on: z.string(), kind: z.string(), amount_ntd: money, bank: z.string().nullable() })), warnings: z.array(warning), remaining_in_ntd: money.nullable().optional(), remaining_out_ntd: money.nullable().optional(), staff_receivable_ntd:money.nullable().optional(),customer_amount_ntd:money.nullable().optional(),customer_fully_received:z.boolean().nullable().optional(),subsidy_ntd:money.nullable().optional(),scheme:z.enum(['unknown','waiting','split','advance','direct']).optional(),cash_by_flow:z.strictObject({C:money,G:money,PS:money,PT:money,RS:money,RT:money}).nullable().optional(),cash_net_ntd:money.nullable().optional(),customer_burden_ntd:money.nullable().optional(),arrangement:arrangementSchema.nullable().optional(),scheme_conflict:z.boolean().optional(),can_confirm_direct:z.boolean().optional(), collection_progress:z.strictObject({stage:z.enum(['deposit','first','second','scheme']),sources_complete:z.boolean(),expected_ntd:money.nullable(),received_ntd:money.nullable(),remaining_ntd:money.nullable(),due_date:z.string().nullable()}).nullable().optional(), subsidy_plan:subsidyPlanSchema.nullable().optional(),ongoing_completed:z.boolean().optional(), bank_facts: z.array(z.strictObject({ identity: z.string(), occurred_on: z.string(), direction: z.enum(['in', 'out']), amount_ntd: money.positive(), cases: z.array(z.string()), bank: z.string().nullable().optional(), cash_flow: z.enum(['C','G','PS','PT','RS','RT']).nullable().optional() })).optional(), historical_marker: historicalMarkerSchema.nullable().optional() });
const caseDetail = detail.extend({
  receivable_ntd: exactNtd.nullable(), received_ntd: exactNtd.nullable(),
  payable_ntd: exactNtd.nullable(), paid_ntd: exactNtd.nullable(),
  remaining_in_ntd: exactNtd.nullable().optional(), remaining_out_ntd: exactNtd.nullable().optional(),
  client_items: z.array(item.extend({
    expected_ntd: exactNtd, actual_ntd: exactNtd, remaining_ntd: exactNtd.nullable().optional(),
    noncash_ntd: exactNtd.optional(), recognized_ntd: exactNtd.optional(), unallocated_surplus_ntd: exactNtd.optional(),
  })),
  cancellation_settlement: z.strictObject({
    processed_on: z.string(), service_due_ntd: exactNtd, fee_ntd: exactNtd, net_received_ntd: exactNtd,
    fee_received_ntd: exactNtd, refund_due_ntd: exactNtd, additional_charge_due_ntd: exactNtd,
    obligation_identity: z.string().nullable(),
    bank_refunded_ntd: exactNtd.nullable().optional(),
    transfer_fee_ntd: exactNtd.nullable().optional(),
    service_remaining_ntd: exactNtd.optional(),
    fee_remaining_ntd: exactNtd.optional(),
  }).nullable().optional(),
});
const receipt = z.strictObject({ identity: z.string().nullable(), saved_count: money, excluded_count: money });
const envelope = <T extends z.ZodTypeAny>(data: T) => z.strictObject({ success: z.literal(true), message: z.string(), data, error: z.string().nullable().optional() });
export type CaseAccounting = z.infer<typeof caseDetail>;
export type AccountingWarning = z.infer<typeof warning>;
export type AccountingItem = z.infer<typeof item>;
export type CaseManualSupplementCommand = {
  bank: 'sinopac' | 'taishin';
  direction: 'client_receipt' | 'staff_salary' | 'client_refund' | 'government_subsidy';
  target_item: string;
  amount_ntd: number | string;
  transaction_date: string;
  reason?: string | null;
  allow_overage_disposition?: boolean;
};
export const statementColumns = ['帳號', '交易日', '計息日', '入帳日', '摘要', '幣別', '支出', '存入', '餘額', '票據號碼', '銷帳編號', '交易參考編號', '備註', '更正註記', '存摺備註'] as const;
function options(signal?: AbortSignal) { const token = sessionClient.getToken(); if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。'); return { token, signal }; }
function verify(data: CaseAccounting, caseNo: string) {
  if (data.case_no !== caseNo || data.pending_warning_count !== data.warnings.filter(row => !row.dismissed).length || new Set([...data.client_items, ...data.staff_items].map(row => row.identity)).size !== data.client_items.length + data.staff_items.length) throw new ApiDecodeError('案件帳務資料不一致。');
  if(data.arrangement)verifyArrangement(data.arrangement,caseNo);
  if(data.subsidy_plan)verifyPlan(data.subsidy_plan,caseNo);
  return data;
}
export const financeAccountingClient = {
  async subsidyPlan(caseNo:string,signal?:AbortSignal){return verifyPlan(decodePayload(envelope(subsidyPlanSchema),await transport.get(`/api/v1/finance-import/cases/${encodeURIComponent(caseNo)}/accounting/subsidy-plan`,options(signal))).data,caseNo);},
  async saveSubsidyPlan(caseNo:string,command:SubsidyPlanCommand,key:string){const result=decodePayload(envelope(z.strictObject({case_no:z.string(),applied_version:z.number().int().positive(),plan:subsidyPlanSchema})),await transport.post(`/api/v1/finance-import/cases/${encodeURIComponent(caseNo)}/accounting/subsidy-plan`,command,{...options(),headers:{'Idempotency-Key':key}})).data;if(result.case_no!==caseNo||result.applied_version!==command.expected_version+1||result.applied_version>result.plan.version)throw new ApiDecodeError('方案儲存結果與原操作不一致。');verifyPlan(result.plan,caseNo);return result;},

  async arrangement(caseNo:string,signal?:AbortSignal){return verifyArrangement(decodePayload(envelope(arrangementSchema),await transport.get(`/api/v1/finance-import/cases/${encodeURIComponent(caseNo)}/accounting/arrangement`,options(signal))).data,caseNo);},
  async confirmArrangement(caseNo:string,command:ArrangementCommand,key:string){
   const result=decodePayload(envelope(z.strictObject({case_no:z.string(),applied_version:z.number().int().positive(),arrangement:arrangementSchema})),await transport.post(`/api/v1/finance-import/cases/${encodeURIComponent(caseNo)}/accounting/arrangement`,command,{...options(),headers:{'Idempotency-Key':key}})).data;
   if(result.case_no!==caseNo||result.applied_version!==command.expected_version+1||result.applied_version>result.arrangement.version)throw new ApiDecodeError('安排儲存結果與原操作不一致。');
   verifyArrangement(result.arrangement,caseNo);return result;
  },
  async query(caseNo: string, signal?: AbortSignal) { return verify(decodePayload(envelope(caseDetail), await transport.get(`/api/v1/finance-import/cases/${encodeURIComponent(caseNo)}/accounting`, options(signal))).data, caseNo); },
  async warnings(signal?: AbortSignal) { return decodePayload(envelope(z.array(caseDetail)), await transport.get('/api/v1/finance-import/accounting/warnings', options(signal))).data.map(row => verify(row, row.case_no)); },
  async dismiss(caseNo: string, source: AccountingWarning) {
    const { item_identity, kind, expected_ntd, actual_ntd, difference_ntd, source_version } = source;
    return verify(decodePayload(envelope(caseDetail), await transport.post(`/api/v1/finance-import/cases/${encodeURIComponent(caseNo)}/accounting/dismiss`, { item_identity, kind, expected_ntd, actual_ntd, difference_ntd, source_version }, options())).data, caseNo);
  },
  async manual(fields: Record<string, string>, key: string, duplicateOf?: string) {
    return decodePayload(envelope(receipt), await transport.post('/api/v1/finance-import/statements/manual', { fields, duplicate_of: duplicateOf || null }, { ...options(), headers: { 'Idempotency-Key': key } })).data;
  },
  async duplicate(candidate: string, kept: string, key: string) {
    return decodePayload(envelope(receipt), await transport.post('/api/v1/finance-import/statements/duplicates', { candidate_identity: candidate, kept_identity: kept }, { ...options(), headers: { 'Idempotency-Key': key } })).data;
  },
  async download() { return transport.get<Blob>('/api/v1/finance-import/statements/export', { ...options(), responseType: 'blob', timeoutMs: 60000 }); },
  async manualSupplement(caseNo: string, command: CaseManualSupplementCommand, key: string) {
    return verify(decodePayload(envelope(caseDetail), await transport.post(`/api/v1/finance-import/cases/${encodeURIComponent(caseNo)}/manual-supplement`, command, { ...options(), headers: { 'Idempotency-Key': key } })).data, caseNo);
  },
};
