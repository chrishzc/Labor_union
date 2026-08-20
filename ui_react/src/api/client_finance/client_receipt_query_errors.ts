/**
 * File: client_receipt_query_errors.ts
 * Description: 收斂Client Receipt查詢的認證、HTTP、解碼、逾時與取消錯誤。
 */
import { ApiAbortError, ApiDecodeError, ApiError, ApiHttpError, ApiNetworkError, ApiTimeoutError, extractErrorMessage } from '../shared/typed_errors';

export class ClientReceiptQueryError extends ApiError {
  public readonly name: string = 'ClientReceiptQueryError';
  public readonly code: string;
  public readonly retryable: boolean;
  public readonly status?: number;
  constructor(
    code: string,
    message: string,
    retryable = false,
    status?: number
  ) {
    super(message);
    this.code = code;
    this.retryable = retryable;
    this.status = status;
  }
}

export function mapClientReceiptQueryError(error: unknown): ClientReceiptQueryError {
  if (error instanceof ClientReceiptQueryError) return error;
  if (error instanceof ApiAbortError) return new ClientReceiptQueryError('CLIENT_RECEIPT_ABORTED', error.message);
  if (error instanceof ApiTimeoutError) return new ClientReceiptQueryError('CLIENT_RECEIPT_TIMEOUT', error.message, true);
  if (error instanceof ApiNetworkError) return new ClientReceiptQueryError('CLIENT_RECEIPT_NETWORK', error.message, true);
  if (error instanceof ApiDecodeError) return new ClientReceiptQueryError('CLIENT_RECEIPT_SCHEMA_MISMATCH', error.message);
  if (error instanceof ApiHttpError) return new ClientReceiptQueryError(error.code, error.message, error.retryable, error.status);
  return new ClientReceiptQueryError('CLIENT_RECEIPT_UNKNOWN', extractErrorMessage(error));
}
