/**
 * File: finance_import_correction_client.ts
 * Description: 以嚴格 typed contract 執行帳務異常的 Finance Import 更正 Preview、Apply 與 receipt 查詢。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { FinanceImportQueryError, mapFinanceImportQueryError } from './finance_import_query_errors';

const sha256 = z.string().regex(/^[0-9a-f]{64}$/);
const classificationType = z.enum([
  'client_receipt', 'client_refund', 'client_refund_return',
  'client_subsidy_return', 'government_subsidy', 'staff_payout',
]);
const selectionSchema = z.strictObject({
  row_identity: z.string().min(1).max(191),
  classification_type: classificationType,
  target_obligation_identities: z.array(z.string().min(1).max(191)).min(1),
  refund_ledger_entry_identity: z.string().min(1).max(191).nullable(),
  allow_partial_refund_recovery: z.boolean(),
  allow_refund_overage_recovery: z.boolean(),
  allow_client_receipt_overage: z.boolean(),
  reason: z.string().min(1).max(500),
  evidence: z.array(z.string().min(1)).min(1),
});
const candidateSchema = z.strictObject({
  row_identity: z.string().min(1), batch_identity: z.string().min(1), classification_type: z.string().min(1),
  owning_domain: z.string().min(1), bank_amount_ntd: z.number().int().positive(),
  allocations: z.array(z.strictObject({ obligation_identity: z.string().min(1), amount_ntd: z.number().int().positive() })),
  reason: z.string().min(1), evidence: z.array(z.string().min(1)), refund_ledger_entry_identity: z.string().min(1).nullable(),
  allow_partial_refund_recovery: z.boolean(), allow_refund_overage_recovery: z.boolean(), allow_client_receipt_overage: z.boolean(),
  candidate_fingerprint: sha256,
});
const previewSchema = z.strictObject({
  candidate: candidateSchema, batch_version: z.number().int().nonnegative(), canonical_fact_version: z.number().int().nonnegative(),
  alert_version: z.number().int().nonnegative(), preview_fingerprint: sha256,
});
const jobAcceptedSchema = z.strictObject({ job_id: z.string().min(1).max(191), status_url: z.string().min(1), replayed: z.boolean() });
const receiptSchema = z.strictObject({
  row_identity: z.string().min(1), batch_identity: z.string().min(1), resulting_batch_version: z.number().int().positive(),
  classification_event_count: z.number().int().positive(), ledger_entry_count: z.number().int().positive(), allocation_count: z.number().int().positive(),
  reconciliation_receipt_count: z.number().int().positive(), alert_resolved_event_count: z.number().int().nonnegative(), preview_fingerprint: sha256,
});
const outcomeSchema = z.strictObject({
  job_id: z.string().min(1).max(191), status: z.enum(['queued', 'running', 'succeeded', 'failed', 'cancelled']),
  attempt_count: z.number().int().nonnegative(), max_attempts: z.number().int().nonnegative(), result_reference: z.string().min(1).max(191).nullable(),
  receipt: receiptSchema.nullable(),
});
const envelope = <T extends z.ZodType>(data: T) => z.strictObject({ success: z.literal(true), message: z.string(), data, error: z.null() });

export type FinanceImportCorrectionSelection = z.infer<typeof selectionSchema>;
export type FinanceImportCorrectionPreview = z.infer<typeof previewSchema>;
export type FinanceImportCorrectionJobAccepted = z.infer<typeof jobAcceptedSchema>;
export type FinanceImportCorrectionJobOutcome = z.infer<typeof outcomeSchema>;

function requestOptions(signal?: AbortSignal, headers: Record<string, string> = {}): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new FinanceImportQueryError('FINANCE_IMPORT_UNAUTHENTICATED', '請先登入。', false, 401);
  return { token, signal, timeoutMs: 30_000, headers };
}

function commandHeaders(idempotencyKey: string, correlationId: string): Record<string, string> {
  if (!idempotencyKey.trim() || !correlationId.trim()) throw new FinanceImportQueryError('FINANCE_IMPORT_COMMAND_IDENTITY_INVALID', '命令識別不得為空白。');
  return { 'Idempotency-Key': idempotencyKey, 'X-Correlation-ID': correlationId };
}

function decode<T>(schema: z.ZodType<T>, raw: unknown, label: string): T {
  try { return decodePayload(envelope(schema), raw).data as T; }
  catch (error) { throw mapFinanceImportQueryError(error instanceof Error ? error : new Error(`${label}回應結構異常。`)); }
}

function validSelection(selection: FinanceImportCorrectionSelection): FinanceImportCorrectionSelection {
  const parsed = selectionSchema.safeParse(selection);
  if (!parsed.success) throw new FinanceImportQueryError('FINANCE_IMPORT_CORRECTION_INPUT_INVALID', '帳務更正輸入不完整或格式不正確。');
  return parsed.data;
}

export const financeImportCorrectionClient = {
  async preview(selection: FinanceImportCorrectionSelection, signal?: AbortSignal): Promise<FinanceImportCorrectionPreview> {
    const request = validSelection(selection);
    try {
      return decode(previewSchema, await transport.post('/api/v1/finance-import/corrections/preview', request, requestOptions(signal, { 'X-Correlation-ID': `finance-import-correction-preview-${crypto.randomUUID()}` })), '帳務更正 Preview');
    } catch (error) { throw mapFinanceImportQueryError(error); }
  },
  async apply(preview: FinanceImportCorrectionPreview, selection: FinanceImportCorrectionSelection, command: { idempotencyKey: string; correlationId: string; signal?: AbortSignal }): Promise<FinanceImportCorrectionJobAccepted> {
    const request = validSelection(selection);
    try {
      return decode(jobAcceptedSchema, await transport.post('/api/v1/finance-import/corrections/apply', {
        ...request, expected_batch_version: preview.batch_version, expected_canonical_fact_version: preview.canonical_fact_version,
        expected_alert_version: preview.alert_version, preview_fingerprint: preview.preview_fingerprint,
      }, requestOptions(command.signal, commandHeaders(command.idempotencyKey, command.correlationId))), '帳務更正 Apply');
    } catch (error) { throw mapFinanceImportQueryError(error); }
  },
  async queryOutcome(jobId: string, signal?: AbortSignal): Promise<FinanceImportCorrectionJobOutcome> {
    const normalized = jobId.trim();
    if (!normalized) throw new FinanceImportQueryError('FINANCE_IMPORT_JOB_ID_INVALID', 'job id 不得為空白。');
    try {
      const outcome = decode(outcomeSchema, await transport.get(`/api/v1/finance-import/jobs/${encodeURIComponent(normalized)}/correction-outcome`, requestOptions(signal)), '帳務更正 terminal receipt');
      if (outcome.job_id !== normalized) throw new FinanceImportQueryError('FINANCE_IMPORT_JOB_IDENTITY_MISMATCH', 'job identity 與查詢不一致。');
      return outcome;
    } catch (error) { throw mapFinanceImportQueryError(error); }
  },
};
