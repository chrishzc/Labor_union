/**
 * File: data_browser_query_errors.ts
 * Description: 將 Data Browser transport/decode failures 收斂為 typed query errors。
 */
import {
  ApiAbortError,
  ApiDecodeError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
} from '../shared/typed_errors';

export type DataBrowserQueryErrorCode =
  | 'unauthenticated'
  | 'forbidden'
  | 'not_found'
  | 'invalid'
  | 'unavailable'
  | 'aborted'
  | 'network';

export class DataBrowserQueryError extends Error {
  public readonly code: DataBrowserQueryErrorCode;
  public readonly retryable: boolean;
  public readonly status?: number;

  constructor(
    code: DataBrowserQueryErrorCode,
    message: string,
    retryable: boolean,
    status?: number
  ) {
    super(message);
    this.name = 'DataBrowserQueryError';
    this.code = code;
    this.retryable = retryable;
    this.status = status;
  }
}

export function mapDataBrowserQueryError(error: unknown): DataBrowserQueryError {
  if (error instanceof DataBrowserQueryError) return error;
  if (error instanceof ApiAbortError) {
    return new DataBrowserQueryError('aborted', '查詢已取消', false);
  }
  if (error instanceof ApiTimeoutError) {
    return new DataBrowserQueryError('unavailable', '查詢逾時，請稍後重試', true);
  }
  if (error instanceof ApiDecodeError) {
    return new DataBrowserQueryError('invalid', error.message, false);
  }
  if (error instanceof ApiHttpError) {
    const code = error.status === 401
      ? 'unauthenticated'
      : error.status === 403
        ? 'forbidden'
        : error.status === 404
          ? 'not_found'
          : error.status >= 500
            ? 'unavailable'
            : 'invalid';
    return new DataBrowserQueryError(code, error.message, error.retryable, error.status);
  }
  if (error instanceof ApiNetworkError) {
    return new DataBrowserQueryError('network', error.message, true);
  }
  return new DataBrowserQueryError(
    'network',
    error instanceof Error ? error.message : '資料來源查詢失敗',
    true
  );
}
