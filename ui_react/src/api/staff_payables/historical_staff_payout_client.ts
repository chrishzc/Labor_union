/** Strict Staff Payables client for pre-system historical payout evidence. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';

const ObligationSchema = z.strictObject({
  obligation_identity: z.string().min(1), case_no: z.string().min(1), staff_id: z.number().int().positive(), amount_due_ntd: z.number().int().positive(),
  payroll_version: z.number().int().nonnegative(), direction: z.enum(['payable_to_staff', 'receivable_from_staff']), status: z.enum(['open', 'settled', 'cancelled']),
});
const QuerySchema = z.strictObject({
  case_no: z.string().min(1), staff_id: z.number().int().positive(), staff_payables_version: z.number().int().nonnegative(),
  adoption_receipt_id: z.number().int().positive().nullable(), adopted: z.boolean(), normal_bank_candidate_identities: z.array(z.string().min(1)), obligations: z.array(ObligationSchema),
});
const PreviewSchema = z.strictObject({
  case_no: z.string().min(1), staff_id: z.number().int().positive(), staff_payables_version: z.number().int().nonnegative(),
  adoption_receipt_id: z.number().int().positive().nullable(), obligations: z.array(ObligationSchema), amount_snapshot_ntd: z.number().int().nonnegative(),
  blockers: z.array(z.string()), can_apply: z.boolean(), preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});
const ReceiptSchema = z.strictObject({
  event_identity: z.string().min(1), case_no: z.string().min(1), staff_id: z.number().int().positive(), obligation_identities: z.array(z.string().min(1)),
  amount_snapshot_ntd: z.number().int().positive(), resulting_staff_payables_version: z.number().int().positive(), preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});
const ReadbackSchema = z.strictObject({
  case_no: z.string().min(1), staff_id: z.number().int().positive(), staff_payables_version: z.number().int().nonnegative(), obligations: z.array(ObligationSchema),
  projections: z.array(z.strictObject({ obligation_identity: z.string().min(1), amount_snapshot_ntd: z.number().int().positive(), obligation_payroll_version: z.number().int().nonnegative() })),
  owner_terminal: z.boolean(),
});
const response = <T extends z.ZodTypeAny>(schema: T) => z.strictObject({ success: z.literal(true), message: z.string(), data: schema, error: z.string().nullable().optional() });
export type HistoricalStaffPayoutQuery = z.infer<typeof QuerySchema>;
export type HistoricalStaffPayoutPreview = z.infer<typeof PreviewSchema>;
export type HistoricalStaffPayoutReadback = z.infer<typeof ReadbackSchema>;
export type HistoricalStaffPayoutIntent = { case_no: string; staff_id: number; confirmation_kind: 'paid' | 'settled'; obligation_identities: string[]; payment_date: string | null; payment_date_unknown_reason: string | null; source_availability: 'missing' | 'ambiguous' | 'unrecoverable'; evidence_reference: string | null };
export type HistoricalStaffPayoutOptions = { signal?: AbortSignal; timeoutMs?: number; baseUrl?: string };
export class HistoricalStaffPayoutClientError extends Error {
  public readonly code: string; public readonly status?: number; public readonly retryable: boolean;
  constructor(code: string, message: string, status?: number, retryable = false) { super(message); this.code = code; this.status = status; this.retryable = retryable; }
}
function requestOptions(input: HistoricalStaffPayoutOptions = {}, headers: Record<string, string> = {}): RequestOptions {
  const token = sessionClient.getToken(); if (!token) throw new HistoricalStaffPayoutClientError('HISTORICAL_STAFF_UNAUTHENTICATED', '請先登入。', 401);
  return { ...input, token, headers, timeoutMs: input.timeoutMs ?? 30_000 };
}
function decode<T extends z.ZodTypeAny>(schema: T, raw: unknown): z.output<T> { try { return decodePayload(response(schema), raw).data; } catch { throw new HistoricalStaffPayoutClientError('HISTORICAL_STAFF_SCHEMA_MISMATCH', '回應不符合 Staff Payables strict 契約。'); } }
function mapped(error: unknown): never { if (error instanceof HistoricalStaffPayoutClientError) throw error; if (error instanceof ApiHttpError) throw new HistoricalStaffPayoutClientError(error.code, error.message, error.status, error.retryable); throw new HistoricalStaffPayoutClientError('HISTORICAL_STAFF_OUTCOME_UNKNOWN', error instanceof Error ? error.message : '結果目前無法確認。', undefined, true); }
export const historicalStaffPayoutClient = {
  async query(caseNo: string, staffId: number, options: HistoricalStaffPayoutOptions = {}): Promise<HistoricalStaffPayoutQuery> { try { return decode(QuerySchema, await transport.get<unknown>(`/api/v1/staff-payout/historical-payouts/${encodeURIComponent(caseNo)}/${staffId}`, requestOptions(options))); } catch (error) { return mapped(error); } },
  async preview(intent: HistoricalStaffPayoutIntent, options: HistoricalStaffPayoutOptions = {}): Promise<HistoricalStaffPayoutPreview> { try { return decode(PreviewSchema, await transport.post<unknown>('/api/v1/staff-payout/historical-payouts/preview', intent, requestOptions(options))); } catch (error) { return mapped(error); } },
  async apply(intent: HistoricalStaffPayoutIntent, preview: HistoricalStaffPayoutPreview, reason: string, idempotencyKey: string, options: HistoricalStaffPayoutOptions = {}) { try { return decode(ReceiptSchema, await transport.post<unknown>('/api/v1/staff-payout/historical-payouts/apply', { ...intent, expected_staff_payables_version: preview.staff_payables_version, expected_adoption_receipt_id: preview.adoption_receipt_id, preview_fingerprint: preview.preview_fingerprint, reason }, requestOptions(options, { 'Idempotency-Key': idempotencyKey, 'X-Correlation-ID': `historical-staff-${crypto.randomUUID()}` }))); } catch (error) { return mapped(error); } },
  async readback(caseNo: string, staffId: number, options: HistoricalStaffPayoutOptions = {}): Promise<HistoricalStaffPayoutReadback> { try { return decode(ReadbackSchema, await transport.get<unknown>(`/api/v1/staff-payout/historical-payouts/${encodeURIComponent(caseNo)}/${staffId}/readback`, requestOptions(options))); } catch (error) { return mapped(error); } },
};
