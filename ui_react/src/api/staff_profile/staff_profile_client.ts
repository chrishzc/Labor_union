/** Authenticated client for one bounded Staff personal profile. */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import { StaffProfileResponseSchema, StaffSavedDocumentSchema, type StaffProfile, type StaffSavedDocument } from './staff_profile_schemas';
import { staffResumeClient } from './staff_resume_client';

export interface StaffProfileRequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
  headers?: Record<string, string>;
  documentsAfter?: string;
  documentsPageSize?: number;
}

export interface StaffProfileClient {
  query(staffId: number, options?: StaffProfileRequestOptions): Promise<StaffProfile>;
}

export async function queryStaffProfile(
  staffId: number,
  options?: StaffProfileRequestOptions,
): Promise<StaffProfile> {
  if (!Number.isInteger(staffId) || staffId <= 0) throw new Error('staffId 必須是正整數。');
  const token = sessionClient.getToken();
  if (!token) throw new Error('請先登入管理後台。');
  const headers = { ...(options?.headers ?? {}) };
  for (const name of Object.keys(headers)) {
    if (name.toLowerCase() === 'authorization') delete headers[name];
  }
  const requestOptions: RequestOptions = {
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
    headers,
    token,
  };
  const parameters = new URLSearchParams();
  if (options?.documentsAfter !== undefined) {
    if (!/^cf_[0-9a-f]{32}$/.test(options.documentsAfter)) throw new Error('文件清單位置無效。');
    parameters.set('documents_after', options.documentsAfter);
  }
  if (options?.documentsPageSize !== undefined) {
    if (!Number.isInteger(options.documentsPageSize) || options.documentsPageSize < 1 || options.documentsPageSize > 200) throw new Error('文件清單頁數無效。');
    parameters.set('documents_page_size', String(options.documentsPageSize));
  }
  const endpoint = `/api/v1/staff/${encodeURIComponent(String(staffId))}/profile${parameters.size ? `?${parameters}` : ''}`;
  const raw = await transport.get<unknown>(endpoint, requestOptions);
  const parsed = StaffProfileResponseSchema.safeParse(raw);
  if (!parsed.success) {
    throw new ApiDecodeError(
      '服務人員個人資料回應結構異常。',
      parsed.error.issues.map((issue) => ({
        path: issue.path.join('.') || '(root)',
        message: issue.message,
        code: issue.code,
      })),
      raw,
    );
  }
  if (parsed.data.data.staff_id !== staffId || parsed.data.data.documents?.items.some(item => item.staff_id !== staffId)) {
    throw new Error('服務人員個人資料與查詢對象不一致。');
  }
  return parsed.data.data;
}

class DefaultStaffProfileClient implements StaffProfileClient {
  public query(staffId: number, options?: StaffProfileRequestOptions): Promise<StaffProfile> {
    return queryStaffProfile(staffId, options);
  }
}

export const staffProfileClient: StaffProfileClient = new DefaultStaffProfileClient();

export async function downloadStaffSavedDocument(savedDocument: StaffSavedDocument): Promise<void> {
  const value = StaffSavedDocumentSchema.parse(savedDocument);
  const settings = await staffResumeClient.settings();
  const token = sessionClient.getToken();
  if (!token) throw new Error('請先登入管理後台。');
  const content = await transport.get<Blob>(`/api/v1/data-center/files/${value.file_id}/download`,
    { token, responseType: 'blob', cache: 'no-store', timeoutMs: settings.timeout_seconds * 1000 });
  if (content.type.split(';')[0] !== value.mime_type || content.size !== value.size_bytes) throw new Error('文件版本或格式與清單不一致，請重新讀取。');
  const url = URL.createObjectURL(content);
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = value.filename; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
