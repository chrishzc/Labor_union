/**
 * File: line_safe_config_errors.ts
 * Description: 將 LINE safe configuration 的認證、傳輸、HTTP 與契約錯誤型別化。
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

export type LineSafeConfigErrorCode =
  | 'LINE_SAFE_CONFIG_UNAUTHENTICATED'
  | 'LINE_SAFE_CONFIG_FORBIDDEN'
  | 'LINE_SAFE_CONFIG_VALIDATION'
  | 'LINE_SAFE_CONFIG_UNAVAILABLE'
  | 'LINE_SAFE_CONFIG_CONTRACT'
  | 'LINE_SAFE_CONFIG_NETWORK'
  | 'LINE_SAFE_CONFIG_TIMEOUT'
  | 'LINE_SAFE_CONFIG_ABORTED';

export class LineSafeConfigError extends ApiError {
  public readonly name = 'LineSafeConfigError';
  public readonly code: LineSafeConfigErrorCode;
  public readonly retryable: boolean;
  public readonly status?: number;
  public readonly publicCode?: string;
  public readonly originalError?: unknown;

  constructor(
    code: LineSafeConfigErrorCode,
    message: string,
    retryable = false,
    status?: number,
    publicCode?: string,
    originalError?: unknown,
  ) {
    super(message);
    this.code = code;
    this.retryable = retryable;
    this.status = status;
    this.publicCode = publicCode;
    this.originalError = originalError;
  }
}

export function mapLineSafeConfigError(error: unknown): LineSafeConfigError {
  if (error instanceof LineSafeConfigError) return error;
  if (error instanceof ApiAbortError) return new LineSafeConfigError('LINE_SAFE_CONFIG_ABORTED', error.message, false, undefined, undefined, error);
  if (error instanceof ApiTimeoutError) return new LineSafeConfigError('LINE_SAFE_CONFIG_TIMEOUT', error.message, true, undefined, undefined, error);
  if (error instanceof ApiNetworkError) return new LineSafeConfigError('LINE_SAFE_CONFIG_NETWORK', error.message, true, undefined, undefined, error);
  if (error instanceof ApiDecodeError) return new LineSafeConfigError('LINE_SAFE_CONFIG_CONTRACT', error.message, false, undefined, undefined, error);
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return new LineSafeConfigError('LINE_SAFE_CONFIG_UNAUTHENTICATED', error.message, false, error.status, error.code, error);
    if (error.status === 403) return new LineSafeConfigError('LINE_SAFE_CONFIG_FORBIDDEN', error.message, false, error.status, error.code, error);
    if ([502, 503, 504].includes(error.status)) return new LineSafeConfigError('LINE_SAFE_CONFIG_UNAVAILABLE', error.message, true, error.status, error.code, error);
    return new LineSafeConfigError('LINE_SAFE_CONFIG_VALIDATION', error.message, error.retryable, error.status, error.code, error);
  }
  return new LineSafeConfigError('LINE_SAFE_CONFIG_NETWORK', extractErrorMessage(error), true, undefined, undefined, error);
}
