/**
 * File: case_preference_summary_errors.ts
 * Description: 收斂 Staff case-preference summary 的 typed HTTP、解碼與傳輸錯誤。
 */
import { z } from 'zod';
import {
  ApiAbortError,
  ApiDecodeError,
  ApiError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
  extractErrorMessage,
} from '../shared/typed_errors';

const TypedErrorSchema = z.strictObject({
  category: z.enum(['validation', 'forbidden', 'not_found', 'domain_blocked', 'conflict', 'idempotency_mismatch', 'unavailable', 'internal']),
  code: z.string(),
  message: z.string(),
  field_errors: z.array(z.unknown()),
  domain_blockers: z.array(z.string()),
  retryable: z.boolean(),
  correlation_id: z.string(),
  current_version: z.number().int().nullable(),
});

export type StaffCasePreferenceSummaryErrorCode =
  | 'STAFF_CASE_PREFERENCE_UNAUTHENTICATED'
  | 'STAFF_CASE_PREFERENCE_VALIDATION'
  | 'STAFF_CASE_PREFERENCE_NOT_FOUND'
  | 'STAFF_CASE_PREFERENCE_UNAVAILABLE'
  | 'STAFF_CASE_PREFERENCE_NETWORK'
  | 'STAFF_CASE_PREFERENCE_TIMEOUT'
  | 'STAFF_CASE_PREFERENCE_ABORTED';

export class StaffCasePreferenceSummaryError extends ApiError {
  public readonly name: string = 'StaffCasePreferenceSummaryError';
  public readonly code: StaffCasePreferenceSummaryErrorCode;
  public readonly status?: number;
  public readonly retryable: boolean;
  public readonly correlationId?: string;
  public readonly originalError?: unknown;

  public constructor(code: StaffCasePreferenceSummaryErrorCode, message: string, options?: { status?: number; retryable?: boolean; correlationId?: string; originalError?: unknown }) {
    super(message);
    this.code = code;
    this.status = options?.status;
    this.retryable = options?.retryable ?? false;
    this.correlationId = options?.correlationId;
    this.originalError = options?.originalError;
  }
}

export class StaffCasePreferenceUnauthenticatedError extends StaffCasePreferenceSummaryError {
  public readonly name = 'StaffCasePreferenceUnauthenticatedError';
  public constructor(message = '請先完成管理員登入後再查詢接案偏好摘要。') {
    super('STAFF_CASE_PREFERENCE_UNAUTHENTICATED', message, { status: 401 });
  }
}

export class StaffCasePreferenceValidationError extends StaffCasePreferenceSummaryError {
  public readonly name = 'StaffCasePreferenceValidationError';
  public constructor(message: string, originalError?: unknown) {
    super('STAFF_CASE_PREFERENCE_VALIDATION', message, { status: 422, originalError });
  }
}

export class StaffCasePreferenceAbortedError extends StaffCasePreferenceSummaryError {
  public readonly name = 'StaffCasePreferenceAbortedError';
  public constructor(message = '接案偏好摘要查詢已取消。') {
    super('STAFF_CASE_PREFERENCE_ABORTED', message);
  }
}

function typedPayload(raw: unknown) {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return null;
  const detail = Reflect.get(raw, 'detail');
  if (typeof detail !== 'object' || detail === null || Array.isArray(detail)) return null;
  const parsed = TypedErrorSchema.safeParse(Reflect.get(detail, 'error'));
  return parsed.success ? parsed.data : null;
}

export function mapStaffCasePreferenceSummaryError(error: unknown): StaffCasePreferenceSummaryError {
  if (error instanceof StaffCasePreferenceSummaryError) return error;
  if (error instanceof ApiAbortError) return new StaffCasePreferenceAbortedError(error.message);
  if (error instanceof ApiTimeoutError) return new StaffCasePreferenceSummaryError('STAFF_CASE_PREFERENCE_TIMEOUT', error.message, { retryable: true, originalError: error });
  if (error instanceof ApiNetworkError) return new StaffCasePreferenceSummaryError('STAFF_CASE_PREFERENCE_NETWORK', error.message, { retryable: true, originalError: error });
  if (error instanceof ApiDecodeError) return new StaffCasePreferenceValidationError(error.message, error);
  if (error instanceof ApiHttpError) {
    const payload = typedPayload(error.raw);
    const message = payload?.message ?? error.message;
    const options = { status: error.status, retryable: payload?.retryable ?? error.retryable, correlationId: payload?.correlation_id, originalError: error };
    if (error.status === 401) return new StaffCasePreferenceUnauthenticatedError(message);
    if (error.status === 404) return new StaffCasePreferenceSummaryError('STAFF_CASE_PREFERENCE_NOT_FOUND', message, options);
    if ([500, 502, 503, 504].includes(error.status)) return new StaffCasePreferenceSummaryError('STAFF_CASE_PREFERENCE_UNAVAILABLE', message, options);
    return new StaffCasePreferenceValidationError(message, error);
  }
  return new StaffCasePreferenceSummaryError('STAFF_CASE_PREFERENCE_NETWORK', extractErrorMessage(error), { retryable: true, originalError: error });
}
