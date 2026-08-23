/**
 * File: client.ts
 * Description: 保存Historical Orders真檔快照並提供typed Preview／Apply請求。
 */
import { sessionClient } from '../../auth/session_client';
import { decodePayload } from '../../shared/runtime_decoder';
import { transport, type RequestOptions } from '../../shared/transport';
import {
  HistoricalOrderWorkbookContractError,
  HistoricalOrderWorkbookFileError,
  HistoricalOrderWorkbookUnauthenticatedError,
  mapHistoricalOrderWorkbookApplyError,
  mapHistoricalOrderWorkbookPreviewError,
} from './errors';
import { HistoricalOrderWorkbookPreviewEnvelopeSchema, HistoricalOrderWorkbookReceiptEnvelopeSchema, type HistoricalOrderWorkbookPreview, type HistoricalOrderWorkbookReceipt } from './schemas';

export const HISTORICAL_ORDER_WORKBOOK_PREVIEW_PATH = '/api/v1/orders/historical-adoption/workbooks/preview';
export const HISTORICAL_ORDER_WORKBOOK_APPLY_PATH = '/api/v1/orders/historical-adoption/workbooks/apply';
const MAXIMUM_BYTES = 20 * 1024 * 1024;

export class HistoricalOrderWorkbookSnapshot {
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

  static async fromFile(file: File): Promise<HistoricalOrderWorkbookSnapshot> {
    if (!file.name.toLowerCase().endsWith('.xlsx')) throw new HistoricalOrderWorkbookFileError('historical_order_workbook_must_be_xlsx', '歷史訂單僅支援 .xlsx 檔案。');
    if (file.size <= 0) throw new HistoricalOrderWorkbookFileError('historical_order_workbook_empty', '歷史訂單工作簿不可為空檔。');
    if (file.size > MAXIMUM_BYTES) throw new HistoricalOrderWorkbookFileError('historical_order_workbook_too_large', '歷史訂單工作簿不可超過 20 MiB。');
    const source = await file.arrayBuffer();
    if (source.byteLength !== file.size) throw new HistoricalOrderWorkbookFileError('historical_order_file_size_changed', '檔案內容在讀取期間改變，請重新選檔。');
    const bytes = new Uint8Array(source.slice(0));
    return new HistoricalOrderWorkbookSnapshot(file.name, file.type, bytes, await sha256Hex(bytes));
  }

  toFormData(): FormData {
    const data = new FormData();
    data.append('workbook', new File([new Uint8Array(this.#bytes)], this.filename, { type: this.contentType }), this.filename);
    return data;
  }

  toApplyFormData(previewFingerprint: string): FormData {
    const data = this.toFormData();
    data.append('preview_fingerprint', previewFingerprint);
    return data;
  }
}

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  if (!globalThis.crypto?.subtle) throw new HistoricalOrderWorkbookFileError('historical_order_sha256_unavailable', '此瀏覽器無法驗證檔案內容。');
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new Uint8Array(bytes).buffer);
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, '0')).join('');
}

function requestOptions(signal?: AbortSignal, operation: 'preview' | 'apply' = 'preview'): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new HistoricalOrderWorkbookUnauthenticatedError(operation);
  return { token, signal, timeoutMs: 30_000 };
}

function applyRequestOptions(idempotencyKey: string, correlationId: string, signal?: AbortSignal): RequestOptions {
  return {
    ...requestOptions(signal, 'apply'),
    headers: { 'Idempotency-Key': idempotencyKey, 'X-Correlation-ID': correlationId },
  };
}

export interface HistoricalOrderWorkbookPreviewClient {
  preview(snapshot: HistoricalOrderWorkbookSnapshot, options?: { signal?: AbortSignal }): Promise<HistoricalOrderWorkbookPreview>;
  apply(snapshot: HistoricalOrderWorkbookSnapshot, previewFingerprint: string, options: { idempotencyKey: string; correlationId: string; signal?: AbortSignal }): Promise<HistoricalOrderWorkbookReceipt>;
}

export async function previewHistoricalOrderWorkbook(
  snapshot: HistoricalOrderWorkbookSnapshot,
  options?: { signal?: AbortSignal }
): Promise<HistoricalOrderWorkbookPreview> {
  try {
    const raw = await transport.post(HISTORICAL_ORDER_WORKBOOK_PREVIEW_PATH, snapshot.toFormData(), requestOptions(options?.signal));
    const envelope = decodePayload(HistoricalOrderWorkbookPreviewEnvelopeSchema, raw);
    if (envelope.data.source_content_digest !== snapshot.sha256) {
      throw new HistoricalOrderWorkbookContractError('historical_order_source_digest_mismatch', '伺服器回傳摘要與已選檔案不一致。');
    }
    return envelope.data;
  } catch (error) {
    throw mapHistoricalOrderWorkbookPreviewError(error);
  }
}

export async function applyHistoricalOrderWorkbook(
  snapshot: HistoricalOrderWorkbookSnapshot,
  previewFingerprint: string,
  options: { idempotencyKey: string; correlationId: string; signal?: AbortSignal }
): Promise<HistoricalOrderWorkbookReceipt> {
  try {
    const raw = await transport.post(
      HISTORICAL_ORDER_WORKBOOK_APPLY_PATH,
      snapshot.toApplyFormData(previewFingerprint),
      applyRequestOptions(options.idempotencyKey, options.correlationId, options.signal)
    );
    const receipt = decodePayload(HistoricalOrderWorkbookReceiptEnvelopeSchema, raw).data;
    if (receipt.source_content_digest !== snapshot.sha256) {
      throw new HistoricalOrderWorkbookContractError('historical_order_apply_source_digest_mismatch', '套用收據摘要與已選檔案不一致。');
    }
    return receipt;
  } catch (error) {
    throw mapHistoricalOrderWorkbookApplyError(error);
  }
}

export const historicalOrderWorkbookPreviewClient: HistoricalOrderWorkbookPreviewClient = {
  preview: previewHistoricalOrderWorkbook,
  apply: applyHistoricalOrderWorkbook,
};
