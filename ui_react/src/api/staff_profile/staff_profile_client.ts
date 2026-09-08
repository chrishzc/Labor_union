/** Authenticated client for one bounded Staff personal profile. */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import { StaffProfileResponseSchema, type StaffProfile } from './staff_profile_schemas';

export interface StaffProfileRequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
  headers?: Record<string, string>;
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
  const endpoint = `/api/v1/staff/${encodeURIComponent(String(staffId))}/profile`;
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
  if (parsed.data.data.staff_id !== staffId) {
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
