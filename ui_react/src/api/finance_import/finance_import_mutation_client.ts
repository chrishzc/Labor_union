/**
 * File: finance_import_mutation_client.ts
 * Description: 以嚴格 typed contract 執行銀行工作簿入庫、Preview、durable Apply 與 terminal receipt 查詢。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { FinanceImportQueryError, mapFinanceImportQueryError } from './finance_import_query_errors';

const sha256 = z.string().regex(/^[0-9a-f]{64}$/);
const ingestionReceiptSchema = z.strictObject({
  batch_identity: z.string().min(1), source_content_digest: sha256, source_row_count: z.number().int().nonnegative(),
  canonical_created_count: z.number().int().nonnegative(), duplicate_occurrence_count: z.number().int().nonnegative(),
  source_warning_count: z.number().int().nonnegative(), source_warning_created_count: z.number().int().nonnegative(), replayed: z.boolean(),
});
const countsSchema = z.strictObject({ source_rows: z.number().int().nonnegative(), canonical_created: z.number().int().nonnegative(), duplicate_occurrences: z.number().int().nonnegative(), ready_dispatch: z.number().int().nonnegative(), existing: z.number().int().nonnegative(), manual_review: z.number().int().nonnegative(), business_pending: z.number().int().nonnegative(), blocked: z.number().int().nonnegative() });
const previewSchema = z.strictObject({ batch_identity: z.string().min(1), batch_version: z.number().int().nonnegative(), source_content_digest: sha256, classifier_version: z.string(), fingerprint_version: z.string(), counts: countsSchema, dispatch_summaries: z.array(z.strictObject({ classification_type: z.string(), candidate_count: z.number().int().nonnegative(), total_amount_ntd: z.number().int().nonnegative() })), rows: z.array(z.strictObject({ row_identity: z.string(), canonical_fact_version: z.number().int().nonnegative(), amount_ntd: z.number().int().positive(), classification_type: z.string(), disposition: z.string(), target_identities: z.array(z.string()), evidence: z.array(z.string()), available_actions: z.array(z.string()), integrity_violations: z.array(z.string()), fingerprint_collision: z.boolean(), formal_reference_conflict: z.boolean() })), blocking_codes: z.array(z.string()), apply_allowed: z.boolean(), preview_fingerprint: sha256 });
const jobAcceptedSchema = z.strictObject({ job_id: z.string().min(1).max(191), status_url: z.string().min(1), replayed: z.boolean() });
const batchReceiptSchema = z.strictObject({ batch_identity: z.string().min(1), resulting_batch_version: z.number().int().positive(), preview_fingerprint: sha256, reconciled_count: z.number().int().nonnegative(), existing_count: z.number().int().nonnegative(), pending_count: z.number().int().nonnegative() });
const batchOutcomeSchema = z.strictObject({ job_id: z.string().min(1).max(191), status: z.enum(['queued', 'running', 'succeeded', 'failed', 'cancelled']), attempt_count: z.number().int().nonnegative(), max_attempts: z.number().int().nonnegative(), result_reference: z.string().min(1).max(191).nullable(), receipt: batchReceiptSchema.nullable() });
const envelope = <T extends z.ZodType>(data: T) => z.strictObject({ success: z.literal(true), message: z.string(), data, error: z.null() });

export type FinanceWorkbookIngestionReceipt = z.infer<typeof ingestionReceiptSchema>;
export type FinanceImportBatchPreview = z.infer<typeof previewSchema>;
export type FinanceImportJobAccepted = z.infer<typeof jobAcceptedSchema>;
export type FinanceImportBatchOutcome = z.infer<typeof batchOutcomeSchema>;

const MAXIMUM_BYTES = 20 * 1024 * 1024;

export class FinanceWorkbookSnapshot {
  readonly #bytes: Uint8Array;
  public readonly filename: string;
  public readonly contentType: string;
  public readonly sha256: string;
  private constructor(filename: string, contentType: string, bytes: Uint8Array, sha256Text: string) { this.filename = filename; this.contentType = contentType; this.#bytes = bytes; this.sha256 = sha256Text; }
  static async fromFile(file: File): Promise<FinanceWorkbookSnapshot> {
    if (!file.name.toLowerCase().endsWith('.xlsx')) throw new FinanceImportQueryError('FINANCE_IMPORT_FILE_TYPE', '銀行流水僅支援 .xlsx 檔案。');
    if (file.size <= 0) throw new FinanceImportQueryError('FINANCE_IMPORT_FILE_EMPTY', '銀行流水工作簿不可為空檔。');
    if (file.size > MAXIMUM_BYTES) throw new FinanceImportQueryError('FINANCE_IMPORT_FILE_TOO_LARGE', '銀行流水工作簿不可超過 20 MiB。');
    if (!globalThis.crypto?.subtle) throw new FinanceImportQueryError('FINANCE_IMPORT_SHA256_UNAVAILABLE', '此瀏覽器無法驗證檔案內容。');
    const bytes = new Uint8Array(await file.arrayBuffer());
    if (bytes.byteLength !== file.size) throw new FinanceImportQueryError('FINANCE_IMPORT_FILE_CHANGED', '檔案內容在讀取期間改變，請重新選檔。');
    const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes.buffer.slice(0));
    const digestText = Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, '0')).join('');
    return new FinanceWorkbookSnapshot(file.name, file.type, bytes, digestText);
  }
  toFormData(): FormData { const body = new FormData(); body.append('workbook', new File([new Uint8Array(this.#bytes)], this.filename, { type: this.contentType }), this.filename); return body; }
}

function requestOptions(signal?: AbortSignal, headers: Record<string, string> = {}): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new FinanceImportQueryError('FINANCE_IMPORT_UNAUTHENTICATED', '請先登入。', false, 401);
  return { token, signal, timeoutMs: 30_000, headers };
}
function keyHeader(key: string, correlationId: string): Record<string, string> {
  if (!key.trim() || !correlationId.trim()) throw new FinanceImportQueryError('FINANCE_IMPORT_COMMAND_IDENTITY_INVALID', '命令識別不得為空白。');
  return { 'Idempotency-Key': key, 'X-Correlation-ID': correlationId };
}
function decode<T>(schema: z.ZodType<T>, raw: unknown, label: string): T {
  try { return decodePayload(envelope(schema), raw).data as T; } catch (error) { throw mapFinanceImportQueryError(error instanceof Error ? error : new Error(`${label}回應結構異常。`)); }
}

export const financeImportMutationClient = {
  async ingest(snapshot: FinanceWorkbookSnapshot, command: { idempotencyKey: string; correlationId: string; signal?: AbortSignal }): Promise<FinanceWorkbookIngestionReceipt> {
    try {
      const receipt = decode(ingestionReceiptSchema, await transport.post('/api/v1/finance-import/workbooks/ingest', snapshot.toFormData(), requestOptions(command.signal, keyHeader(command.idempotencyKey, command.correlationId))), '銀行流水入庫');
      if (receipt.source_content_digest !== snapshot.sha256) throw new FinanceImportQueryError('FINANCE_IMPORT_SOURCE_DIGEST_MISMATCH', '伺服器回傳來源摘要與已選檔案不一致。');
      return receipt;
    } catch (error) { throw mapFinanceImportQueryError(error); }
  },
  async preview(batchIdentity: string, signal?: AbortSignal): Promise<FinanceImportBatchPreview> {
    const batch = batchIdentity.trim(); if (!batch) throw new FinanceImportQueryError('FINANCE_IMPORT_BATCH_IDENTITY_INVALID', 'batch identity 不得為空白。');
    try { return decode(previewSchema, await transport.post('/api/v1/finance-import/batches/preview', { batch_identity: batch }, requestOptions(signal, { 'X-Correlation-ID': `finance-import-preview-${crypto.randomUUID()}` })), 'Finance Import Preview'); } catch (error) { throw mapFinanceImportQueryError(error); }
  },
  async apply(preview: FinanceImportBatchPreview, reason: string, command: { idempotencyKey: string; correlationId: string; signal?: AbortSignal }): Promise<FinanceImportJobAccepted> {
    const normalizedReason = reason.trim(); if (!normalizedReason) throw new FinanceImportQueryError('FINANCE_IMPORT_REASON_REQUIRED', '請填寫正式入帳原因。');
    try { return decode(jobAcceptedSchema, await transport.post('/api/v1/finance-import/batches/apply', { batch_identity: preview.batch_identity, expected_batch_version: preview.batch_version, preview_fingerprint: preview.preview_fingerprint, reason: normalizedReason }, requestOptions(command.signal, keyHeader(command.idempotencyKey, command.correlationId))), 'Finance Import Apply'); } catch (error) { throw mapFinanceImportQueryError(error); }
  },
  async queryBatchOutcome(jobId: string, signal?: AbortSignal): Promise<FinanceImportBatchOutcome> {
    const normalized = jobId.trim(); if (!normalized) throw new FinanceImportQueryError('FINANCE_IMPORT_JOB_ID_INVALID', 'job id 不得為空白。');
    try { const outcome = decode(batchOutcomeSchema, await transport.get(`/api/v1/finance-import/jobs/${encodeURIComponent(normalized)}/batch-outcome`, requestOptions(signal)), 'Finance Import terminal receipt'); if (outcome.job_id !== normalized) throw new FinanceImportQueryError('FINANCE_IMPORT_JOB_IDENTITY_MISMATCH', 'job identity 與查詢不一致。'); return outcome; } catch (error) { throw mapFinanceImportQueryError(error); }
  },
};
