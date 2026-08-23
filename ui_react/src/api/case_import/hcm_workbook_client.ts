/**
 * File: hcm_workbook_client.ts
 * Description: 保存 HCM 真檔快照並提供 typed Preview／Apply 請求。
 */
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import {
  HcmWorkbookContractError,
  HcmWorkbookFileError,
  HcmWorkbookUnauthenticatedError,
  mapHcmWorkbookApplyError,
  mapHcmWorkbookPreviewError,
} from './hcm_workbook_errors';
import {
  HcmWorkbookPreviewEnvelopeSchema,
  HcmWorkbookReceiptEnvelopeSchema,
  type HcmWorkbookPreview,
  type HcmWorkbookReceipt,
} from './hcm_workbook_schemas';

export const HCM_WORKBOOK_PREVIEW_PATH =
  '/api/v1/case-import/hcm/workbooks/preview';
export const HCM_WORKBOOK_APPLY_PATH =
  '/api/v1/case-import/hcm/workbooks/apply';
export const HCM_WORKBOOK_PREVIEW_TIMEOUT_MS = 30_000;
export const HCM_WORKBOOK_MAXIMUM_BYTES = 20 * 1024 * 1024;

export interface HcmWorkbookPreviewRequestOptions {
  signal?: AbortSignal;
  headers?: Record<string, string>;
  baseUrl?: string;
}

/**
 * Snapshot 將 bytes 私有化；每次 request 都由同一份 bytes 重建 multipart File。
 */
export class HcmWorkbookSnapshot {
  readonly #bytes: Uint8Array;
  public readonly filename: string;
  public readonly contentType: string;
  public readonly byteLength: number;
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

  static async fromFile(file: File): Promise<HcmWorkbookSnapshot> {
    validateHcmWorkbookFile(file);
    const source = await file.arrayBuffer();
    if (source.byteLength !== file.size) {
      throw new HcmWorkbookFileError(
        'hcm_preview_file_size_changed',
        '選取中的 HCM 檔案內容在讀取期間改變，請重新選檔。'
      );
    }
    const bytes = new Uint8Array(source.byteLength);
    bytes.set(new Uint8Array(source));
    const sha256 = await sha256Hex(bytes);
    return new HcmWorkbookSnapshot(file.name, file.type, bytes, sha256);
  }

  toFormData(): FormData {
    const copiedBytes = new Uint8Array(this.#bytes.byteLength);
    copiedBytes.set(this.#bytes);
    const workbook = new File([copiedBytes], this.filename, {
      type: this.contentType,
    });
    const formData = new FormData();
    formData.append('workbook', workbook, this.filename);
    return formData;
  }
}

export interface HcmWorkbookPreviewClient {
  preview(
    snapshot: HcmWorkbookSnapshot,
    options?: HcmWorkbookPreviewRequestOptions
  ): Promise<HcmWorkbookPreview>;
  apply(
    snapshot: HcmWorkbookSnapshot,
    previewFingerprint: string,
    options: HcmWorkbookPreviewRequestOptions & { idempotencyKey: string; correlationId: string }
  ): Promise<HcmWorkbookReceipt>;
}

function validateHcmWorkbookFile(file: File): void {
  if (
    !file ||
    typeof file.name !== 'string' ||
    typeof file.size !== 'number' ||
    typeof file.arrayBuffer !== 'function'
  ) {
    throw new HcmWorkbookFileError(
      'hcm_preview_file_invalid',
      '請選擇有效的 HCM Excel 檔案。'
    );
  }
  if (!file.name.toLowerCase().endsWith('.xlsx')) {
    throw new HcmWorkbookFileError(
      'hcm_workbook_must_be_xlsx',
      'HCM Current Workbook 僅支援 .xlsx 檔案。'
    );
  }
  if (file.size <= 0) {
    throw new HcmWorkbookFileError(
      'hcm_workbook_empty',
      'HCM Workbook 不可為空檔。'
    );
  }
  if (file.size > HCM_WORKBOOK_MAXIMUM_BYTES) {
    throw new HcmWorkbookFileError(
      'hcm_workbook_exceeds_20_mib',
      'HCM Workbook 不可超過 20 MiB。'
    );
  }
}

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new HcmWorkbookFileError(
      'hcm_preview_sha256_unavailable',
      '此瀏覽器無法驗證 HCM 檔案內容，請改用支援 Web Crypto 的瀏覽器。'
    );
  }
  const digestBytes = new Uint8Array(new ArrayBuffer(bytes.byteLength));
  digestBytes.set(bytes);
  const digest = await globalThis.crypto.subtle.digest(
    'SHA-256',
    digestBytes.buffer
  );
  return Array.from(new Uint8Array(digest), (value) =>
    value.toString(16).padStart(2, '0')
  ).join('');
}

