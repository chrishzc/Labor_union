/**
 * File: client.ts
 * Description: 保存Client BeClass真檔快照並提供typed Preview／Apply請求。
 */
import { sessionClient } from '../../auth/session_client';
import { decodePayload } from '../../shared/runtime_decoder';
import { transport, type RequestOptions } from '../../shared/transport';
import {
  ClientBeClassWorkbookContractError,
  ClientBeClassWorkbookFileError,
  ClientBeClassWorkbookUnauthenticatedError,
  mapClientBeClassWorkbookApplyError,
  mapClientBeClassWorkbookPreviewError,
} from './errors';
import {
  ClientBeClassWorkbookPreviewEnvelopeSchema,
  ClientBeClassWorkbookReceiptEnvelopeSchema,
  type ClientBeClassWorkbookPreview,
  type ClientBeClassWorkbookReceipt,
} from './schemas';

export const CLIENT_BECLASS_WORKBOOK_PREVIEW_PATH =
  '/api/v1/case-import/client-beclass/workbooks/preview';
export const CLIENT_BECLASS_WORKBOOK_APPLY_PATH =
  '/api/v1/case-import/client-beclass/workbooks/apply';
const MAXIMUM_BYTES = 20 * 1024 * 1024;

export class ClientBeClassWorkbookSnapshot {
  readonly #bytes: Uint8Array;
  public readonly byteLength: number;
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
    this.byteLength = bytes.byteLength;
    this.sha256 = sha256;
  }

  static async fromFile(file: File): Promise<ClientBeClassWorkbookSnapshot> {
    if (!file.name.toLowerCase().endsWith('.xlsx')) throw new ClientBeClassWorkbookFileError('client_beclass_workbook_must_be_xlsx', '客戶 BeClass 僅支援 .xlsx 檔案。');
    if (file.size <= 0) throw new ClientBeClassWorkbookFileError('client_beclass_workbook_empty', '客戶 BeClass 工作簿不可為空檔。');
    if (file.size > MAXIMUM_BYTES) throw new ClientBeClassWorkbookFileError('client_beclass_workbook_too_large', '客戶 BeClass 工作簿不可超過 20 MiB。');
    const source = await file.arrayBuffer();
    if (source.byteLength !== file.size) throw new ClientBeClassWorkbookFileError('client_beclass_file_size_changed', '檔案內容在讀取期間改變，請重新選檔。');
    const bytes = new Uint8Array(source.slice(0));
    return new ClientBeClassWorkbookSnapshot(file.name, file.type, bytes, await sha256Hex(bytes));
  }

  toFormData(): FormData {
    const copy = new Uint8Array(this.#bytes);
    const data = new FormData();
    data.append('workbook', new File([copy], this.filename, { type: this.contentType }), this.filename);
    return data;
  }

  toApplyFormData(previewFingerprint: string): FormData {
    const data = this.toFormData();
    data.append('preview_fingerprint', previewFingerprint);
    return data;
  }
}

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  if (!globalThis.crypto?.subtle) throw new ClientBeClassWorkbookFileError('client_beclass_sha256_unavailable', '此瀏覽器無法驗證檔案內容。');
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new Uint8Array(bytes).buffer);
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, '0')).join('');
}

function requestOptions(signal?: AbortSignal, operation: 'preview' | 'apply' = 'preview'): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new ClientBeClassWorkbookUnauthenticatedError(operation);
  return { token, signal, timeoutMs: 30_000 };
}

function applyRequestOptions(idempotencyKey: string, correlationId: string, signal?: AbortSignal): RequestOptions {
  return { ...requestOptions(signal, 'apply'), headers: { 'Idempotency-Key': idempotencyKey, 'X-Correlation-ID': correlationId } };
}

export interface ClientBeClassWorkbookPreviewClient {
  preview(snapshot: ClientBeClassWorkbookSnapshot, options?: { signal?: AbortSignal }): Promise<ClientBeClassWorkbookPreview>;
  apply(snapshot: ClientBeClassWorkbookSnapshot, previewFingerprint: string, options: { idempotencyKey: string; correlationId: string; signal?: AbortSignal }): Promise<ClientBeClassWorkbookReceipt>;
}

export async function previewClientBeClassWorkbook(
  snapshot: ClientBeClassWorkbookSnapshot,
  options?: { signal?: AbortSignal }
): Promise<ClientBeClassWorkbookPreview> {
  try {
    const raw = await transport.post(CLIENT_BECLASS_WORKBOOK_PREVIEW_PATH, snapshot.toFormData(), requestOptions(options?.signal));
    const envelope = decodePayload(ClientBeClassWorkbookPreviewEnvelopeSchema, raw);
    if (envelope.data.source_content_digest !== snapshot.sha256) {
      throw new ClientBeClassWorkbookContractError('client_beclass_source_digest_mismatch', '伺服器回傳摘要與已選檔案不一致。');
    }
    return envelope.data;
  } catch (error) {
    throw mapClientBeClassWorkbookPreviewError(error);
  }
}

export async function applyClientBeClassWorkbook(
  snapshot: ClientBeClassWorkbookSnapshot,
  previewFingerprint: string,
  options: { idempotencyKey: string; correlationId: string; signal?: AbortSignal }
): Promise<ClientBeClassWorkbookReceipt> {
  try {
    const raw = await transport.post(CLIENT_BECLASS_WORKBOOK_APPLY_PATH, snapshot.toApplyFormData(previewFingerprint), applyRequestOptions(options.idempotencyKey, options.correlationId, options.signal));
    const receipt = decodePayload(ClientBeClassWorkbookReceiptEnvelopeSchema, raw).data;
    if (receipt.source_content_digest !== snapshot.sha256) throw new ClientBeClassWorkbookContractError('client_beclass_apply_source_digest_mismatch', '套用收據摘要與已選檔案不一致。');
    return receipt;
  } catch (error) {
    throw mapClientBeClassWorkbookApplyError(error);
  }
}

export const clientBeClassWorkbookPreviewClient: ClientBeClassWorkbookPreviewClient = {
  preview: previewClientBeClassWorkbook,
  apply: applyClientBeClassWorkbook,
};
