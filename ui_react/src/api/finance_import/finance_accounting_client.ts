/** Typed archive commands and case facts; never infer settlement in the browser. */
import { z } from 'zod';
import { transport } from '../shared/transport';
import { sessionClient } from '../auth/session_client';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';
import { decodePayload } from '../shared/runtime_decoder';

const money = z.number().int();
const item = z.strictObject({ identity: z.string(), direction: z.enum(['receivable', 'payable']), label: z.string(), party: z.string(), expected_ntd: money, actual_ntd: money, has_payment: z.boolean(), version: z.string(), due_date: z.string().nullable(), summary_included: z.boolean().optional(), unallocated_surplus_ntd: money.optional() });
const warning = z.strictObject({ item_identity: z.string(), kind: z.enum(['over_received', 'over_paid', 'under_paid']), expected_ntd: money, actual_ntd: money, difference_ntd: money, source_version: z.string(), dismissed: z.boolean(), dismissed_by: z.string().nullable(), dismissed_at: z.string().nullable() });
const detail = z.strictObject({ case_no: z.string(), client_name: z.string(), receivable_ntd: money.nullable(), received_ntd: money.nullable(), payable_ntd: money.nullable(), paid_ntd: money.nullable(), pending_warning_count: z.number().int().nonnegative(), client_items: z.array(item), staff_items: z.array(item), transactions: z.array(z.strictObject({ identity: z.string(), item_identity: z.string(), occurred_on: z.string(), kind: z.string(), amount_ntd: money, bank: z.string().nullable() })), warnings: z.array(warning) });
const receipt = z.strictObject({ identity: z.string().nullable(), saved_count: money, excluded_count: money });
const envelope = <T extends z.ZodTypeAny>(data: T) => z.strictObject({ success: z.literal(true), message: z.string(), data, error: z.string().nullable().optional() });
export type CaseAccounting = z.infer<typeof detail>;
export type AccountingWarning = z.infer<typeof warning>;
export type AccountingItem = z.infer<typeof item>;
export const statementColumns = ['帳號', '交易日', '計息日', '入帳日', '摘要', '幣別', '支出', '存入', '餘額', '票據號碼', '銷帳編號', '交易參考編號', '備註', '更正註記', '存摺備註'] as const;
function options(signal?: AbortSignal) { const token = sessionClient.getToken(); if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。'); return { token, signal }; }
function verify(data: CaseAccounting, caseNo: string) {
  if (data.case_no !== caseNo || data.pending_warning_count !== data.warnings.filter(row => !row.dismissed).length || new Set([...data.client_items, ...data.staff_items].map(row => row.identity)).size !== data.client_items.length + data.staff_items.length) throw new ApiDecodeError('案件帳務資料不一致。');
  return data;
}
export const financeAccountingClient = {
  async query(caseNo: string, signal?: AbortSignal) { return verify(decodePayload(envelope(detail), await transport.get(`/api/v1/finance-import/cases/${encodeURIComponent(caseNo)}/accounting`, options(signal))).data, caseNo); },
  async warnings(signal?: AbortSignal) { return decodePayload(envelope(z.array(detail)), await transport.get('/api/v1/finance-import/accounting/warnings', options(signal))).data.map(row => verify(row, row.case_no)); },
  async dismiss(caseNo: string, source: AccountingWarning) {
    const { item_identity, kind, expected_ntd, actual_ntd, difference_ntd, source_version } = source;
    return verify(decodePayload(envelope(detail), await transport.post(`/api/v1/finance-import/cases/${encodeURIComponent(caseNo)}/accounting/dismiss`, { item_identity, kind, expected_ntd, actual_ntd, difference_ntd, source_version }, options())).data, caseNo);
  },
  async manual(fields: Record<string, string>, key: string, duplicateOf?: string) {
    return decodePayload(envelope(receipt), await transport.post('/api/v1/finance-import/statements/manual', { fields, duplicate_of: duplicateOf || null }, { ...options(), headers: { 'Idempotency-Key': key } })).data;
  },
  async duplicate(candidate: string, kept: string, key: string) {
    return decodePayload(envelope(receipt), await transport.post('/api/v1/finance-import/statements/duplicates', { candidate_identity: candidate, kept_identity: kept }, { ...options(), headers: { 'Idempotency-Key': key } })).data;
  },
  async download() { return transport.get<Blob>('/api/v1/finance-import/statements/export', { ...options(), responseType: 'blob', timeoutMs: 60000 }); },
};
