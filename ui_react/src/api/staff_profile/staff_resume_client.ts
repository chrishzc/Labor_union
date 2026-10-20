/** Thin adapter for the Staff-owned resume object; it keeps the controlled-file
 * stage/preview/apply protocol out of the Staff editor. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { decodePayload } from '../shared/runtime_decoder';
import { ApiHttpError, ApiNetworkError, ApiTimeoutError } from '../shared/typed_errors';

const ResumeSchema = z.strictObject({
  file_id: z.string().regex(/^cf_[0-9a-f]{32}$/),
  filename: z.string().min(1).max(255),
  version: z.number().int().positive(),
});
const ResumeResponseSchema = z.strictObject({
  success: z.boolean(), message: z.string(), error: z.string().nullable().optional(),
  data: z.strictObject({ staff_id: z.number().int().positive(), resume: ResumeSchema.nullable() }),
});
const StagingSchema = z.strictObject({
  staging_id: z.string().regex(/^cfs_[0-9a-f]{32}$/), filename: z.string(), mime_type: z.string(),
  size_bytes: z.number().int().nonnegative(), sha256_digest: z.string().regex(/^[0-9a-f]{64}$/), expires_at: z.string(),
});
const PreviewSchema = z.strictObject({
  candidate: z.strictObject({ staging_id: z.string().regex(/^cfs_[0-9a-f]{32}$/), staging_version: z.number().int().positive(), owner: z.literal('staff'), purpose: z.literal('staff_resume'), subject_reference: z.string(), object_key: z.string(), logical_folder: z.string(), filename: z.string(), mime_type: z.string(), size_bytes: z.number().int().nonnegative(), sha256_digest: z.string().regex(/^[0-9a-f]{64}$/), expires_at: z.string() }),
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/), expected_staging_version: z.number().int().positive(), blockers: z.array(z.string()),
});
const ApplySchema = z.strictObject({
  receipt_id: z.string().regex(/^cfr_[0-9a-f]{32}$/), outcome: z.enum(['created', 'replayed']), receipt_type: z.string(), schema_version: z.string(),
  file_id: z.string().regex(/^cf_[0-9a-f]{32}$/), owner: z.literal('staff'), purpose: z.literal('staff_resume'), subject_reference: z.string(), filename: z.string(), logical_folder: z.string(), version: z.number().int().positive(), mime_type: z.literal('application/pdf'), size_bytes: z.number().int().positive(), status: z.string(), applied_at: z.string(), sha256_digest: z.string().regex(/^[0-9a-f]{64}$/),
});
const envelope = <T extends z.ZodTypeAny>(data: T) => z.strictObject({ success: z.boolean(), message: z.string(), error: z.string().nullable().optional(), data });
const identity = () => globalThis.crypto?.randomUUID?.().replaceAll('-', '') ?? Math.random().toString(36).slice(2);
const TransferSettingsSchema = z.strictObject({
  photo_max_bytes: z.number().int().positive(), resume_max_bytes: z.number().int().positive(),
  timeout_seconds: z.number().int().nonnegative(),
});
export type FileTransferSettings = z.infer<typeof TransferSettingsSchema>;
export const fileSizeLabel = (bytes: number) => bytes < 1048576 ? `${bytes} bytes` : `${(bytes / 1048576).toFixed(2)} MiB`;

function resumeError(error: unknown, writing = false): Error {
  if (error instanceof ApiTimeoutError || error instanceof ApiNetworkError) {
    return new Error(writing
      ? '連線中斷或等待逾時，結果尚未確認。請保留目前檔案，以相同操作重試；不要重新建立另一筆上傳。'
      : '連線中斷或等待逾時，檔案尚未讀取完成，請稍後重試。');
  }
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return new Error('管理登入已失效，請重新登入後再操作。');
    if (error.status === 403) return new Error('目前帳號沒有操作此履歷的權限。');
    if (error.status === 404) return new Error('找不到這份履歷，請重新查詢目前版本。');
    if (error.status === 503) return new Error('檔案儲存服務目前無法使用，請稍後重試；原有履歷不會因此被刪除。');
  }
  return error instanceof Error ? error : new Error('履歷操作未完成，請稍後重試。');
}
type ResumeUploadProgress = {
  signature: string;
  intent: Record<string, string>;
  preview: z.infer<typeof PreviewSchema>;
};
const uploadProgress = new Map<string, ResumeUploadProgress>();
const headers = (key?: string) => {
  const token = sessionClient.getToken();
  if (!token) throw new Error('請先登入管理後台。');
  return { token, headers: { 'X-Correlation-ID': `staff-resume-${identity()}`, ...(key ? { 'Idempotency-Key': key } : {}) } };
};

export type StaffResume = z.infer<typeof ResumeSchema>;

export const staffResumeClient = {
  async settings(): Promise<FileTransferSettings> {
    try {
      return decodePayload(envelope(TransferSettingsSchema),
        await transport.get<unknown>('/api/v1/storage/transfer-settings', headers())).data;
    } catch (error) { throw resumeError(error); }
  },
  async current(staffId: number): Promise<StaffResume | null> {
    try {
      const raw = await transport.get<unknown>(`/api/v1/staff/${staffId}/resume`, headers());
      const parsed = decodePayload(ResumeResponseSchema, raw);
      if (parsed.data.staff_id !== staffId) throw new Error('月嫂履歷查詢身分不一致。');
      return parsed.data.resume;
    } catch (error) { throw resumeError(error); }
  },
  async upload(staffId: number, file: File, operationKey?: string): Promise<StaffResume> {
    if (file.type !== 'application/pdf' || !file.name.toLowerCase().endsWith('.pdf')) throw new Error('請選擇 PDF 履歷檔案。');
    const settings = await staffResumeClient.settings();
    if (file.size > settings.resume_max_bytes) throw new Error(`所選履歷 ${fileSizeLabel(file.size)}，超過目前上限 ${fileSizeLabel(settings.resume_max_bytes)}。本次未上傳，請選擇較小檔案或請管理者調整上限。`);
    const options = (key?: string) => ({ ...headers(key), timeoutMs: settings.timeout_seconds * 1000 });
    try {
      const key = operationKey?.trim() || `staff-resume-${staffId}-${identity()}`;
      if (key.length > 191) throw new Error('履歷上傳操作識別無效，請重新選擇檔案。');
      const signature = `${staffId}:${file.name}:${file.size}:${file.lastModified}`;
      let progress = uploadProgress.get(key);
      if (progress && progress.signature !== signature) throw new Error('履歷上傳操作識別已屬於另一個檔案。');
      if (!progress) {
        const form = new FormData();
        form.append('document', file); form.append('owner', 'staff'); form.append('purpose', 'staff_resume');
        form.append('subject_reference', String(staffId)); form.append('object_key', 'resume'); form.append('logical_folder', `staff/${staffId}/resume`);
        const staged = decodePayload(envelope(StagingSchema), await transport.post<unknown>('/api/v1/storage/staging', form, options(key))).data;
        const intent = { staging_id: staged.staging_id, owner: 'staff', purpose: 'staff_resume', subject_reference: String(staffId), object_key: 'resume', logical_folder: `staff/${staffId}/resume` };
        const preview = decodePayload(envelope(PreviewSchema), await transport.post<unknown>('/api/v1/storage/files/preview', intent, options())).data;
        if (preview.blockers.length) throw new Error(`履歷無法上傳：${preview.blockers.join('、')}`);
        progress = { signature, intent, preview };
        uploadProgress.set(key, progress);
      }
      const receipt = decodePayload(envelope(ApplySchema), await transport.post<unknown>('/api/v1/storage/files/apply', { ...progress.intent, expected_staging_version: progress.preview.expected_staging_version, preview_fingerprint: progress.preview.preview_fingerprint }, options(key))).data;
      if (receipt.subject_reference !== String(staffId)) throw new Error('履歷套用身分不一致。');
      uploadProgress.delete(key);
      return { file_id: receipt.file_id, filename: receipt.filename, version: receipt.version };
    } catch (error) { throw resumeError(error, true); }
  },
  async preview(fileId: string): Promise<Blob> {
    const settings = await staffResumeClient.settings();
    try {
      const blob = await transport.get<Blob>(`/api/v1/storage/files/${encodeURIComponent(fileId)}/download`,
        { ...headers(), responseType: 'blob', cache: 'no-store', timeoutMs: settings.timeout_seconds * 1000 });
      if (blob.type.split(';')[0] !== 'application/pdf') throw new Error('履歷回應不是 PDF，無法預覽或下載。');
      return blob;
    } catch (error) { throw resumeError(error); }
  },
  async download(fileId: string, filename: string): Promise<void> {
    const url = URL.createObjectURL(await staffResumeClient.preview(fileId));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
