/**
 * File: staff_case_preference_summary_client.ts
 * Description: 查詢並以 Staff owner Preview/Apply 維護單一月嫂的六項接案偏好。
 */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';
import {
  StaffCasePreferenceApplyPayloadSchema,
  StaffCasePreferenceApplyReceiptResponseSchema,
  StaffCasePreferencePreviewResponseSchema,
  StaffCasePreferenceSnapshotSchema,
  StaffCasePreferenceSummaryResponseSchema,
  type StaffCasePreferenceApplyPayload,
  type StaffCasePreferenceApplyReceipt,
  type StaffCasePreferencePreview,
  type StaffCasePreferenceSnapshot,
  type StaffCasePreferenceSummary,
} from './staff_case_preference_summary_schemas';

export interface StaffCasePreferenceSummaryQueryOptions {
  signal?: AbortSignal;
  headers?: Record<string, string>;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface StaffCasePreferenceSummaryClient {
  query(staffId: number, options?: StaffCasePreferenceSummaryQueryOptions): Promise<StaffCasePreferenceSummary>;
  preview(staffId: number, snapshot: StaffCasePreferenceSnapshot, options?: StaffCasePreferenceSummaryQueryOptions): Promise<StaffCasePreferencePreview>;
  apply(staffId: number, payload: StaffCasePreferenceApplyPayload, options?: StaffCasePreferenceSummaryQueryOptions): Promise<StaffCasePreferenceApplyReceipt>;
}

function requireStaffId(staffId: number): void {
  if (!Number.isInteger(staffId) || staffId <= 0) throw new RangeError('staffId 必須是正整數。');
}

function requestOptions(options?: StaffCasePreferenceSummaryQueryOptions): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) {
    throw new ApiHttpError(401, 'staff_case_preference_summary_unauthenticated', '尚未登入，無法查詢服務人員接案偏好摘要。');
  }
  const headers = { ...(options?.headers ?? {}) };
  for (const name of Object.keys(headers)) {
    if (name.toLowerCase() === 'authorization') delete headers[name];
  }
  return { signal: options?.signal, timeoutMs: options?.timeoutMs, baseUrl: options?.baseUrl, headers, token };
}

function decode<T>(raw: unknown, schema: { safeParse(value: unknown): any }, label: string, staffId: number): T {
  const decoded = schema.safeParse(raw);
  if (!decoded.success) {
    throw new ApiDecodeError(
      `${label}回應結構異常。`,
      decoded.error.issues.map((issue: any) => ({ path: issue.path.join('.') || '(root)', message: issue.message, code: issue.code })),
      raw,
    );
  }
  if (!decoded.data.success) throw new ApiDecodeError(`${label}成功信封標記異常。`, [{ path: 'success', message: 'expected true', code: 'custom' }], raw);
  if (decoded.data.data.staff_id !== staffId) throw new ApiDecodeError(`${label} identity 與 request staffId 不一致。`, [{ path: 'data.staff_id', message: 'identity mismatch', code: 'custom' }], raw);
  return decoded.data.data as T;
}

class DefaultStaffCasePreferenceSummaryClient implements StaffCasePreferenceSummaryClient {
  public async query(staffId: number, options?: StaffCasePreferenceSummaryQueryOptions): Promise<StaffCasePreferenceSummary> {
    requireStaffId(staffId);
    const raw = await transport.get<unknown>(`/api/v1/staff/${staffId}/case-preference-summary`, requestOptions(options));
    return decode<StaffCasePreferenceSummary>(raw, StaffCasePreferenceSummaryResponseSchema, '服務人員接案偏好摘要', staffId);
  }

  public async preview(staffId: number, snapshot: StaffCasePreferenceSnapshot, options?: StaffCasePreferenceSummaryQueryOptions): Promise<StaffCasePreferencePreview> {
    requireStaffId(staffId);
    const parsed = StaffCasePreferenceSnapshotSchema.parse(snapshot);
    const raw = await transport.post<unknown>(`/api/v1/staff/${staffId}/case-preference-summary/preview`, parsed, requestOptions(options));
    return decode<StaffCasePreferencePreview>(raw, StaffCasePreferencePreviewResponseSchema, '服務人員接案偏好預覽', staffId);
  }

  public async apply(staffId: number, payload: StaffCasePreferenceApplyPayload, options?: StaffCasePreferenceSummaryQueryOptions): Promise<StaffCasePreferenceApplyReceipt> {
    requireStaffId(staffId);
    const parsed = StaffCasePreferenceApplyPayloadSchema.parse(payload);
    const raw = await transport.post<unknown>(`/api/v1/staff/${staffId}/case-preference-summary/apply`, parsed, requestOptions(options));
    return decode<StaffCasePreferenceApplyReceipt>(raw, StaffCasePreferenceApplyReceiptResponseSchema, '服務人員接案偏好套用', staffId);
  }
}

export function createStaffCasePreferenceSummaryClient(): StaffCasePreferenceSummaryClient {
  return new DefaultStaffCasePreferenceSummaryClient();
}

export const staffCasePreferenceSummaryClient = createStaffCasePreferenceSummaryClient();
