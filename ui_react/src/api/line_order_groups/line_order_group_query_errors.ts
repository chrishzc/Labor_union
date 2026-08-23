/**
 * File: line_order_group_query_errors.ts
 * Description: 收斂 LINE 訂單群組 query 的認證、傳輸、嚴格解碼、取消與逾時錯誤。
 */
import {
  ApiAbortError, ApiDecodeError, ApiError, ApiHttpError, ApiNetworkError,
  ApiTimeoutError, extractErrorMessage,
} from '../shared/typed_errors';

export class LineOrderGroupQueryError extends ApiError {
  public readonly name = 'LineOrderGroupQueryError';
  public readonly code: string;
  public readonly retryable: boolean;
  public readonly status?: number;

  constructor(code: string, message: string, retryable = false, status?: number) {
    super(message);
    this.code = code;
    this.retryable = retryable;
    this.status = status;
  }
}

export function mapLineOrderGroupQueryError(error: unknown): LineOrderGroupQueryError {
  if (error instanceof LineOrderGroupQueryError) return error;
  if (error instanceof ApiAbortError) return new LineOrderGroupQueryError('LINE_ORDER_GROUP_ABORTED', error.message);
  if (error instanceof ApiTimeoutError) return new LineOrderGroupQueryError('LINE_ORDER_GROUP_TIMEOUT', error.message, true);
  if (error instanceof ApiNetworkError) return new LineOrderGroupQueryError('LINE_ORDER_GROUP_NETWORK', error.message, true);
  if (error instanceof ApiDecodeError) return new LineOrderGroupQueryError('LINE_ORDER_GROUP_SCHEMA_MISMATCH', error.message);
  if (error instanceof ApiHttpError) return new LineOrderGroupQueryError(error.code, error.message, error.retryable, error.status);
  return new LineOrderGroupQueryError('LINE_ORDER_GROUP_UNKNOWN', extractErrorMessage(error));
}
