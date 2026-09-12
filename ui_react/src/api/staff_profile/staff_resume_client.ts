/** Thin adapter for the Staff-owned resume object; it keeps the controlled-file
 * stage/preview/apply protocol out of the Staff editor. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { decodePayload } from '../shared/runtime_decoder';

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
  async current(staffId: number): Promise<StaffResume | null> {
    const raw = await transport.get<unknown>(`/api/v1/staff/${staffId}/resume`, headers());
    const parsed = decodePayload(ResumeResponseSchema, raw);
    if (parsed.data.staff_id !== staffId) throw new Error('月嫂履歷查詢身分不一致。');
    return parsed.data.resume;
  },
  async upload(staffId: number, file: File, operationKey?: string): Promise<StaffResume> {
    if (file.type !== 'application/pdf' || !file.name.toLowerCase().endsWith('.pdf')) throw new Error('請選擇 PDF 履歷檔案。');
    const key = operationKey?.trim() || `staff-resume-${staffId}-${identity()}`;
    if (key.length > 191) throw new Error('履歷上傳操作識別無效，請重新選擇檔案。');
    const signature = `${staffId}:${file.name}:${file.size}:${file.lastModified}`;
    let progress = uploadProgress.get(key);
    if (progress && progress.signature !== signature) throw new Error('履歷上傳操作識別已屬於另一個檔案。');
    if (!progress) {
      const form = new FormData();
      form.append('document', file); form.append('owner', 'staff'); form.append('purpose', 'staff_resume');
      form.append('subject_reference', String(staffId)); form.append('object_key', 'resume'); form.append('logical_folder', `staff/${staffId}/resume`);
      const staged = decodePayload(envelope(StagingSchema), await transport.post<unknown>('/api/v1/storage/staging', form, headers(key))).data;
      const intent = { staging_id: staged.staging_id, owner: 'staff', purpose: 'staff_resume', subject_reference: String(staffId), object_key: 'resume', logical_folder: `staff/${staffId}/resume` };
      const preview = decodePayload(envelope(PreviewSchema), await transport.post<unknown>('/api/v1/storage/files/preview', intent, headers())).data;
      if (preview.blockers.length) throw new Error(`履歷無法上傳：${preview.blockers.join('、')}`);
      progress = { signature, intent, preview };
      uploadProgress.set(key, progress);
    }
    const receipt = decodePayload(envelope(ApplySchema), await transport.post<unknown>('/api/v1/storage/files/apply', { ...progress.intent, expected_staging_version: progress.preview.expected_staging_version, preview_fingerprint: progress.preview.preview_fingerprint }, headers(key))).data;
    if (receipt.subject_reference !== String(staffId)) throw new Error('履歷套用身分不一致。');
    uploadProgress.delete(key);
    return { file_id: receipt.file_id, filename: receipt.filename, version: receipt.version };
  },
  async download(fileId: string, filename: string): Promise<void> {
    const token = sessionClient.getToken();
    if (!token) throw new Error('請先登入管理後台。');
    const response = await fetch(`/api/v1/storage/files/${encodeURIComponent(fileId)}/download`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) throw new Error('目前履歷下載失敗。');
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click();
    URL.revokeObjectURL(url);
  },
};
