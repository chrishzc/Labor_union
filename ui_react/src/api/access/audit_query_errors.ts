/**
 * File: audit_query_errors.ts
 * Description: 收斂遮罩稽核查詢的傳輸、權限、解碼與取消錯誤。
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

export type AuditQueryErrorCode =
  | 'AUDIT_QUERY_UNAUTHENTICATED'
  | 'AUDIT_QUERY_FORBIDDEN'
  | 'AUDIT_QUERY_NOT_FOUND'
  | 'AUDIT_QUERY_INVALID'
  | 'AUDIT_QUERY_UNAVAILABLE'
  | 'AUDIT_QUERY_NETWORK'
  | 'AUDIT_QUERY_TIMEOUT'
  | 'AUDIT_QUERY_ABORTED';

export class AuditQueryError extends ApiError {
  public readonly name = 'AuditQueryError';
  public readonly code: AuditQueryErrorCode;
  public readonly status?: number;
  public readonly retryable: boolean;
  public readonly originalError?: unknown;

  constructor(
    code: AuditQueryErrorCode,
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

export function mapAuditQueryError(error: unknown): AuditQueryError {
  if (error instanceof AuditQueryError) return error;
  if (error instanceof ApiAbortError) {
    return new AuditQueryError('AUDIT_QUERY_ABORTED', error.message);
  }
  if (error instanceof ApiTimeoutError) {
    return new AuditQueryError('AUDIT_QUERY_TIMEOUT', error.message, {
      retryable: true,
      originalError: error,
    });
  }
  if (error instanceof ApiDecodeError) {
    return new AuditQueryError('AUDIT_QUERY_INVALID', error.message, {
      originalError: error,
    });
  }
  if (error instanceof ApiHttpError) {
    const code = error.status === 401
      ? 'AUDIT_QUERY_UNAUTHENTICATED'
      : error.status === 403
        ? 'AUDIT_QUERY_FORBIDDEN'
        : error.status === 404
          ? 'AUDIT_QUERY_NOT_FOUND'
        : [500, 502, 503, 504].includes(error.status)
          ? 'AUDIT_QUERY_UNAVAILABLE'
          : 'AUDIT_QUERY_INVALID';
    return new AuditQueryError(code, error.message, {
      status: error.status,
      retryable: error.retryable,
      originalError: error,
    });
  }
  if (error instanceof ApiNetworkError) {
    return new AuditQueryError('AUDIT_QUERY_NETWORK', error.message, {
      retryable: true,
      originalError: error,
    });
  }
  return new AuditQueryError('AUDIT_QUERY_NETWORK', extractErrorMessage(error), {
    retryable: true,
    originalError: error,
  });
}
