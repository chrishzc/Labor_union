/**
 * File: scheduling_current_errors.ts
 * Description: 將 Scheduling query 的認證、HTTP、解碼、逾時與取消失敗收斂為 typed errors。
 */
import {
  ApiAbortError,
  ApiDecodeError,
  ApiError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
  extractErrorMessage,
} from '../shared/typed_errors';
import { SchedulingGlobalTypedErrorResponseSchema } from './scheduling_current_schemas';

export type SchedulingCurrentErrorCode =
  | 'SCHEDULING_UNAUTHENTICATED'
  | 'SCHEDULING_FORBIDDEN'
  | 'SCHEDULING_NOT_FOUND'
  | 'SCHEDULING_VALIDATION'
  | 'SCHEDULING_CONFLICT'
  | 'SCHEDULING_UNAVAILABLE'
  | 'SCHEDULING_NETWORK'
  | 'SCHEDULING_TIMEOUT'
  | 'SCHEDULING_ABORTED';

export class SchedulingCurrentError extends ApiError {
  public readonly name: string = 'SchedulingCurrentError';
  public readonly code: SchedulingCurrentErrorCode;
  public readonly publicCode?: string;
  public readonly correlationId?: string;
  public readonly status?: number;
  public readonly retryable: boolean;
  public readonly originalError?: unknown;

  constructor(
    code: SchedulingCurrentErrorCode,
    message: string,
    options?: {
      publicCode?: string;
      correlationId?: string;
      status?: number;
      retryable?: boolean;
      originalError?: unknown;
    }
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

export class SchedulingUnauthenticatedError extends SchedulingCurrentError {
  public override readonly name = 'SchedulingUnauthenticatedError';

  constructor(message = '請先完成管理員登入後再查詢排班日曆。') {
    super('SCHEDULING_UNAUTHENTICATED', message, { status: 401 });
  }
}

export class SchedulingValidationError extends SchedulingCurrentError {
  public override readonly name = 'SchedulingValidationError';

  constructor(message: string, originalError?: unknown) {
    super('SCHEDULING_VALIDATION', message, {
      status: 422,
      originalError,
    });
  }
}

export class SchedulingAbortedError extends SchedulingCurrentError {
  public override readonly name = 'SchedulingAbortedError';

  constructor(message = '排班日曆查詢已取消。') {
    super('SCHEDULING_ABORTED', message);
  }
}

function httpMetadata(error: ApiHttpError) {
  const decoded = SchedulingGlobalTypedErrorResponseSchema.safeParse(error.raw);
  if (!decoded.success) {
    return { publicCode: error.code, correlationId: undefined };
  }
  return {
    publicCode: decoded.data.detail.error.code,
    correlationId: decoded.data.detail.error.correlation_id,
  };
}

export function mapSchedulingCurrentError(error: unknown): SchedulingCurrentError {
  if (error instanceof SchedulingCurrentError) return error;
  if (error instanceof ApiAbortError) return new SchedulingAbortedError(error.message);
  if (error instanceof ApiTimeoutError) {
    return new SchedulingCurrentError('SCHEDULING_TIMEOUT', error.message, {
      retryable: true,
      originalError: error,
    });
  }
  if (error instanceof ApiNetworkError) {
    return new SchedulingCurrentError('SCHEDULING_NETWORK', error.message, {
      retryable: true,
      originalError: error,
    });
  }
  if (error instanceof ApiDecodeError) {
    return new SchedulingValidationError(error.message, error);
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
      return new SchedulingCurrentError(
        'SCHEDULING_UNAUTHENTICATED',
        error.message,
        options
      );
    }
    if (error.status === 403) {
      return new SchedulingCurrentError('SCHEDULING_FORBIDDEN', error.message, options);
    }
    if (error.status === 404) {
      return new SchedulingCurrentError('SCHEDULING_NOT_FOUND', error.message, options);
    }
    if (error.status === 409) {
      return new SchedulingCurrentError('SCHEDULING_CONFLICT', error.message, options);
    }
    if (error.status === 422) {
      return new SchedulingCurrentError('SCHEDULING_VALIDATION', error.message, options);
    }
    if ([500, 502, 503, 504].includes(error.status)) {
      return new SchedulingCurrentError('SCHEDULING_UNAVAILABLE', error.message, options);
    }
    return new SchedulingCurrentError('SCHEDULING_VALIDATION', error.message, options);
  }
  return new SchedulingCurrentError(
    'SCHEDULING_NETWORK',
    extractErrorMessage(error),
    { retryable: true, originalError: error }
  );
}
