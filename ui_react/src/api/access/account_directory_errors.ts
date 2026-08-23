/**
 * File: account_directory_errors.ts
 * Description: 收斂帳號清冊傳輸、認證、解碼與取消錯誤。
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

export type AccountDirectoryErrorCode =
  | 'ACCOUNT_DIRECTORY_UNAUTHENTICATED'
  | 'ACCOUNT_DIRECTORY_FORBIDDEN'
  | 'ACCOUNT_DIRECTORY_INVALID'
  | 'ACCOUNT_DIRECTORY_UNAVAILABLE'
  | 'ACCOUNT_DIRECTORY_NETWORK'
  | 'ACCOUNT_DIRECTORY_TIMEOUT'
  | 'ACCOUNT_DIRECTORY_ABORTED';

export class AccountDirectoryError extends ApiError {
  public readonly name: string = 'AccountDirectoryError';
  public readonly code: AccountDirectoryErrorCode;
  public readonly status?: number;
  public readonly retryable: boolean;
  public readonly originalError?: unknown;

  constructor(
    code: AccountDirectoryErrorCode,
    message: string,
    options?: { status?: number; retryable?: boolean; originalError?: unknown },
  ) {
    super(message);
    this.code = code;
    this.status = options?.status;
    this.retryable = options?.retryable ?? false;
    this.originalError = options?.originalError;
  }
}

export class AccountDirectoryUnauthenticatedError extends AccountDirectoryError {
  public override readonly name = 'AccountDirectoryUnauthenticatedError';

  constructor(message = '請先完成管理員登入後再查詢帳號清冊。') {
    super('ACCOUNT_DIRECTORY_UNAUTHENTICATED', message, { status: 401 });
  }
}

export class AccountDirectoryForbiddenError extends AccountDirectoryError {
  public override readonly name = 'AccountDirectoryForbiddenError';

  constructor(message = '目前登入者沒有檢視帳號清冊的 root 權限。') {
    super('ACCOUNT_DIRECTORY_FORBIDDEN', message, { status: 403 });
  }
}

export class AccountDirectoryInvalidError extends AccountDirectoryError {
  public override readonly name = 'AccountDirectoryInvalidError';

  constructor(message: string, originalError?: unknown) {
    super('ACCOUNT_DIRECTORY_INVALID', message, {
      status: 422,
      originalError,
    });
  }
}

export function mapAccountDirectoryError(error: unknown): AccountDirectoryError {
  if (error instanceof AccountDirectoryError) return error;
  if (error instanceof ApiAbortError) {
    return new AccountDirectoryError('ACCOUNT_DIRECTORY_ABORTED', error.message);
  }
  if (error instanceof ApiTimeoutError) {
    return new AccountDirectoryError('ACCOUNT_DIRECTORY_TIMEOUT', error.message, {
      retryable: true,
      originalError: error,
    });
  }
  if (error instanceof ApiDecodeError) {
    return new AccountDirectoryInvalidError(error.message, error);
  }
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return new AccountDirectoryUnauthenticatedError(error.message);
    if (error.status === 403) return new AccountDirectoryForbiddenError(error.message);
    if ([500, 502, 503, 504].includes(error.status)) {
      return new AccountDirectoryError('ACCOUNT_DIRECTORY_UNAVAILABLE', error.message, {
        status: error.status,
        retryable: error.retryable,
        originalError: error,
      });
    }
    return new AccountDirectoryInvalidError(error.message, error);
  }
  if (error instanceof ApiNetworkError) {
    return new AccountDirectoryError('ACCOUNT_DIRECTORY_NETWORK', error.message, {
      retryable: true,
      originalError: error,
    });
  }
  return new AccountDirectoryError(
    'ACCOUNT_DIRECTORY_NETWORK',
    extractErrorMessage(error),
    { retryable: true, originalError: error },
  );
}
