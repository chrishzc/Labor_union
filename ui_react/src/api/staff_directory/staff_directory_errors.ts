/**
 * File: staff_directory_errors.ts
 * Description: 將 Staff 摘要查詢的傳輸、認證、解碼與取消失敗收斂為 bounded typed errors。
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

export type StaffDirectoryErrorCode =
  | 'STAFF_DIRECTORY_UNAUTHENTICATED'
  | 'STAFF_DIRECTORY_FORBIDDEN'
  | 'STAFF_DIRECTORY_VALIDATION'
  | 'STAFF_DIRECTORY_UNAVAILABLE'
  | 'STAFF_DIRECTORY_NETWORK'
  | 'STAFF_DIRECTORY_TIMEOUT'
  | 'STAFF_DIRECTORY_ABORTED';

export class StaffDirectoryError extends ApiError {
  public readonly name: string = 'StaffDirectoryError';
  public readonly code: StaffDirectoryErrorCode;
  public readonly status?: number;
  public readonly retryable: boolean;
  public readonly originalError?: unknown;

  constructor(
    code: StaffDirectoryErrorCode,
    message: string,
    options?: { status?: number; retryable?: boolean; originalError?: unknown }
  ) {
    super(message);
    this.code = code;
    this.status = options?.status;
    this.retryable = options?.retryable ?? false;
    this.originalError = options?.originalError;
  }
}

export class StaffDirectoryUnauthenticatedError extends StaffDirectoryError {
  public override readonly name = 'StaffDirectoryUnauthenticatedError';

  constructor(message = '請先完成管理員登入後再查詢服務人員名冊。') {
    super('STAFF_DIRECTORY_UNAUTHENTICATED', message, { status: 401 });
  }
}

export class StaffDirectoryValidationError extends StaffDirectoryError {
  public override readonly name = 'StaffDirectoryValidationError';

  constructor(message: string, originalError?: unknown) {
    super('STAFF_DIRECTORY_VALIDATION', message, {
      status: 422,
      originalError,
    });
  }
}

export class StaffDirectoryAbortedError extends StaffDirectoryError {
  public override readonly name = 'StaffDirectoryAbortedError';

  constructor(message = '服務人員名冊查詢已取消。') {
    super('STAFF_DIRECTORY_ABORTED', message);
  }
}

export function mapStaffDirectoryError(error: unknown): StaffDirectoryError {
  if (error instanceof StaffDirectoryError) return error;
  if (error instanceof ApiAbortError) return new StaffDirectoryAbortedError(error.message);
  if (error instanceof ApiTimeoutError) {
    return new StaffDirectoryError('STAFF_DIRECTORY_TIMEOUT', error.message, {
      retryable: true,
      originalError: error,
    });
  }
  if (error instanceof ApiNetworkError) {
    return new StaffDirectoryError('STAFF_DIRECTORY_NETWORK', error.message, {
      retryable: true,
      originalError: error,
    });
  }
  if (error instanceof ApiDecodeError) {
    return new StaffDirectoryValidationError(error.message, error);
  }
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return new StaffDirectoryUnauthenticatedError(error.message);
    if (error.status === 403) {
      return new StaffDirectoryError('STAFF_DIRECTORY_FORBIDDEN', error.message, {
        status: 403,
        originalError: error,
      });
    }
    if (error.status === 422) return new StaffDirectoryValidationError(error.message, error);
    if ([500, 502, 503, 504].includes(error.status)) {
      return new StaffDirectoryError('STAFF_DIRECTORY_UNAVAILABLE', error.message, {
        status: error.status,
        retryable: error.retryable,
        originalError: error,
      });
    }
    return new StaffDirectoryError('STAFF_DIRECTORY_VALIDATION', error.message, {
      status: error.status,
      retryable: error.retryable,
      originalError: error,
    });
  }
  return new StaffDirectoryError('STAFF_DIRECTORY_NETWORK', extractErrorMessage(error), {
    retryable: true,
    originalError: error,
  });
}
