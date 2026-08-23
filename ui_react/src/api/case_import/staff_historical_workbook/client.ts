/**
 * File: client.ts
 * Description: 保存Staff Historical真檔快照並提供typed Preview／Apply請求。
 */
import { sessionClient } from '../../auth/session_client';
import { decodePayload } from '../../shared/runtime_decoder';
import { transport, type RequestOptions } from '../../shared/transport';
import {
  StaffHistoricalWorkbookContractError,
  StaffHistoricalWorkbookFileError,
  StaffHistoricalWorkbookUnauthenticatedError,
  mapStaffHistoricalWorkbookPreviewError,
  mapStaffHistoricalWorkbookApplyError,
} from './errors';
import { StaffHistoricalWorkbookPreviewEnvelopeSchema, StaffHistoricalWorkbookReceiptEnvelopeSchema, type StaffHistoricalWorkbookPreview, type StaffHistoricalWorkbookReceipt } from './schemas';

export const STAFF_HISTORICAL_WORKBOOK_PREVIEW_PATH = '/api/v1/case-import/staff-historical/workbooks/preview';
export const STAFF_HISTORICAL_WORKBOOK_APPLY_PATH = '/api/v1/case-import/staff-historical/workbooks/apply';
const MAXIMUM_BYTES = 20 * 1024 * 1024;

export class StaffHistoricalWorkbookSnapshot {
  readonly #bytes: Uint8Array;
  public readonly filename: string;
  public readonly contentType: string;
  public readonly sha256: string;

  private constructor(
    filename: string,
    contentType: string,
    bytes: Uint8Array,
    sha256: string
  ) {
    this.filename = filename;
    this.contentType = contentType;
    this.#bytes = bytes;
    this.sha256 = sha256;
  }

  static async fromFile(file: File): Promise<StaffHistoricalWorkbookSnapshot> {
    if (!file.name.toLowerCase().endsWith('.xlsx')) throw new StaffHistoricalWorkbookFileError('staff_historical_workbook_must_be_xlsx', '月嫂歷史資料僅支援 .xlsx 檔案。');
    if (file.size <= 0) throw new StaffHistoricalWorkbookFileError('staff_historical_workbook_empty', '月嫂歷史工作簿不可為空檔。');
    if (file.size > MAXIMUM_BYTES) throw new StaffHistoricalWorkbookFileError('staff_historical_workbook_too_large', '月嫂歷史工作簿不可超過 20 MiB。');
    const source = await file.arrayBuffer();
    if (source.byteLength !== file.size) throw new StaffHistoricalWorkbookFileError('staff_historical_file_size_changed', '檔案內容在讀取期間改變，請重新選檔。');
    const bytes = new Uint8Array(source.slice(0));
    return new StaffHistoricalWorkbookSnapshot(file.name, file.type, bytes, await sha256Hex(bytes));
  }

  toFormData(sourceRevision?: string): FormData {
    const data = new FormData();
    data.append('workbook', new File([new Uint8Array(this.#bytes)], this.filename, { type: this.contentType }), this.filename);
    if (sourceRevision) data.append('source_revision', sourceRevision);
    return data;
  }
}

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  if (!globalThis.crypto?.subtle) throw new StaffHistoricalWorkbookFileError('staff_historical_sha256_unavailable', '此瀏覽器無法驗證檔案內容。');
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new Uint8Array(bytes).buffer);
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, '0')).join('');
}

export interface StaffHistoricalWorkbookPreviewOptions {
  signal?: AbortSignal;
  sourceRevision?: string;
}

function requestOptions(signal?: AbortSignal, operation: 'preview' | 'apply' = 'preview'): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new StaffHistoricalWorkbookUnauthenticatedError(operation);
  return { token, signal, timeoutMs: 30_000 };
}

function applyRequestOptions(previewFingerprint: string, idempotencyKey: string, correlationId: string, signal?: AbortSignal): RequestOptions {
  return { ...requestOptions(signal, 'apply'), headers: { 'X-Preview-Fingerprint': previewFingerprint, 'Idempotency-Key': idempotencyKey, 'X-Correlation-ID': correlationId } };
}

export interface StaffHistoricalWorkbookPreviewClient {
  preview(snapshot: StaffHistoricalWorkbookSnapshot, options?: StaffHistoricalWorkbookPreviewOptions): Promise<StaffHistoricalWorkbookPreview>;
  apply(snapshot: StaffHistoricalWorkbookSnapshot, previewFingerprint: string, options: StaffHistoricalWorkbookPreviewOptions & { idempotencyKey: string; correlationId: string }): Promise<StaffHistoricalWorkbookReceipt>;
}

export async function previewStaffHistoricalWorkbook(
  snapshot: StaffHistoricalWorkbookSnapshot,
  options?: StaffHistoricalWorkbookPreviewOptions
): Promise<StaffHistoricalWorkbookPreview> {
  try {
    const raw = await transport.post(STAFF_HISTORICAL_WORKBOOK_PREVIEW_PATH, snapshot.toFormData(options?.sourceRevision), requestOptions(options?.signal));
    const envelope = decodePayload(StaffHistoricalWorkbookPreviewEnvelopeSchema, raw);
    if (envelope.data.source_content_digest !== snapshot.sha256) {
      throw new StaffHistoricalWorkbookContractError('staff_historical_source_digest_mismatch', '伺服器回傳摘要與已選檔案不一致。');
    }
    return envelope.data;
  } catch (error) {
    throw mapStaffHistoricalWorkbookPreviewError(error);
  }
}

export async function applyStaffHistoricalWorkbook(
  snapshot: StaffHistoricalWorkbookSnapshot,
  previewFingerprint: string,
  options: StaffHistoricalWorkbookPreviewOptions & { idempotencyKey: string; correlationId: string }
): Promise<StaffHistoricalWorkbookReceipt> {
  try {
    const raw = await transport.post(STAFF_HISTORICAL_WORKBOOK_APPLY_PATH, snapshot.toFormData(options.sourceRevision), applyRequestOptions(previewFingerprint, options.idempotencyKey, options.correlationId, options.signal));
    const receipt = decodePayload(StaffHistoricalWorkbookReceiptEnvelopeSchema, raw).data;
    if (receipt.source_content_digest !== snapshot.sha256) throw new StaffHistoricalWorkbookContractError('staff_historical_apply_source_digest_mismatch', '套用收據摘要與已選檔案不一致。');
    return receipt;
  } catch (error) {
    throw mapStaffHistoricalWorkbookApplyError(error);
  }
}

export const staffHistoricalWorkbookPreviewClient: StaffHistoricalWorkbookPreviewClient = {
  preview: previewStaffHistoricalWorkbook,
  apply: applyStaffHistoricalWorkbook,
};
