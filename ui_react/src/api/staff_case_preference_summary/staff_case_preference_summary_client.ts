/**
 * File: staff_case_preference_summary_client.ts
 * Description: 以目前 Session 查詢單一月嫂的 bounded 接案偏好摘要。
 */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';
import {
  StaffCasePreferenceSummaryResponseSchema,
  type StaffCasePreferenceSummary,
} from './staff_case_preference_summary_schemas';

export interface StaffCasePreferenceSummaryQueryOptions {
  signal?: AbortSignal;
  headers?: Record<string, string>;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface StaffCasePreferenceSummaryClient {
  query(
    staffId: number,
    options?: StaffCasePreferenceSummaryQueryOptions,
  ): Promise<StaffCasePreferenceSummary>;
}

function requireStaffId(staffId: number): void {
  if (!Number.isInteger(staffId) || staffId <= 0) {
    throw new RangeError('staffId 必須是正整數。');
  }
}

function requestOptions(options?: StaffCasePreferenceSummaryQueryOptions): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) {
    throw new ApiHttpError(
      401,
      'staff_case_preference_summary_unauthenticated',
      '尚未登入，無法查詢服務人員接案偏好摘要。',
    );
  }
  const headers = { ...(options?.headers ?? {}) };
  for (const name of Object.keys(headers)) {
    if (name.toLowerCase() === 'authorization') delete headers[name];
  }
  return {
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
    headers,
    token,
  };
}

function decodeSummary(raw: unknown, staffId: number): StaffCasePreferenceSummary {
  const decoded = StaffCasePreferenceSummaryResponseSchema.safeParse(raw);
  if (!decoded.success) {
    throw new ApiDecodeError(
      '服務人員接案偏好摘要回應結構異常。',
      decoded.error.issues.map((issue) => ({
        path: issue.path.join('.') || '(root)',
        message: issue.message,
        code: issue.code,
      })),
      raw,
    );
  }
  if (!decoded.data.success) {
    throw new ApiDecodeError(
      '服務人員接案偏好摘要成功信封標記異常。',
      [{ path: 'success', message: 'expected true', code: 'custom' }],
      raw,
    );
  }
  if (decoded.data.data.staff_id !== staffId) {
    throw new ApiDecodeError(
      '服務人員接案偏好摘要 identity 與 request staffId 不一致。',
      [{ path: 'data.staff_id', message: 'identity mismatch', code: 'custom' }],
      raw,
    );
  }
  return decoded.data.data;
}

class DefaultStaffCasePreferenceSummaryClient implements StaffCasePreferenceSummaryClient {
  public async query(
    staffId: number,
    options?: StaffCasePreferenceSummaryQueryOptions,
  ): Promise<StaffCasePreferenceSummary> {
    requireStaffId(staffId);
    const raw = await transport.get<unknown>(
      `/api/v1/staff/${staffId}/case-preference-summary`,
      requestOptions(options),
    );
    return decodeSummary(raw, staffId);
  }
}

export function createStaffCasePreferenceSummaryClient(): StaffCasePreferenceSummaryClient {
  return new DefaultStaffCasePreferenceSummaryClient();
}

export const staffCasePreferenceSummaryClient = createStaffCasePreferenceSummaryClient();
