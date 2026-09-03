/**
 * File: staff_case_preference_summary_command_client.ts
 * Description: 以目前 Session 執行六項 Staff 接案偏好的 Preview → Apply。
 */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';
import {
  StaffCasePreferenceApplyRequestSchema,
  StaffCasePreferencePreviewRequestSchema,
  StaffCasePreferencePreviewResponseSchema,
  StaffCasePreferenceReceiptResponseSchema,
  type StaffCasePreferenceApplyRequest,
  type StaffCasePreferencePreview,
  type StaffCasePreferencePreviewRequest,
  type StaffCasePreferenceReceipt,
} from './staff_case_preference_summary_command_schemas';

export interface StaffCasePreferenceCommandOptions {
  signal?: AbortSignal;
  headers?: Record<string, string>;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface StaffCasePreferenceCommandClient {
  preview(
    staffId: number,
    payload: StaffCasePreferencePreviewRequest,
    options?: StaffCasePreferenceCommandOptions,
  ): Promise<StaffCasePreferencePreview>;
  apply(
    staffId: number,
    payload: StaffCasePreferenceApplyRequest,
    options?: StaffCasePreferenceCommandOptions,
  ): Promise<StaffCasePreferenceReceipt>;
}

function requireStaffId(staffId: number): void {
  if (!Number.isInteger(staffId) || staffId <= 0) {
    throw new RangeError('staffId 必須是正整數。');
  }
}

function requestOptions(options?: StaffCasePreferenceCommandOptions): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) {
    throw new ApiHttpError(
      401,
      'staff_case_preference_unauthenticated',
      '尚未登入，無法維護服務人員接案偏好。',
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

function decodePreview(raw: unknown, staffId: number): StaffCasePreferencePreview {
  const decoded = StaffCasePreferencePreviewResponseSchema.safeParse(raw);
  if (!decoded.success) {
    throw new ApiDecodeError(
      '服務人員接案偏好預覽回應結構異常。',
      decoded.error.issues.map((issue) => ({
        path: issue.path.join('.') || '(root)',
        message: issue.message,
        code: issue.code,
      })),
      raw,
    );
  }
  if (!decoded.data.success || decoded.data.data.staff_id !== staffId) {
    throw new ApiDecodeError(
      '服務人員接案偏好預覽 identity 或 success 狀態異常。',
      [],
      raw,
    );
  }
  return decoded.data.data;
}

function decodeReceipt(raw: unknown, staffId: number): StaffCasePreferenceReceipt {
  const decoded = StaffCasePreferenceReceiptResponseSchema.safeParse(raw);
  if (!decoded.success) {
    throw new ApiDecodeError(
      '服務人員接案偏好儲存回應結構異常。',
      decoded.error.issues.map((issue) => ({
        path: issue.path.join('.') || '(root)',
        message: issue.message,
        code: issue.code,
      })),
      raw,
    );
  }
  if (!decoded.data.success || decoded.data.data.staff_id !== staffId) {
    throw new ApiDecodeError(
      '服務人員接案偏好儲存 identity 或 success 狀態異常。',
      [],
      raw,
    );
  }
  return decoded.data.data;
}

class DefaultStaffCasePreferenceCommandClient implements StaffCasePreferenceCommandClient {
  public async preview(
    staffId: number,
    payload: StaffCasePreferencePreviewRequest,
    options?: StaffCasePreferenceCommandOptions,
  ): Promise<StaffCasePreferencePreview> {
    requireStaffId(staffId);
    const validated = StaffCasePreferencePreviewRequestSchema.parse(payload);
    const raw = await transport.post<unknown>(
      `/api/v1/staff/${staffId}/case-preference-summary/preview`,
      validated,
      requestOptions(options),
    );
    return decodePreview(raw, staffId);
  }

  public async apply(
    staffId: number,
    payload: StaffCasePreferenceApplyRequest,
    options?: StaffCasePreferenceCommandOptions,
  ): Promise<StaffCasePreferenceReceipt> {
    requireStaffId(staffId);
    const validated = StaffCasePreferenceApplyRequestSchema.parse(payload);
    const raw = await transport.post<unknown>(
      `/api/v1/staff/${staffId}/case-preference-summary/apply`,
      validated,
      requestOptions(options),
    );
    return decodeReceipt(raw, staffId);
  }
}

export function createStaffCasePreferenceCommandClient(): StaffCasePreferenceCommandClient {
  return new DefaultStaffCasePreferenceCommandClient();
}

export const staffCasePreferenceCommandClient = createStaffCasePreferenceCommandClient();
