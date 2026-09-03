/**
 * File: line_delivery_query_errors.ts
 * Description: 收斂 LINE Delivery canonical query 的驗證、認證、HTTP、解碼、逾時與取消錯誤。
 */
import {
  ApiAbortError, ApiDecodeError, ApiError, ApiHttpError, ApiNetworkError,
  ApiTimeoutError, extractErrorMessage,
} from '../shared/typed_errors';

export class LineDeliveryQueryError extends ApiError {
  public readonly name = 'LineDeliveryQueryError';
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

export function mapLineDeliveryQueryError(error: unknown): LineDeliveryQueryError {
  if (error instanceof LineDeliveryQueryError) return error;
  if (error instanceof ApiAbortError) return new LineDeliveryQueryError('LINE_DELIVERY_ABORTED', error.message);
  if (error instanceof ApiTimeoutError) return new LineDeliveryQueryError('LINE_DELIVERY_TIMEOUT', error.message, true);
  if (error instanceof ApiNetworkError) return new LineDeliveryQueryError('LINE_DELIVERY_NETWORK', error.message, true);
  if (error instanceof ApiDecodeError) return new LineDeliveryQueryError('LINE_DELIVERY_SCHEMA_MISMATCH', error.message);
  if (error instanceof ApiHttpError) return new LineDeliveryQueryError(error.code, error.message, error.retryable, error.status);
  return new LineDeliveryQueryError('LINE_DELIVERY_UNKNOWN', extractErrorMessage(error));
}
