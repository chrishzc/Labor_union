/**
 * File: client.ts
 * Description: 以 immutable review identity 提供 typed Query／Preview／Apply 與冪等檔案快照。
 */
import { sessionClient } from '../../auth/session_client';
import { decodePayload } from '../../shared/runtime_decoder';
import { transport, type RequestOptions } from '../../shared/transport';
import {
  HistoricalReviewRemediationContractError,
  HistoricalReviewRemediationFileError,
  HistoricalReviewRemediationUnauthenticatedError,
  mapHistoricalReviewRemediationApplyError,
  mapHistoricalReviewRemediationPreviewError,
  mapHistoricalReviewRemediationQueryError,
} from './errors';
import {
  HistoricalReviewApplyEnvelopeSchema,
  HistoricalReviewContextEnvelopeSchema,
  HistoricalReviewPreviewEnvelopeSchema,
  type HistoricalReviewApply,
  type HistoricalReviewContext,
  type HistoricalReviewPreview,
} from './schemas';

export const HISTORICAL_REVIEW_REMEDIATION_PATH = '/api/v1/orders/historical-review-remediations';
export const HISTORICAL_REVIEW_REMEDIATION_QUERY_PATH = (reviewIdentity: string): string => `${HISTORICAL_REVIEW_REMEDIATION_PATH}/${encodeURIComponent(reviewIdentity)}`;
export const HISTORICAL_REVIEW_REMEDIATION_PREVIEW_PATH = (): string => `${HISTORICAL_REVIEW_REMEDIATION_PATH}/preview`;
export const HISTORICAL_REVIEW_REMEDIATION_APPLY_PATH = (): string => `${HISTORICAL_REVIEW_REMEDIATION_PATH}/apply`;
const MAXIMUM_BYTES = 20 * 1024 * 1024;

export class HistoricalReviewRemediationWorkbookSnapshot {
  readonly #bytes: Uint8Array;
  public readonly filename: string;
  public readonly contentType: string;
  public readonly sha256: string;

  private constructor(filename: string, contentType: string, bytes: Uint8Array, sha256: string) {
    this.filename = filename;
    this.contentType = contentType;
    this.#bytes = bytes;
    this.sha256 = sha256;
  }

  static async fromFile(file: File): Promise<HistoricalReviewRemediationWorkbookSnapshot> {
    if (!file.name.toLowerCase().endsWith('.xlsx')) throw new HistoricalReviewRemediationFileError('historical_review_workbook_must_be_xlsx', '更正工作簿僅支援 .xlsx 檔案。');
    if (file.size <= 0) throw new HistoricalReviewRemediationFileError('historical_review_workbook_empty', '更正工作簿不可為空檔。');
    if (file.size > MAXIMUM_BYTES) throw new HistoricalReviewRemediationFileError('historical_review_workbook_too_large', '更正工作簿不可超過 20 MiB。');
    const source = await file.arrayBuffer();
    if (source.byteLength !== file.size) throw new HistoricalReviewRemediationFileError('historical_review_file_size_changed', '檔案內容在讀取期間改變，請重新選檔。');
    const bytes = new Uint8Array(source.slice(0));
    return new HistoricalReviewRemediationWorkbookSnapshot(file.name, file.type, bytes, await sha256Hex(bytes));
  }

  toFormData(): FormData {
    const data = new FormData();
    data.append('workbook', new File([new Uint8Array(this.#bytes)], this.filename, { type: this.contentType }), this.filename);
    return data;
  }
}

export interface HistoricalReviewRemediationPreviewInput {
  prior_review_identity: string;
  expected_review_version: number;
  expected_remediation_version: number;
  reason: string;
  evidence: string;
}

export interface HistoricalReviewRemediationApplyInput extends HistoricalReviewRemediationPreviewInput {
  preview_fingerprint: string;
}

export interface HistoricalReviewRemediationRequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

export interface HistoricalReviewRemediationApplyOptions extends HistoricalReviewRemediationRequestOptions {
  idempotencyKey: string;
  correlationId: string;
}

export interface HistoricalReviewRemediationClient {
  query(reviewIdentity: string, options?: HistoricalReviewRemediationRequestOptions): Promise<HistoricalReviewContext>;
  preview(snapshot: HistoricalReviewRemediationWorkbookSnapshot, input: HistoricalReviewRemediationPreviewInput, options?: HistoricalReviewRemediationRequestOptions): Promise<HistoricalReviewPreview>;
  apply(snapshot: HistoricalReviewRemediationWorkbookSnapshot, input: HistoricalReviewRemediationApplyInput, options: HistoricalReviewRemediationApplyOptions): Promise<HistoricalReviewApply>;
}

function requestOptions(options: HistoricalReviewRemediationRequestOptions | undefined, operation: 'query' | 'preview' | 'apply'): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new HistoricalReviewRemediationUnauthenticatedError(operation);
  return { token, signal: options?.signal, timeoutMs: options?.timeoutMs ?? 30_000 };
}

function validateIdentity(identity: string): string {
  const value = identity.trim();
  if (!value) throw new HistoricalReviewRemediationContractError('historical_review_identity_missing', '歷史訂單 review identity 不可為空。');
  return value;
}

function validateOperatorInput(input: HistoricalReviewRemediationPreviewInput): void {
  if (!input.reason.trim()) throw new HistoricalReviewRemediationContractError('historical_review_reason_required', '處理原因為必填。');
  if (!input.evidence.trim()) throw new HistoricalReviewRemediationContractError('historical_review_evidence_required', '處理佐證為必填。');
  if (!Number.isInteger(input.expected_review_version) || input.expected_review_version < 0) throw new HistoricalReviewRemediationContractError('historical_review_expected_version_invalid', 'review 版本無效。');
  if (!Number.isInteger(input.expected_remediation_version) || input.expected_remediation_version < 0) throw new HistoricalReviewRemediationContractError('historical_review_expected_remediation_version_invalid', 'remediation 版本無效。');
}

function appendInput(data: FormData, input: HistoricalReviewRemediationPreviewInput): void {
  data.append('review_identity', input.prior_review_identity);
  data.append('expected_review_version', String(input.expected_review_version));
  data.append('expected_remediation_version', String(input.expected_remediation_version));
  data.append('reason', input.reason.trim());
  data.append('evidence', input.evidence.trim());
}

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  if (!globalThis.crypto?.subtle) throw new HistoricalReviewRemediationFileError('historical_review_sha256_unavailable', '此瀏覽器無法驗證檔案內容。');
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new Uint8Array(bytes).buffer);
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, '0')).join('');
}

