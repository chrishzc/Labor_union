/**
 * File: staff_lifecycle_errors.ts
 * Description: 收斂 Staff lifecycle 的 typed HTTP、解碼、認證與重試錯誤。
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

export const StaffLifecycleFieldErrorSchema = z
  .strictObject({
    field: z.string(),
    code: z.string(),
    message: z.string(),
  });

export const StaffLifecycleTypedErrorPayloadSchema = z
  .strictObject({
    category: z.enum([
      'validation',
      'forbidden',
      'not_found',
      'domain_blocked',
      'conflict',
      'idempotency_mismatch',
      'unavailable',
      'internal',
    ]),
    code: z.string(),
    message: z.string(),
    correlation_id: z.string(),
    field_errors: z.array(StaffLifecycleFieldErrorSchema),
    domain_blockers: z.array(z.string()),
    retryable: z.boolean(),
    current_version: z.number().int().nullable(),
  });

export type StaffLifecycleFieldError = z.infer<typeof StaffLifecycleFieldErrorSchema>;
export type StaffLifecycleTypedErrorPayload = z.infer<
  typeof StaffLifecycleTypedErrorPayloadSchema
>;
export type StaffLifecycleErrorCategory = StaffLifecycleTypedErrorPayload['category'];

export interface StaffLifecycleErrorParams {
  status?: number;
  category: StaffLifecycleErrorCategory;
  code: string;
  message: string;
  correlationId?: string;
  retryable?: boolean;
  fieldErrors?: readonly StaffLifecycleFieldError[];
  domainBlockers?: readonly string[];
  currentVersion?: number | null;
  rawPayload?: unknown;
  originalError?: unknown;
}

export class StaffLifecycleError extends ApiError {
  public readonly name: string = 'StaffLifecycleError';
  public readonly status?: number;
  public readonly category: StaffLifecycleErrorCategory;
  public readonly code: string;
  public readonly correlationId?: string;
  public readonly retryable: boolean;
  public readonly fieldErrors: readonly StaffLifecycleFieldError[];
  public readonly domainBlockers: readonly string[];
  public readonly currentVersion: number | null;
  public readonly rawPayload?: unknown;
  public readonly originalError?: unknown;

  constructor(params: StaffLifecycleErrorParams) {
    super(params.message);
    this.status = params.status;
    this.category = params.category;
    this.code = params.code;
    this.correlationId = params.correlationId;
    this.retryable = params.retryable ?? false;
    this.fieldErrors = params.fieldErrors ?? [];
    this.domainBlockers = params.domainBlockers ?? [];
    this.currentVersion = params.currentVersion ?? null;
    this.rawPayload = params.rawPayload;
    this.originalError = params.originalError;
  }
}

export class StaffLifecycleUnauthenticatedError extends StaffLifecycleError {
  public override readonly name = 'StaffLifecycleUnauthenticatedError';

  constructor(message = '請先完成管理員登入後再操作 Staff lifecycle。') {
    super({ category: 'forbidden', code: 'STAFF_LIFECYCLE_UNAUTHENTICATED', message, status: 401 });
  }
}

export class StaffLifecycleForbiddenError extends StaffLifecycleError {
  public override readonly name = 'StaffLifecycleForbiddenError';

  constructor(params: Omit<StaffLifecycleErrorParams, 'category'>) {
    super({ ...params, category: 'forbidden', status: params.status ?? 403 });
  }
}

export class StaffLifecycleValidationError extends StaffLifecycleError {
  public override readonly name = 'StaffLifecycleValidationError';

  constructor(message: string, originalError?: unknown) {
    super({
      category: 'validation',
      code: 'STAFF_LIFECYCLE_VALIDATION',
      message,
      status: 422,
      originalError,
    });
  }
}

export class StaffLifecycleNotFoundError extends StaffLifecycleError {
  public override readonly name = 'StaffLifecycleNotFoundError';

  constructor(params: Omit<StaffLifecycleErrorParams, 'category'>) {
    super({ ...params, category: 'not_found', status: params.status ?? 404 });
  }
}

export class StaffLifecycleConflictError extends StaffLifecycleError {
  public override readonly name = 'StaffLifecycleConflictError';

  constructor(params: Omit<StaffLifecycleErrorParams, 'category'>) {
    super({ ...params, category: 'conflict', status: params.status ?? 409 });
  }
}

export class StaffLifecycleUnavailableError extends StaffLifecycleError {
  public override readonly name = 'StaffLifecycleUnavailableError';

  constructor(params: Omit<StaffLifecycleErrorParams, 'category'>) {
    super({
      ...params,
      category: 'unavailable',
      status: params.status ?? 503,
      retryable: params.retryable ?? true,
    });
  }
}

export class StaffLifecycleAbortedError extends StaffLifecycleError {
  public override readonly name = 'StaffLifecycleAbortedError';

  constructor(message = 'Staff lifecycle 請求已取消。') {
    super({ category: 'validation', code: 'STAFF_LIFECYCLE_ABORTED', message });
  }
}

function readProperty(value: unknown, key: string): unknown {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return undefined;
  return Reflect.get(value, key);
}

function decodeTypedPayload(raw: unknown): StaffLifecycleTypedErrorPayload | null {
  const detail = readProperty(raw, 'detail');
  const error = readProperty(detail, 'error');
  const parsed = StaffLifecycleTypedErrorPayloadSchema.safeParse(error);
  return parsed.success ? parsed.data : null;
}

function mapTypedError(
  error: ApiHttpError,
  payload: StaffLifecycleTypedErrorPayload
): StaffLifecycleError {
  const params: StaffLifecycleErrorParams = {
    status: error.status,
    category: payload.category,
    code: payload.code,
    message: payload.message,
    correlationId: payload.correlation_id,
    retryable: payload.retryable,
    fieldErrors: payload.field_errors,
    domainBlockers: payload.domain_blockers,
    currentVersion: payload.current_version,
    rawPayload: error.raw,
  };
  switch (payload.category) {
    case 'validation':
      return new StaffLifecycleValidationError(payload.message, error);
    case 'forbidden':
      return error.status === 401
        ? new StaffLifecycleUnauthenticatedError(payload.message)
        : new StaffLifecycleForbiddenError(params);
    case 'not_found':
      return new StaffLifecycleNotFoundError(params);
    case 'conflict':
    case 'idempotency_mismatch':
    case 'domain_blocked':
      return new StaffLifecycleConflictError(params);
    case 'unavailable':
      return new StaffLifecycleUnavailableError(params);
    case 'internal':
      return new StaffLifecycleError(params);
  }
}

export function mapStaffLifecycleError(error: unknown): StaffLifecycleError {
  if (error instanceof StaffLifecycleError) return error;
  if (error instanceof ApiAbortError) return new StaffLifecycleAbortedError(error.message);
  if (error instanceof ApiTimeoutError) {
    return new StaffLifecycleUnavailableError({
      code: 'STAFF_LIFECYCLE_TIMEOUT',
      message: error.message,
      retryable: true,
      originalError: error,
    });
  }
  if (error instanceof ApiNetworkError) {
    return new StaffLifecycleUnavailableError({
      code: 'STAFF_LIFECYCLE_NETWORK',
      message: error.message,
      retryable: true,
      originalError: error,
    });
  }
  if (error instanceof ApiDecodeError) {
    return new StaffLifecycleValidationError(error.message, error);
  }
  if (error instanceof ApiHttpError) {
    const payload = decodeTypedPayload(error.raw);
    if (payload) return mapTypedError(error, payload);
    if (error.status === 401) return new StaffLifecycleUnauthenticatedError(error.message);
    if (error.status === 403) {
      return new StaffLifecycleForbiddenError({
        code: error.code,
        message: error.message,
        retryable: error.retryable,
        rawPayload: error.raw,
      });
    }
    if (error.status === 404) {
      return new StaffLifecycleNotFoundError({
        code: error.code,
        message: error.message,
        retryable: error.retryable,
        rawPayload: error.raw,
      });
    }
    if (error.status === 409) {
      return new StaffLifecycleConflictError({
        code: error.code,
        message: error.message,
        retryable: error.retryable,
        rawPayload: error.raw,
      });
    }
    if ([502, 503, 504].includes(error.status)) {
      return new StaffLifecycleUnavailableError({
        code: error.code,
        message: error.message,
        retryable: error.retryable,
        rawPayload: error.raw,
      });
    }
    return new StaffLifecycleValidationError(error.message, error);
  }
  return new StaffLifecycleError({
    category: 'internal',
    code: 'STAFF_LIFECYCLE_UNKNOWN',
    message: extractErrorMessage(error),
    originalError: error,
  });
}

export {
  ApiAbortError,
  ApiDecodeError,
  ApiError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
};
