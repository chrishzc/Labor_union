import { z } from 'zod';

import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';


const sha256 = z.string().regex(/^[0-9a-f]{64}$/);
const previewSchema = z.strictObject({
  source_content_digest: sha256,
  sheet_identity: sha256,
  source_row_count: z.number().int().min(0),
  candidate_count: z.number().int().min(0),
  import_count: z.number().int().min(0),
  existing_count: z.number().int().min(0),
  skipped_count: z.number().int().min(0),
  preview_fingerprint: sha256,
});
const receiptSchema = z.strictObject({
  source_content_digest: sha256,
  source_row_count: z.number().int().min(0),
  inserted_count: z.number().int().min(0),
  existing_count: z.number().int().min(0),
  skipped_count: z.number().int().min(0),
  replayed_workbook: z.boolean(),
});
const envelope = <T extends z.ZodTypeAny>(schema: T) => z.strictObject({ success: z.literal(true), message: z.string(), data: schema, error: z.null() });

export type LegacyVirtualAccountPreview = z.infer<typeof previewSchema>;
export type LegacyVirtualAccountReceipt = z.infer<typeof receiptSchema>;

const token = () => {
  const value = sessionClient.getToken();
  if (!value) throw new Error('請先登入管理後台。');
  return value;
};
const commandKey = (scope: string) => `${scope}-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;

export class LegacyVirtualAccountWorkbookSnapshot {
  readonly #bytes: Uint8Array;
  readonly filename: string;
  readonly contentType: string;
  readonly digest: string;

  private constructor(file: File, bytes: Uint8Array, digest: string) {
    this.filename = file.name;
    this.contentType = file.type;
    this.#bytes = bytes;
    this.digest = digest;
  }

  static async fromFile(file: File) {
    if (!file.name.toLowerCase().endsWith('.xlsx')) throw new Error('僅支援 .xlsx 檔案。');
    if (file.size <= 0) throw new Error('工作簿不可為空檔。');
    if (file.size > 20 * 1024 * 1024) throw new Error('工作簿不可超過 20 MiB。');
    const bytes = new Uint8Array(await file.arrayBuffer());
    if (bytes.byteLength !== file.size) throw new Error('檔案內容在讀取期間改變，請重新選檔。');
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes.buffer)), value => value.toString(16).padStart(2, '0')).join('');
    return new LegacyVirtualAccountWorkbookSnapshot(file, bytes, digest);
  }

  form(previewFingerprint?: string) {
    const data = new FormData();
    data.append('workbook', new File([new Uint8Array(this.#bytes)], this.filename, { type: this.contentType }), this.filename);
    if (previewFingerprint) data.append('preview_fingerprint', previewFingerprint);
    return data;
  }
}

const path = '/api/v1/admin/client-finance/legacy-virtual-account-workbooks';

export const legacyVirtualAccountImportClient = {
  async preview(snapshot: LegacyVirtualAccountWorkbookSnapshot): Promise<LegacyVirtualAccountPreview> {
    const raw = await transport.post(`${path}/preview`, snapshot.form(), { token: token(), timeoutMs: 30_000 });
    const result = decodePayload(envelope(previewSchema), raw).data;
    if (result.source_content_digest !== snapshot.digest) throw new Error('伺服器回傳的檔案摘要不一致。');
    return result;
  },
  async apply(snapshot: LegacyVirtualAccountWorkbookSnapshot, previewFingerprint: string, idempotencyKey = commandKey('legacy-va')): Promise<LegacyVirtualAccountReceipt> {
    const raw = await transport.post(`${path}/apply`, snapshot.form(previewFingerprint), { token: token(), timeoutMs: 30_000, headers: { 'Idempotency-Key': idempotencyKey } });
    const result = decodePayload(envelope(receiptSchema), raw).data;
    if (result.source_content_digest !== snapshot.digest) throw new Error('匯入收據的檔案摘要不一致。');
    return result;
  },
};
