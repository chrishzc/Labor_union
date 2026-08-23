/**
 * File: staff_preferences_errors.ts
 * Description: 將 Staff 偏好傳輸、認證、解碼與 Global typed error 收斂為 bounded errors。
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

export type StaffPreferencesErrorCode =
  | 'STAFF_PREFERENCES_UNAUTHENTICATED'
  | 'STAFF_PREFERENCES_FORBIDDEN'
  | 'STAFF_PREFERENCES_NOT_FOUND'
  | 'STAFF_PREFERENCES_VALIDATION'
  | 'STAFF_PREFERENCES_CONFLICT'
  | 'STAFF_PREFERENCES_UNAVAILABLE'
  | 'STAFF_PREFERENCES_NETWORK'
  | 'STAFF_PREFERENCES_TIMEOUT'
  | 'STAFF_PREFERENCES_ABORTED';

const GlobalFieldErrorSchema = z.strictObject({
  field: z.string(),
  code: z.string(),
  message: z.string(),
});

export const StaffPreferencesGlobalErrorEnvelopeSchema = z.strictObject({
  detail: z.strictObject({
    error: z.strictObject({
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
      field_errors: z.array(GlobalFieldErrorSchema),
      domain_blockers: z.array(z.string()),
      retryable: z.boolean(),
      correlation_id: z.string(),
      current_version: z.number().int().nullable(),
    }),
  }),
});

type StaffPreferencesGlobalError = z.infer<
  typeof StaffPreferencesGlobalErrorEnvelopeSchema
>['detail']['error'];

export class StaffPreferencesError extends ApiError {
  public readonly name: string = 'StaffPreferencesError';
  public readonly code: StaffPreferencesErrorCode;
  public readonly publicCode?: string;
  public readonly correlationId?: string;
  public readonly currentVersion: number | null;
  public readonly domainBlockers: readonly string[];
  public readonly fieldErrors: readonly {
    field: string;
    code: string;
    message: string;
  }[];
  public readonly status?: number;
  public readonly retryable: boolean;
  public readonly originalError?: unknown;

  constructor(
    code: StaffPreferencesErrorCode,
    message: string,
    options?: {
      publicCode?: string;
      correlationId?: string;
      currentVersion?: number | null;
      domainBlockers?: readonly string[];
      fieldErrors?: readonly {
        field: string;
        code: string;
        message: string;
      }[];
      status?: number;
      retryable?: boolean;
      originalError?: unknown;
    }
  ) {
    super(message);
    this.code = code;
    this.publicCode = options?.publicCode;
    this.correlationId = options?.correlationId;
    this.currentVersion = options?.currentVersion ?? null;
    this.domainBlockers = options?.domainBlockers ?? [];
    this.fieldErrors = options?.fieldErrors ?? [];
    this.status = options?.status;
    this.retryable = options?.retryable ?? false;
    this.originalError = options?.originalError;
  }
}

export class StaffPreferencesUnauthenticatedError extends StaffPreferencesError {
  public override readonly name = 'StaffPreferencesUnauthenticatedError';

  constructor(
    message = '請先完成管理員登入後再查詢月嫂偏好。',
    options?: ConstructorParameters<typeof StaffPreferencesError>[2],
  ) {
    super('STAFF_PREFERENCES_UNAUTHENTICATED', message, { ...options, status: 401 });
  }
}

export class StaffPreferencesForbiddenError extends StaffPreferencesError {
  public override readonly name = 'StaffPreferencesForbiddenError';

  constructor(
    message = '目前帳號無法存取月嫂偏好。',
    options?: ConstructorParameters<typeof StaffPreferencesError>[2],
  ) {
    super('STAFF_PREFERENCES_FORBIDDEN', message, { ...options, status: 403 });
  }
}

export class StaffPreferencesNotFoundError extends StaffPreferencesError {
  public override readonly name = 'StaffPreferencesNotFoundError';

  constructor(
    message = '查無指定服務人員或偏好資料。',
    options?: ConstructorParameters<typeof StaffPreferencesError>[2],
  ) {
    super('STAFF_PREFERENCES_NOT_FOUND', message, { ...options, status: 404 });
  }
}

export class StaffPreferencesValidationError extends StaffPreferencesError {
  public override readonly name = 'StaffPreferencesValidationError';

  constructor(message: string, options?: ConstructorParameters<typeof StaffPreferencesError>[2]) {
    super('STAFF_PREFERENCES_VALIDATION', message, { ...options, status: 422 });
  }
}

export class StaffPreferencesConflictError extends StaffPreferencesError {
  public override readonly name = 'StaffPreferencesConflictError';

  constructor(message: string, options?: ConstructorParameters<typeof StaffPreferencesError>[2]) {
    super('STAFF_PREFERENCES_CONFLICT', message, { ...options, status: 409 });
  }
}

export class StaffPreferencesUnavailableError extends StaffPreferencesError {
  public override readonly name = 'StaffPreferencesUnavailableError';

  constructor(message: string, options?: ConstructorParameters<typeof StaffPreferencesError>[2]) {
    super('STAFF_PREFERENCES_UNAVAILABLE', message, {
      ...options,
      retryable: options?.retryable ?? true,
    });
  }
}

export class StaffPreferencesNetworkError extends StaffPreferencesError {
  public override readonly name = 'StaffPreferencesNetworkError';

  constructor(message: string, originalError?: unknown) {
    super('STAFF_PREFERENCES_NETWORK', message, {
      retryable: true,
      originalError,
    });
  }
}

export class StaffPreferencesTimeoutError extends StaffPreferencesError {
  public override readonly name = 'StaffPreferencesTimeoutError';

  constructor(message: string, originalError?: unknown) {
    super('STAFF_PREFERENCES_TIMEOUT', message, {
      retryable: true,
      originalError,
    });
  }
}

export class StaffPreferencesAbortedError extends StaffPreferencesError {
  public override readonly name = 'StaffPreferencesAbortedError';

  constructor(message = '月嫂偏好請求已取消。') {
    super('STAFF_PREFERENCES_ABORTED', message);
  }
}

function globalErrorFacts(error: ApiHttpError): StaffPreferencesGlobalError | null {
  const parsed = StaffPreferencesGlobalErrorEnvelopeSchema.safeParse(error.raw);
  return parsed.success ? parsed.data.detail.error : null;
}

function optionsFromHttpError(error: ApiHttpError, facts: StaffPreferencesGlobalError | null) {
  return {
    publicCode: facts?.code ?? error.code,
    correlationId: facts?.correlation_id,
    currentVersion: facts?.current_version ?? null,
    domainBlockers: facts?.domain_blockers ?? [],
    fieldErrors: facts?.field_errors ?? [],
    status: error.status,
    retryable: facts?.retryable ?? error.retryable,
    originalError: error,
  };
}

export function isStaffPreferencesError(error: unknown): error is StaffPreferencesError {
  return error instanceof StaffPreferencesError;
}

export function mapStaffPreferencesError(error: unknown): StaffPreferencesError {
  if (isStaffPreferencesError(error)) return error;
  if (error instanceof ApiAbortError) return new StaffPreferencesAbortedError(error.message);
  if (error instanceof ApiTimeoutError) {
    return new StaffPreferencesTimeoutError(error.message, error);
  }
  if (error instanceof ApiNetworkError) {
    return new StaffPreferencesNetworkError(error.message, error);
  }
  if (error instanceof ApiDecodeError) {
    return new StaffPreferencesValidationError(error.message, { originalError: error });
  }
  if (error instanceof ApiHttpError) {
    const facts = globalErrorFacts(error);
    const options = optionsFromHttpError(error, facts);
    if (error.status === 401) {
      return new StaffPreferencesUnauthenticatedError(error.message, options);
    }
    if (error.status === 403) {
      return new StaffPreferencesForbiddenError(error.message, options);
    }
    if (error.status === 404) {
      return new StaffPreferencesNotFoundError(error.message, options);
    }
    if (error.status === 409) {
      return new StaffPreferencesConflictError(error.message, options);
    }
    if (error.status === 422) {
      return new StaffPreferencesValidationError(error.message, options);
    }
    if ([500, 502, 503, 504].includes(error.status)) {
      return new StaffPreferencesUnavailableError(error.message, options);
    }
    return new StaffPreferencesValidationError(error.message, options);
  }
  return new StaffPreferencesNetworkError(extractErrorMessage(error), error);
}
