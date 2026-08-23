/**
 * File: staff_availability_errors.ts
 * Description: 收斂 Availability 的 typed HTTP、解碼、認證與重試錯誤。
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

export const StaffAvailabilityFieldErrorSchema = z
  .strictObject({
    field: z.string(),
    code: z.string(),
    message: z.string(),
  });

export const StaffAvailabilityTypedErrorPayloadSchema = z
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
    field_errors: z.array(StaffAvailabilityFieldErrorSchema),
    domain_blockers: z.array(z.string()),
    retryable: z.boolean(),
    current_version: z.number().int().nullable(),
  });

export type StaffAvailabilityFieldError = z.infer<typeof StaffAvailabilityFieldErrorSchema>;
export type StaffAvailabilityTypedErrorPayload = z.infer<
  typeof StaffAvailabilityTypedErrorPayloadSchema
>;
export type StaffAvailabilityErrorCategory = StaffAvailabilityTypedErrorPayload['category'];

export interface StaffAvailabilityErrorParams {
  status?: number;
  category: StaffAvailabilityErrorCategory;
  code: string;
  message: string;
  correlationId?: string;
  retryable?: boolean;
  fieldErrors?: readonly StaffAvailabilityFieldError[];
  domainBlockers?: readonly string[];
  currentVersion?: number | null;
  rawPayload?: unknown;
  originalError?: unknown;
}

export class StaffAvailabilityError extends ApiError {
  public readonly name: string = 'StaffAvailabilityError';
  public readonly status?: number;
  public readonly category: StaffAvailabilityErrorCategory;
  public readonly code: string;
  public readonly correlationId?: string;
  public readonly retryable: boolean;
  public readonly fieldErrors: readonly StaffAvailabilityFieldError[];
  public readonly domainBlockers: readonly string[];
  public readonly currentVersion: number | null;
  public readonly rawPayload?: unknown;
  public readonly originalError?: unknown;

  constructor(params: StaffAvailabilityErrorParams) {
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

export class StaffAvailabilityUnauthenticatedError extends StaffAvailabilityError {
  public override readonly name = 'StaffAvailabilityUnauthenticatedError';

  constructor(message = '請先完成管理員登入後再操作不可服務期間。') {
    super({ category: 'forbidden', code: 'STAFF_AVAILABILITY_UNAUTHENTICATED', message, status: 401 });
  }
}

export class StaffAvailabilityForbiddenError extends StaffAvailabilityError {
  public override readonly name = 'StaffAvailabilityForbiddenError';

  constructor(params: Omit<StaffAvailabilityErrorParams, 'category'>) {
    super({ ...params, category: 'forbidden', status: params.status ?? 403 });
  }
}

export class StaffAvailabilityValidationError extends StaffAvailabilityError {
  public override readonly name = 'StaffAvailabilityValidationError';

  constructor(message: string, originalError?: unknown) {
    super({
      category: 'validation',
      code: 'STAFF_AVAILABILITY_VALIDATION',
      message,
      status: 422,
      originalError,
    });
  }
}

export class StaffAvailabilityNotFoundError extends StaffAvailabilityError {
  public override readonly name = 'StaffAvailabilityNotFoundError';

  constructor(params: Omit<StaffAvailabilityErrorParams, 'category'>) {
    super({ ...params, category: 'not_found', status: params.status ?? 404 });
  }
}

export class StaffAvailabilityConflictError extends StaffAvailabilityError {
  public override readonly name = 'StaffAvailabilityConflictError';

  constructor(params: Omit<StaffAvailabilityErrorParams, 'category'>) {
    super({ ...params, category: 'conflict', status: params.status ?? 409 });
  }
}

export class StaffAvailabilityUnavailableError extends StaffAvailabilityError {
  public override readonly name = 'StaffAvailabilityUnavailableError';

  constructor(params: Omit<StaffAvailabilityErrorParams, 'category'>) {
    super({
      ...params,
      category: 'unavailable',
      status: params.status ?? 503,
      retryable: params.retryable ?? true,
    });
  }
}

export class StaffAvailabilityAbortedError extends StaffAvailabilityError {
  public override readonly name = 'StaffAvailabilityAbortedError';

  constructor(message = '不可服務期間請求已取消。') {
    super({ category: 'validation', code: 'STAFF_AVAILABILITY_ABORTED', message });
  }
}

function readProperty(value: unknown, key: string): unknown {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return undefined;
  return Reflect.get(value, key);
}

function decodeTypedPayload(raw: unknown): StaffAvailabilityTypedErrorPayload | null {
  const detail = readProperty(raw, 'detail');
  const error = readProperty(detail, 'error');
  const parsed = StaffAvailabilityTypedErrorPayloadSchema.safeParse(error);
  return parsed.success ? parsed.data : null;
}

function mapTypedError(
  error: ApiHttpError,
  payload: StaffAvailabilityTypedErrorPayload
): StaffAvailabilityError {
  const params: StaffAvailabilityErrorParams = {
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
      return new StaffAvailabilityValidationError(payload.message, error);
    case 'forbidden':
      return error.status === 401
        ? new StaffAvailabilityUnauthenticatedError(payload.message)
        : new StaffAvailabilityForbiddenError(params);
    case 'not_found':
      return new StaffAvailabilityNotFoundError(params);
    case 'conflict':
    case 'idempotency_mismatch':
    case 'domain_blocked':
      return new StaffAvailabilityConflictError(params);
    case 'unavailable':
      return new StaffAvailabilityUnavailableError(params);
    case 'internal':
      return new StaffAvailabilityError(params);
  }
}

export function mapStaffAvailabilityError(error: unknown): StaffAvailabilityError {
  if (error instanceof StaffAvailabilityError) return error;
  if (error instanceof ApiAbortError) return new StaffAvailabilityAbortedError(error.message);
  if (error instanceof ApiTimeoutError) {
    return new StaffAvailabilityUnavailableError({
      code: 'STAFF_AVAILABILITY_TIMEOUT',
      message: error.message,
      retryable: true,
      originalError: error,
    });
  }
  if (error instanceof ApiNetworkError) {
    return new StaffAvailabilityUnavailableError({
      code: 'STAFF_AVAILABILITY_NETWORK',
      message: error.message,
      retryable: true,
      originalError: error,
    });
  }
  if (error instanceof ApiDecodeError) {
    return new StaffAvailabilityValidationError(error.message, error);
  }
  if (error instanceof ApiHttpError) {
    const payload = decodeTypedPayload(error.raw);
    if (payload) return mapTypedError(error, payload);
    if (error.status === 401) return new StaffAvailabilityUnauthenticatedError(error.message);
    if (error.status === 403) {
      return new StaffAvailabilityForbiddenError({
        code: error.code,
        message: error.message,
        retryable: error.retryable,
        rawPayload: error.raw,
      });
    }
    if (error.status === 404) {
      return new StaffAvailabilityNotFoundError({
        code: error.code,
        message: error.message,
        retryable: error.retryable,
        rawPayload: error.raw,
      });
    }
    if (error.status === 409) {
      return new StaffAvailabilityConflictError({
        code: error.code,
        message: error.message,
        retryable: error.retryable,
        rawPayload: error.raw,
      });
    }
    if ([502, 503, 504].includes(error.status)) {
      return new StaffAvailabilityUnavailableError({
        code: error.code,
        message: error.message,
        retryable: error.retryable,
        rawPayload: error.raw,
      });
    }
    return new StaffAvailabilityValidationError(error.message, error);
  }
  return new StaffAvailabilityError({
    category: 'internal',
    code: 'STAFF_AVAILABILITY_UNKNOWN',
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