export async function queryHistoricalReviewRemediation(reviewIdentity: string, options?: HistoricalReviewRemediationRequestOptions): Promise<HistoricalReviewContext> {
  const identity = validateIdentity(reviewIdentity);
  try {
    const raw = await transport.get(HISTORICAL_REVIEW_REMEDIATION_QUERY_PATH(identity), requestOptions(options, 'query'));
    const context = decodePayload(HistoricalReviewContextEnvelopeSchema, raw).data;
    if (!context) throw new HistoricalReviewRemediationContractError('historical_review_context_missing', '伺服器未回傳 review 根事實。');
    if (context.review_identity !== identity) throw new HistoricalReviewRemediationContractError('historical_review_identity_mismatch', '伺服器回傳的 review identity 與查詢目標不一致。');
    return context;
  } catch (error) {
    throw mapHistoricalReviewRemediationQueryError(error);
  }
}

export async function previewHistoricalReviewRemediation(snapshot: HistoricalReviewRemediationWorkbookSnapshot, input: HistoricalReviewRemediationPreviewInput, options?: HistoricalReviewRemediationRequestOptions): Promise<HistoricalReviewPreview> {
  const identity = validateIdentity(input.prior_review_identity);
  validateOperatorInput(input);
  try {
    const data = snapshot.toFormData();
    appendInput(data, input);
    const raw = await transport.post(HISTORICAL_REVIEW_REMEDIATION_PREVIEW_PATH(), data, requestOptions(options, 'preview'));
    const preview = decodePayload(HistoricalReviewPreviewEnvelopeSchema, raw).data;
    if (!preview) throw new HistoricalReviewRemediationContractError('historical_review_preview_missing', '伺服器未回傳 Preview 結果。');
    if (preview.prior_review_identity !== identity) throw new HistoricalReviewRemediationContractError('historical_review_preview_identity_mismatch', 'Preview 回傳的 review identity 不一致。');
    if (preview.source_content_digest !== snapshot.sha256) throw new HistoricalReviewRemediationContractError('historical_review_source_digest_mismatch', 'Preview 摘要與已選檔案不一致。');
    return preview;
  } catch (error) {
    throw mapHistoricalReviewRemediationPreviewError(error);
  }
}

export async function applyHistoricalReviewRemediation(snapshot: HistoricalReviewRemediationWorkbookSnapshot, input: HistoricalReviewRemediationApplyInput, options: HistoricalReviewRemediationApplyOptions): Promise<HistoricalReviewApply> {
  const identity = validateIdentity(input.prior_review_identity);
  validateOperatorInput(input);
  if (!/^[0-9a-f]{64}$/.test(input.preview_fingerprint)) throw new HistoricalReviewRemediationContractError('historical_review_preview_fingerprint_invalid', 'Preview fingerprint 無效。');
  if (!options.idempotencyKey.trim() || !options.correlationId.trim()) throw new HistoricalReviewRemediationContractError('historical_review_apply_headers_missing', 'Apply 必須提供 Idempotency-Key 與 X-Correlation-ID。');
  try {
    const data = snapshot.toFormData();
    appendInput(data, input);
    data.append('preview_fingerprint', input.preview_fingerprint);
    const raw = await transport.post(
      HISTORICAL_REVIEW_REMEDIATION_APPLY_PATH(),
      data,
      { ...requestOptions(options, 'apply'), headers: { 'Idempotency-Key': options.idempotencyKey, 'X-Correlation-ID': options.correlationId } },
    );
    const applied = decodePayload(HistoricalReviewApplyEnvelopeSchema, raw).data;
    if (!applied) throw new HistoricalReviewRemediationContractError('historical_review_apply_missing', '伺服器未回傳 Apply 收據。');
    if (applied.prior_review_identity !== identity || applied.receipt.source_content_digest !== snapshot.sha256 || applied.receipt.preview_fingerprint !== input.preview_fingerprint) {
      throw new HistoricalReviewRemediationContractError('historical_review_apply_binding_mismatch', 'Apply 收據未綁定目前 review、檔案與 Preview。');
    }
    if (applied.disposition !== applied.receipt.disposition) throw new HistoricalReviewRemediationContractError('historical_review_apply_disposition_mismatch', 'Apply disposition 與收據不一致。');
    return applied;
  } catch (error) {
    throw mapHistoricalReviewRemediationApplyError(error);
  }
}

export const historicalReviewRemediationClient: HistoricalReviewRemediationClient = {
  query: queryHistoricalReviewRemediation,
  preview: previewHistoricalReviewRemediation,
  apply: applyHistoricalReviewRemediation,
};
