/**
 * File: holiday_errors.ts
 * Description: 將國定假日 API 的認證、契約、HTTP、網路與 outcome_unknown 錯誤型別化。
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

export const HolidayFieldErrorSchema = z.strictObject({
  field: z.string(),
  code: z.string(),
  message: z.string(),
});

export const HolidayTypedErrorSchema = z.strictObject({
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
  code: z.string().min(1),
  message: z.string().min(1),
  field_errors: z.array(HolidayFieldErrorSchema),
  domain_blockers: z.array(z.string()),
  retryable: z.boolean(),
  correlation_id: z.string().min(1),
  current_version: z.number().int().nullable(),
});

export const HolidayTypedErrorResponseSchema = z.strictObject({
  detail: z.strictObject({
    error: HolidayTypedErrorSchema,
  }),
});

export type HolidayErrorCategory = z.infer<typeof HolidayTypedErrorSchema>['category'];
export type HolidayFieldError = z.infer<typeof HolidayFieldErrorSchema>;
export type HolidayTypedError = z.infer<typeof HolidayTypedErrorSchema>;

export type HolidayErrorCode =
  | 'HOLIDAY_UNAUTHENTICATED'
  | 'HOLIDAY_FORBIDDEN'
  | 'HOLIDAY_NOT_FOUND'
  | 'HOLIDAY_VALIDATION'
  | 'HOLIDAY_CONFLICT'
  | 'HOLIDAY_IDEMPOTENCY_MISMATCH'
  | 'HOLIDAY_UNAVAILABLE'
  | 'HOLIDAY_OUTCOME_UNKNOWN'
  | 'HOLIDAY_CONTRACT'
  | 'HOLIDAY_NETWORK'
  | 'HOLIDAY_TIMEOUT'
  | 'HOLIDAY_ABORTED';

export interface HolidayErrorOptions {
  status?: number;
  publicCode?: string;
  category?: HolidayErrorCategory;
  correlationId?: string;
  retryable?: boolean;
  outcomeUnknown?: boolean;
  idempotencyKey?: string;
  fieldErrors?: readonly HolidayFieldError[];
  domainBlockers?: readonly string[];
  currentVersion?: number | null;
  originalError?: unknown;
  rawPayload?: unknown;
}

export class HolidayError extends ApiError {
  public readonly name: string = 'HolidayError';
  public readonly code: HolidayErrorCode;
  public readonly status?: number;
  public readonly publicCode?: string;
  public readonly category?: HolidayErrorCategory;
  public readonly correlationId?: string;
  public readonly retryable: boolean;
  public readonly outcomeUnknown: boolean;
  public readonly idempotencyKey?: string;
  public readonly fieldErrors: readonly HolidayFieldError[];
  public readonly domainBlockers: readonly string[];
  public readonly currentVersion: number | null;
  public readonly originalError?: unknown;
  public readonly rawPayload?: unknown;

  constructor(code: HolidayErrorCode, message: string, options: HolidayErrorOptions = {}) {
    super(message);
    this.code = code;
    this.status = options.status;
    this.publicCode = options.publicCode;
    this.category = options.category;
    this.correlationId = options.correlationId;
    this.retryable = options.retryable ?? false;
    this.outcomeUnknown = options.outcomeUnknown ?? false;
    this.idempotencyKey = options.idempotencyKey;
    this.fieldErrors = options.fieldErrors ?? [];
    this.domainBlockers = options.domainBlockers ?? [];
    this.currentVersion = options.currentVersion ?? null;
    this.originalError = options.originalError;
    this.rawPayload = options.rawPayload;
  }
}

export class HolidayUnauthenticatedError extends HolidayError {
  public readonly name = 'HolidayUnauthenticatedError';

  constructor(message = '請先完成管理員登入後再處理國定假日。') {
    super('HOLIDAY_UNAUTHENTICATED', message, { category: 'forbidden', status: 401 });
  }
}

export class HolidayForbiddenError extends HolidayError {
  public readonly name = 'HolidayForbiddenError';

  constructor(message: string, options: HolidayErrorOptions = {}) {
    super('HOLIDAY_FORBIDDEN', message, { ...options, category: 'forbidden', status: options.status ?? 403 });
  }
}

export class HolidayNotFoundError extends HolidayError {
  public readonly name = 'HolidayNotFoundError';

  constructor(message: string, options: HolidayErrorOptions = {}) {
    super('HOLIDAY_NOT_FOUND', message, { ...options, category: 'not_found', status: options.status ?? 404 });
  }
}

export class HolidayValidationError extends HolidayError {
  public readonly name = 'HolidayValidationError';

  constructor(message: string, originalError?: unknown) {
    super('HOLIDAY_VALIDATION', message, {
      category: 'validation',
      status: 422,
      originalError,
    });
  }
}

export class HolidayConflictError extends HolidayError {
  public readonly name = 'HolidayConflictError';

  constructor(message: string, options: HolidayErrorOptions = {}) {
    super('HOLIDAY_CONFLICT', message, { ...options, category: 'conflict', status: options.status ?? 409 });
  }
}

export class HolidayIdempotencyMismatchError extends HolidayError {
  public readonly name = 'HolidayIdempotencyMismatchError';

  constructor(message: string, options: HolidayErrorOptions = {}) {
    super('HOLIDAY_IDEMPOTENCY_MISMATCH', message, {
      ...options,
      category: 'idempotency_mismatch',
      status: options.status ?? 409,
    });
  }
}

export class HolidayUnavailableError extends HolidayError {
  public readonly name = 'HolidayUnavailableError';

  constructor(message: string, options: HolidayErrorOptions = {}) {
    super('HOLIDAY_UNAVAILABLE', message, {
      ...options,
      category: 'unavailable',
      status: options.status ?? 503,
      retryable: options.retryable ?? true,
    });
  }
}

export class HolidayOutcomeUnknownError extends HolidayError {
  public readonly name = 'HolidayOutcomeUnknownError';

  constructor(message: string, options: HolidayErrorOptions = {}) {
    super('HOLIDAY_OUTCOME_UNKNOWN', message, {
      ...options,
      category: 'unavailable',
      status: options.status ?? 503,
      retryable: options.retryable ?? true,
      outcomeUnknown: true,
    });
  }
}

export class HolidayContractError extends HolidayError {
  public readonly name = 'HolidayContractError';

  constructor(message: string, originalError?: unknown) {
    super('HOLIDAY_CONTRACT', message, { originalError, status: 422 });
  }
}

export class HolidayNetworkError extends HolidayError {
  public readonly name = 'HolidayNetworkError';

  constructor(message: string, originalError?: unknown, options: HolidayErrorOptions = {}) {
    super('HOLIDAY_NETWORK', message, { ...options, retryable: true, originalError });
  }
}

export class HolidayTimeoutError extends HolidayError {
  public readonly name = 'HolidayTimeoutError';

  constructor(message: string, originalError?: unknown, options: HolidayErrorOptions = {}) {
    super('HOLIDAY_TIMEOUT', message, { ...options, retryable: true, originalError });
  }
}

export class HolidayAbortedError extends HolidayError {
  public readonly name = 'HolidayAbortedError';

  constructor(message = '國定假日請求已取消。', originalError?: unknown) {
    super('HOLIDAY_ABORTED', message, { originalError });
  }
}

function typedErrorPayload(raw: unknown): HolidayTypedError | null {
  const parsed = HolidayTypedErrorResponseSchema.safeParse(raw);
  return parsed.success ? parsed.data.detail.error : null;
}

function typedOptions(error: ApiHttpError, payload: HolidayTypedError): HolidayErrorOptions {
  return {
    status: error.status,
    publicCode: payload.code,
    category: payload.category,
    correlationId: payload.correlation_id,
    retryable: payload.retryable,
    fieldErrors: payload.field_errors,
    domainBlockers: payload.domain_blockers,
    currentVersion: payload.current_version,
    rawPayload: error.raw,
    originalError: error,
  };
}

export function mapHolidayError(
  error: unknown,
  operation: 'query' | 'preview' | 'apply' = 'query',
  idempotencyKey?: string,
): HolidayError {
  if (error instanceof HolidayError) return error;
  if (error instanceof ApiAbortError) return new HolidayAbortedError(error.message, error);
  if (error instanceof ApiTimeoutError) {
    return operation === 'apply'
      ? new HolidayOutcomeUnknownError(error.message, { idempotencyKey, originalError: error })
      : new HolidayTimeoutError(error.message, error);
  }
  if (error instanceof ApiDecodeError) return new HolidayContractError(error.message, error);
  if (error instanceof ApiNetworkError) {
    return operation === 'apply'
      ? new HolidayOutcomeUnknownError(error.message, { idempotencyKey, originalError: error })
      : new HolidayNetworkError(error.message, error);
  }
  if (error instanceof ApiHttpError) {
    const payload = typedErrorPayload(error);
    const options = payload
      ? { ...typedOptions(error, payload), idempotencyKey }
      : {
        status: error.status,
        publicCode: error.code,
        retryable: error.retryable,
        rawPayload: error.raw,
        originalError: error,
        idempotencyKey,
      };
    if (operation === 'apply' && [502, 503, 504].includes(error.status)) {
      return new HolidayOutcomeUnknownError(error.message, options);
    }
    if (payload?.category === 'idempotency_mismatch' || error.status === 409 && payload?.code.includes('idempotency')) {
      return new HolidayIdempotencyMismatchError(error.message, options);
    }
    if (error.status === 401) return new HolidayUnauthenticatedError(error.message);
    if (error.status === 403) return new HolidayForbiddenError(error.message, options);
    if (error.status === 404) return new HolidayNotFoundError(error.message, options);
    if (error.status === 409) return new HolidayConflictError(error.message, options);
    if ([502, 503, 504].includes(error.status)) return new HolidayUnavailableError(error.message, options);
    return new HolidayValidationError(error.message, error);
  }
  const message = extractErrorMessage(error);
  return operation === 'apply'
    ? new HolidayOutcomeUnknownError(message, { idempotencyKey, originalError: error })
    : new HolidayNetworkError(message, error);
}

export {
  ApiAbortError,
  ApiDecodeError,
  ApiError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
};
