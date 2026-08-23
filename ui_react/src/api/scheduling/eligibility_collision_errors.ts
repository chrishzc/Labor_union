/**
 * File: eligibility_collision_errors.ts
 * Description: 收斂 Scheduling 資格衝突查詢的 typed HTTP、解碼與網路錯誤。
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
  field_errors: z.array(z.strictObject({ field: z.string(), code: z.string(), message: z.string() })),
  domain_blockers: z.array(z.string()),
  retryable: z.boolean(),
  correlation_id: z.string(),
  current_version: z.number().int().nullable(),
});

export type SchedulingEligibilityCollisionErrorCode =
  | 'SCHEDULING_ELIGIBILITY_UNAUTHENTICATED'
  | 'SCHEDULING_ELIGIBILITY_VALIDATION'
  | 'SCHEDULING_ELIGIBILITY_NOT_FOUND'
  | 'SCHEDULING_ELIGIBILITY_CONFLICT'
  | 'SCHEDULING_ELIGIBILITY_UNAVAILABLE'
  | 'SCHEDULING_ELIGIBILITY_NETWORK'
  | 'SCHEDULING_ELIGIBILITY_TIMEOUT'
  | 'SCHEDULING_ELIGIBILITY_ABORTED';

export class SchedulingEligibilityCollisionError extends ApiError {
  public readonly name: string = 'SchedulingEligibilityCollisionError';
  public readonly code: SchedulingEligibilityCollisionErrorCode;
  public readonly status?: number;
  public readonly retryable: boolean;
  public readonly correlationId?: string;
  public readonly originalError?: unknown;

  public constructor(
    code: SchedulingEligibilityCollisionErrorCode,
    message: string,
    options?: { status?: number; retryable?: boolean; correlationId?: string; originalError?: unknown }
  ) {
    super(message);
    this.code = code;
    this.status = options?.status;
    this.retryable = options?.retryable ?? false;
    this.correlationId = options?.correlationId;
    this.originalError = options?.originalError;
  }
}

export class SchedulingEligibilityUnauthenticatedError extends SchedulingEligibilityCollisionError {
  public readonly name = 'SchedulingEligibilityUnauthenticatedError';
  public constructor(message = '請先完成管理員登入後再查詢資格與檔期衝突。') {
    super('SCHEDULING_ELIGIBILITY_UNAUTHENTICATED', message, { status: 401 });
  }
}

export class SchedulingEligibilityValidationError extends SchedulingEligibilityCollisionError {
  public readonly name = 'SchedulingEligibilityValidationError';
  public constructor(message: string, originalError?: unknown) {
    super('SCHEDULING_ELIGIBILITY_VALIDATION', message, { status: 422, originalError });
  }
}

export class SchedulingEligibilityAbortedError extends SchedulingEligibilityCollisionError {
  public readonly name = 'SchedulingEligibilityAbortedError';
  public constructor(message = '資格與檔期衝突查詢已取消。') {
    super('SCHEDULING_ELIGIBILITY_ABORTED', message);
  }
}

function typedPayload(raw: unknown) {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return null;
  const detail = Reflect.get(raw, 'detail');
  if (typeof detail !== 'object' || detail === null || Array.isArray(detail)) return null;
  const error = Reflect.get(detail, 'error');
  const parsed = TypedErrorSchema.safeParse(error);
  return parsed.success ? parsed.data : null;
}

export function mapSchedulingEligibilityCollisionError(error: unknown): SchedulingEligibilityCollisionError {
  if (error instanceof SchedulingEligibilityCollisionError) return error;
  if (error instanceof ApiAbortError) return new SchedulingEligibilityAbortedError(error.message);
  if (error instanceof ApiTimeoutError) return new SchedulingEligibilityCollisionError('SCHEDULING_ELIGIBILITY_TIMEOUT', error.message, { retryable: true, originalError: error });
  if (error instanceof ApiNetworkError) return new SchedulingEligibilityCollisionError('SCHEDULING_ELIGIBILITY_NETWORK', error.message, { retryable: true, originalError: error });
  if (error instanceof ApiDecodeError) return new SchedulingEligibilityValidationError(error.message, error);
  if (error instanceof ApiHttpError) {
    const payload = typedPayload(error.raw);
    const code = payload?.code ?? error.code;
    const message = payload?.message ?? error.message;
    const options = { status: error.status, retryable: payload?.retryable ?? error.retryable, correlationId: payload?.correlation_id, originalError: error };
    if (error.status === 401) return new SchedulingEligibilityUnauthenticatedError(message);
    if (error.status === 404) return new SchedulingEligibilityCollisionError('SCHEDULING_ELIGIBILITY_NOT_FOUND', message, options);
    if (error.status === 409) return new SchedulingEligibilityCollisionError('SCHEDULING_ELIGIBILITY_CONFLICT', message, options);
    if ([500, 502, 503, 504].includes(error.status)) return new SchedulingEligibilityCollisionError('SCHEDULING_ELIGIBILITY_UNAVAILABLE', message, options);
    return new SchedulingEligibilityValidationError(`[${code}] ${message}`, error);
  }
  return new SchedulingEligibilityCollisionError('SCHEDULING_ELIGIBILITY_NETWORK', extractErrorMessage(error), { retryable: true, originalError: error });
}
