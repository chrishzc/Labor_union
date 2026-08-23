/**
 * File: qualification_master_errors.ts
 * Description: 收斂 Staff qualification master 的 typed HTTP、解碼與資料缺口錯誤。
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

export type StaffQualificationMasterErrorCode =
  | 'STAFF_QUALIFICATION_UNAUTHENTICATED'
  | 'STAFF_QUALIFICATION_VALIDATION'
  | 'STAFF_QUALIFICATION_NOT_FOUND'
  | 'STAFF_QUALIFICATION_UNAVAILABLE'
  | 'STAFF_QUALIFICATION_NETWORK'
  | 'STAFF_QUALIFICATION_TIMEOUT'
  | 'STAFF_QUALIFICATION_ABORTED';

export class StaffQualificationMasterError extends ApiError {
  public readonly name: string = 'StaffQualificationMasterError';
  public readonly code: StaffQualificationMasterErrorCode;
  public readonly status?: number;
  public readonly retryable: boolean;
  public readonly correlationId?: string;
  public readonly originalError?: unknown;

  public constructor(code: StaffQualificationMasterErrorCode, message: string, options?: { status?: number; retryable?: boolean; correlationId?: string; originalError?: unknown }) {
    super(message);
    this.code = code;
    this.status = options?.status;
    this.retryable = options?.retryable ?? false;
    this.correlationId = options?.correlationId;
    this.originalError = options?.originalError;
  }
}

export class StaffQualificationUnauthenticatedError extends StaffQualificationMasterError {
  public readonly name = 'StaffQualificationUnauthenticatedError';
  public constructor(message = '請先完成管理員登入後再查詢資格主檔。') {
    super('STAFF_QUALIFICATION_UNAUTHENTICATED', message, { status: 401 });
  }
}

export class StaffQualificationValidationError extends StaffQualificationMasterError {
  public readonly name = 'StaffQualificationValidationError';
  public constructor(message: string, originalError?: unknown) {
    super('STAFF_QUALIFICATION_VALIDATION', message, { status: 422, originalError });
  }
}

export class StaffQualificationAbortedError extends StaffQualificationMasterError {
  public readonly name = 'StaffQualificationAbortedError';
  public constructor(message = '資格主檔查詢已取消。') {
    super('STAFF_QUALIFICATION_ABORTED', message);
  }
}

function typedPayload(raw: unknown) {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return null;
  const detail = Reflect.get(raw, 'detail');
  if (typeof detail !== 'object' || detail === null || Array.isArray(detail)) return null;
  const parsed = TypedErrorSchema.safeParse(Reflect.get(detail, 'error'));
  return parsed.success ? parsed.data : null;
}

export function mapStaffQualificationMasterError(error: unknown): StaffQualificationMasterError {
  if (error instanceof StaffQualificationMasterError) return error;
  if (error instanceof ApiAbortError) return new StaffQualificationAbortedError(error.message);
  if (error instanceof ApiTimeoutError) return new StaffQualificationMasterError('STAFF_QUALIFICATION_TIMEOUT', error.message, { retryable: true, originalError: error });
  if (error instanceof ApiNetworkError) return new StaffQualificationMasterError('STAFF_QUALIFICATION_NETWORK', error.message, { retryable: true, originalError: error });
  if (error instanceof ApiDecodeError) return new StaffQualificationValidationError(error.message, error);
  if (error instanceof ApiHttpError) {
    const payload = typedPayload(error.raw);
    const message = payload?.message ?? error.message;
    const options = { status: error.status, retryable: payload?.retryable ?? error.retryable, correlationId: payload?.correlation_id, originalError: error };
    if (error.status === 401) return new StaffQualificationUnauthenticatedError(message);
    if (error.status === 404) return new StaffQualificationMasterError('STAFF_QUALIFICATION_NOT_FOUND', message, options);
    if ([500, 502, 503, 504].includes(error.status)) return new StaffQualificationMasterError('STAFF_QUALIFICATION_UNAVAILABLE', message, options);
    return new StaffQualificationValidationError(message, error);
  }
  return new StaffQualificationMasterError('STAFF_QUALIFICATION_NETWORK', extractErrorMessage(error), { retryable: true, originalError: error });
}
