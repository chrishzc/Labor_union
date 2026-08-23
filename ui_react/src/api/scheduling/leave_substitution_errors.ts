/**
 * File: leave_substitution_errors.ts
 * Description: 將請假代班 API 的 HTTP、契約、認證、取消與網路失敗收斂為 typed errors。
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

const LeaveSubstitutionGlobalTypedErrorResponseSchema = z.strictObject({
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
      code: z.string().min(1),
      message: z.string().min(1),
      field_errors: z.array(
        z.strictObject({
          field: z.string(),
          code: z.string(),
          message: z.string(),
        }),
      ),
      domain_blockers: z.array(z.string()),
      retryable: z.boolean(),
      correlation_id: z.string().min(1),
      current_version: z.number().int().nullable(),
    }),
  }),
});

export type LeaveSubstitutionErrorCode =
  | 'LEAVE_SUBSTITUTION_UNAUTHENTICATED'
  | 'LEAVE_SUBSTITUTION_FORBIDDEN'
  | 'LEAVE_SUBSTITUTION_NOT_FOUND'
  | 'LEAVE_SUBSTITUTION_CONFLICT'
  | 'LEAVE_SUBSTITUTION_VALIDATION'
  | 'LEAVE_SUBSTITUTION_UNAVAILABLE'
  | 'LEAVE_SUBSTITUTION_CONTRACT'
  | 'LEAVE_SUBSTITUTION_NETWORK'
  | 'LEAVE_SUBSTITUTION_TIMEOUT'
  | 'LEAVE_SUBSTITUTION_ABORTED';

export class LeaveSubstitutionError extends ApiError {
  public readonly name: string = 'LeaveSubstitutionError';
  public readonly code: LeaveSubstitutionErrorCode;
  public readonly publicCode?: string;
  public readonly correlationId?: string;
  public readonly status?: number;
  public readonly retryable: boolean;
  public readonly originalError?: unknown;

  constructor(
    code: LeaveSubstitutionErrorCode,
    message: string,
    options?: {
      publicCode?: string;
      correlationId?: string;
      status?: number;
      retryable?: boolean;
      originalError?: unknown;
    },
  ) {
    super(message);
    this.code = code;
    this.publicCode = options?.publicCode;
    this.correlationId = options?.correlationId;
    this.status = options?.status;
    this.retryable = options?.retryable ?? false;
    this.originalError = options?.originalError;
  }
}

export class LeaveSubstitutionUnauthenticatedError extends LeaveSubstitutionError {
  public override readonly name = 'LeaveSubstitutionUnauthenticatedError';

  constructor(
    message = '請先完成管理員登入後再處理請假代班。',
    options?: ConstructorParameters<typeof LeaveSubstitutionError>[2],
  ) {
    super('LEAVE_SUBSTITUTION_UNAUTHENTICATED', message, {
      ...options,
      status: options?.status ?? 401,
    });
  }
}

export class LeaveSubstitutionForbiddenError extends LeaveSubstitutionError {
  public override readonly name = 'LeaveSubstitutionForbiddenError';

  constructor(
    message = '目前登入者沒有請假代班處理權限。',
    options?: ConstructorParameters<typeof LeaveSubstitutionError>[2],
  ) {
    super('LEAVE_SUBSTITUTION_FORBIDDEN', message, {
      ...options,
      status: options?.status ?? 403,
    });
  }
}

export class LeaveSubstitutionNotFoundError extends LeaveSubstitutionError {
  public override readonly name = 'LeaveSubstitutionNotFoundError';

  constructor(
    message = '找不到請假代班案件或指派。',
    options?: ConstructorParameters<typeof LeaveSubstitutionError>[2],
  ) {
    super('LEAVE_SUBSTITUTION_NOT_FOUND', message, {
      ...options,
      status: options?.status ?? 404,
    });
  }
}

export class LeaveSubstitutionConflictError extends LeaveSubstitutionError {
  public override readonly name = 'LeaveSubstitutionConflictError';

  constructor(
    message: string,
    options?: ConstructorParameters<typeof LeaveSubstitutionError>[2],
  ) {
    super('LEAVE_SUBSTITUTION_CONFLICT', message, {
      ...options,
      status: options?.status ?? 409,
    });
  }
}

export class LeaveSubstitutionValidationError extends LeaveSubstitutionError {
  public override readonly name = 'LeaveSubstitutionValidationError';

  constructor(
    message: string,
    originalError?: unknown,
    options?: { publicCode?: string; correlationId?: string },
  ) {
    super('LEAVE_SUBSTITUTION_VALIDATION', message, {
      ...options,
      status: 422,
      originalError,
    });
  }
}

export class LeaveSubstitutionContractError extends LeaveSubstitutionError {
  public override readonly name = 'LeaveSubstitutionContractError';

  constructor(message: string, originalError?: unknown) {
    super('LEAVE_SUBSTITUTION_CONTRACT', message, { status: 422, originalError });
  }
}

export class LeaveSubstitutionUnavailableError extends LeaveSubstitutionError {
  public override readonly name = 'LeaveSubstitutionUnavailableError';

  constructor(
    message: string,
    options?: ConstructorParameters<typeof LeaveSubstitutionError>[2],
  ) {
    super('LEAVE_SUBSTITUTION_UNAVAILABLE', message, {
      ...options,
      status: options?.status ?? 503,
      retryable: options?.retryable ?? true,
    });
  }
}

export class LeaveSubstitutionNetworkError extends LeaveSubstitutionError {
  public override readonly name = 'LeaveSubstitutionNetworkError';

  constructor(message: string, originalError?: unknown) {
    super('LEAVE_SUBSTITUTION_NETWORK', message, {
      retryable: true,
      originalError,
    });
  }
}

export class LeaveSubstitutionTimeoutError extends LeaveSubstitutionError {
  public override readonly name = 'LeaveSubstitutionTimeoutError';

  constructor(message: string, originalError?: unknown) {
    super('LEAVE_SUBSTITUTION_TIMEOUT', message, {
      retryable: true,
      originalError,
    });
  }
}

export class LeaveSubstitutionAbortedError extends LeaveSubstitutionError {
  public override readonly name = 'LeaveSubstitutionAbortedError';

  constructor(message = '請假代班請求已取消。', originalError?: unknown) {
    super('LEAVE_SUBSTITUTION_ABORTED', message, { originalError });
  }
}

function httpMetadata(error: ApiHttpError): {
  publicCode?: string;
  correlationId?: string;
} {
  const decoded = LeaveSubstitutionGlobalTypedErrorResponseSchema.safeParse(error.raw);
  if (!decoded.success) {
    return { publicCode: error.code };
  }
  return {
    publicCode: decoded.data.detail.error.code,
    correlationId: decoded.data.detail.error.correlation_id,
  };
}

export function mapLeaveSubstitutionError(error: unknown): LeaveSubstitutionError {
  if (error instanceof LeaveSubstitutionError) return error;
  if (error instanceof ApiAbortError) {
    return new LeaveSubstitutionAbortedError(error.message, error);
  }
  if (error instanceof ApiTimeoutError) {
    return new LeaveSubstitutionTimeoutError(error.message, error);
  }
  if (error instanceof ApiDecodeError) {
    return new LeaveSubstitutionContractError(error.message, error);
  }
  if (error instanceof ApiNetworkError) {
    return new LeaveSubstitutionNetworkError(error.message, error);
  }
  if (error instanceof ApiHttpError) {
    const metadata = httpMetadata(error);
    const options = {
      ...metadata,
      status: error.status,
      retryable: error.retryable,
      originalError: error,
    };
    if (error.status === 401) {
      return new LeaveSubstitutionUnauthenticatedError(error.message, options);
    }
    if (error.status === 403) {
      return new LeaveSubstitutionForbiddenError(error.message, options);
    }
    if (error.status === 404) {
      return new LeaveSubstitutionNotFoundError(error.message, options);
    }
    if (error.status === 409) {
      return new LeaveSubstitutionConflictError(error.message, options);
    }
    if (error.status === 422) {
      return new LeaveSubstitutionValidationError(error.message, error, metadata);
    }
    if ([500, 502, 503, 504].includes(error.status)) {
      return new LeaveSubstitutionUnavailableError(error.message, options);
    }
    return new LeaveSubstitutionValidationError(error.message, error, metadata);
  }
  return new LeaveSubstitutionNetworkError(extractErrorMessage(error), error);
}

export function assertLeaveSubstitutionInput(
  condition: boolean,
  message: string,
): void {
  if (!condition) throw new LeaveSubstitutionValidationError(message);
}
