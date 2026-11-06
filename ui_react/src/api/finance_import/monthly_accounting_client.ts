import { z } from 'zod';
import { exactNtd } from '../shared/exact_ntd';
import { transport } from '../shared/transport';
import { sessionClient } from '../auth/session_client';
import { ApiHttpError } from '../shared/typed_errors';
import { decodePayload } from '../shared/runtime_decoder';

const amount = z.number().int();
const nonnegativeNtd = exactNtd.refine(value => value >= 0);
const positiveNtd = exactNtd.refine(value => value > 0);
const item = z.strictObject({ case_no: z.string(), client_name: z.string(), identity: z.string(), direction: z.enum(['receivable', 'payable']), label: z.string(), party: z.string(), due_date: z.string().nullable(), expected_ntd: exactNtd, actual_ntd: exactNtd, noncash_ntd: nonnegativeNtd, remaining_ntd: nonnegativeNtd });
const bank = z.strictObject({ identity: z.string(), occurred_on: z.string(), direction: z.enum(['in', 'out']), amount_ntd: positiveNtd, cases: z.array(z.string()), bank: z.string().nullable().optional(), cash_flow: z.enum(['C','G','PS','PT','RS','RT']).nullable().optional() });
const report = z.strictObject({ start_month: z.string(), end_month: z.string(), category: z.enum(['all', 'subsidy', 'non_citizen']), as_of: z.string(), rows: z.array(z.strictObject({ month: z.string(), expected_in_ntd: exactNtd, received_ntd: exactNtd, remaining_in_ntd: nonnegativeNtd, expected_out_ntd: exactNtd, paid_ntd: exactNtd, remaining_out_ntd: nonnegativeNtd, cash_in_ntd: exactNtd.nullable(), cash_out_ntd: exactNtd.nullable(), other_in_ntd: nonnegativeNtd, other_out_ntd: nonnegativeNtd, cash_by_flow: z.strictObject({C:exactNtd, G:exactNtd, PS:exactNtd, PT:exactNtd, RS:exactNtd, RT:exactNtd}).nullable().optional(), items: z.array(item), bank_facts: z.array(bank) })), excluded_cases: z.array(z.string()), undated_item_count: amount.nonnegative(), cash_unavailable_reason: z.literal('mixed_accounting_bank_scope').nullable().optional(), recognitions: z.array(z.strictObject({identity:z.string(),cases:z.array(z.string()),action:z.string(),amount_ntd:positiveNtd,confirmed_on:z.string()})).optional(), recognition_unavailable_reason:z.literal('mixed_accounting_recognition_scope').nullable().optional() });
export const historicalMarkerSchema = z.strictObject({ case_no: z.string(), reason: z.string(), actor: z.string(), created_at: z.string(), amounts: z.array(z.strictObject({ identity: z.string(), direction: z.enum(['receivable', 'payable']), expected_ntd: amount, actual_ntd: amount, remaining_ntd: amount.nonnegative() })).optional() });
const marker = historicalMarkerSchema;
const envelope = <T extends z.ZodTypeAny>(data: T) => z.strictObject({ success: z.literal(true), message: z.string(), data, error: z.string().nullable().optional() });
export type MonthlyAccountingReport = z.infer<typeof report>;
export type HistoricalAccountingMarker = z.infer<typeof marker>;
const receivables = z.strictObject({due_month:z.string().nullable(),category:z.enum(['all','subsidy','non_citizen']),items:z.array(item),undated_count:amount.nonnegative()});
export type ReceivableAccountingList = z.infer<typeof receivables>;
export type AccountingRange = { start_month: string; end_month: string; category: 'subsidy' | 'non_citizen' | 'all' };
function options(signal?: AbortSignal) { const token = sessionClient.getToken(); if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。'); return { token, signal }; }
export const monthlyAccountingClient = {
  async receivables(dueMonth:string|null,category:AccountingRange['category'],undatedOnly=false,signal?:AbortSignal){return decodePayload(envelope(receivables),await transport.get('/api/v1/finance-import/accounting/receivables',{...options(signal),params:{category,undated_only:String(undatedOnly),...(dueMonth?{due_month:dueMonth}:{})}})).data;},
  async query(range: AccountingRange, signal?: AbortSignal) {
    return decodePayload(envelope(report), await transport.get('/api/v1/finance-import/accounting/monthly', { ...options(signal), params: range })).data;
  },
  async download(range: AccountingRange, basis: 'due' | 'cash', signal?: AbortSignal) {
    return transport.get<Blob>('/api/v1/finance-import/accounting/monthly/export', { ...options(signal), params: { ...range, basis }, responseType: 'blob', timeoutMs: 60000 });
  },
  async marker(caseNo: string, signal?: AbortSignal) {
    return decodePayload(envelope(marker.nullable()), await transport.get(`/api/v1/finance-import/cases/${encodeURIComponent(caseNo)}/accounting/historical-marker`, options(signal))).data;
  },
  async mark(caseNo: string, reason: string, versions: Record<string, string>, key: string) {
    return decodePayload(envelope(marker), await transport.post(`/api/v1/finance-import/cases/${encodeURIComponent(caseNo)}/accounting/historical-marker`, { reason, source_versions: versions, confirmed_unverifiable: true }, { ...options(), headers: { 'Idempotency-Key': key } })).data;
  },
};