function requestOptions(
  options?: HcmWorkbookPreviewRequestOptions,
  operation: 'preview' | 'apply' = 'preview'
): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) {
    throw new HcmWorkbookUnauthenticatedError(operation);
  }

  const headers = { ...options?.headers };
  for (const name of Object.keys(headers)) {
    const normalized = name.toLowerCase();
    if (
      normalized === 'authorization' ||
      normalized === 'content-type' ||
      normalized === 'idempotency-key' ||
      normalized === 'x-preview-fingerprint'
    ) {
      delete headers[name];
    }
  }

  return {
    token,
    signal: options?.signal,
    headers,
    baseUrl: options?.baseUrl,
    timeoutMs: HCM_WORKBOOK_PREVIEW_TIMEOUT_MS,
  };
}

function applyRequestOptions(
  previewFingerprint: string,
  options: HcmWorkbookPreviewRequestOptions & { idempotencyKey: string; correlationId: string }
): RequestOptions {
  const base = requestOptions(options, 'apply');
  return {
    ...base,
    headers: {
      ...base.headers,
      'X-Preview-Fingerprint': previewFingerprint,
      'Idempotency-Key': options.idempotencyKey,
      'X-Correlation-ID': options.correlationId,
    },
  };
}

function decodeHcmWorkbookPreview(
  raw: unknown,
  snapshot: HcmWorkbookSnapshot
): HcmWorkbookPreview {
  const envelope = decodePayload(HcmWorkbookPreviewEnvelopeSchema, raw);
  if (envelope.data.source_content_digest !== snapshot.sha256) {
    throw new HcmWorkbookContractError(
      'hcm_preview_source_digest_mismatch',
      '伺服器回傳的 HCM 檔案摘要與已選檔案不一致，預覽已拒絕。'
    );
  }
  return envelope.data;
}

export async function previewHcmWorkbook(
  snapshot: HcmWorkbookSnapshot,
  options?: HcmWorkbookPreviewRequestOptions
): Promise<HcmWorkbookPreview> {
  try {
    const raw = await transport.post(
      HCM_WORKBOOK_PREVIEW_PATH,
      snapshot.toFormData(),
      requestOptions(options)
    );
    return decodeHcmWorkbookPreview(raw, snapshot);
  } catch (error) {
    throw mapHcmWorkbookPreviewError(error);
  }
}

export async function applyHcmWorkbook(
  snapshot: HcmWorkbookSnapshot,
  previewFingerprint: string,
  options: HcmWorkbookPreviewRequestOptions & { idempotencyKey: string; correlationId: string }
): Promise<HcmWorkbookReceipt> {
  try {
    const raw = await transport.post(HCM_WORKBOOK_APPLY_PATH, snapshot.toFormData(), applyRequestOptions(previewFingerprint, options));
    const receipt = decodePayload(HcmWorkbookReceiptEnvelopeSchema, raw).data;
    if (receipt.source_content_digest !== snapshot.sha256) {
      throw new HcmWorkbookContractError('hcm_apply_source_digest_mismatch', '套用收據摘要與已選檔案不一致。');
    }
    return receipt;
  } catch (error) {
    throw mapHcmWorkbookApplyError(error);
  }
}

class DefaultHcmWorkbookPreviewClient implements HcmWorkbookPreviewClient {
  preview(
    snapshot: HcmWorkbookSnapshot,
    options?: HcmWorkbookPreviewRequestOptions
  ): Promise<HcmWorkbookPreview> {
    return previewHcmWorkbook(snapshot, options);
  }

  apply(
    snapshot: HcmWorkbookSnapshot,
    previewFingerprint: string,
    options: HcmWorkbookPreviewRequestOptions & { idempotencyKey: string; correlationId: string }
  ): Promise<HcmWorkbookReceipt> {
    return applyHcmWorkbook(snapshot, previewFingerprint, options);
  }
}

export function createHcmWorkbookPreviewClient(): HcmWorkbookPreviewClient {
  return new DefaultHcmWorkbookPreviewClient();
}

export const hcmWorkbookPreviewClient: HcmWorkbookPreviewClient =
  createHcmWorkbookPreviewClient();
