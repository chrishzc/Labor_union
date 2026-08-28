/**
 * File: client_over_refund_recovery_errors.ts
 * Description: 將客戶退款超額追償 owner API 的 transport、typed HTTP 與契約錯誤收斂為單一型別。
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

export class ClientOverRefundRecoveryError extends ApiError {
  public readonly name = 'ClientOverRefundRecoveryError';
  public readonly code: string;
  public readonly retryable: boolean;
  public readonly status?: number;

  constructor(
    code: string,
    message: string,
    retryable = false,
    status?: number,
  ) {
    super(message);
    this.code = code;
    this.retryable = retryable;
    this.status = status;
  }
}

export function mapClientOverRefundRecoveryError(error: unknown): ClientOverRefundRecoveryError {
  if (error instanceof ClientOverRefundRecoveryError) return error;
  if (error instanceof ApiAbortError) return new ClientOverRefundRecoveryError('CLIENT_RECOVERY_ABORTED', error.message);
  if (error instanceof ApiTimeoutError) return new ClientOverRefundRecoveryError('CLIENT_RECOVERY_TIMEOUT', error.message, true);
  if (error instanceof ApiNetworkError) return new ClientOverRefundRecoveryError('CLIENT_RECOVERY_NETWORK', error.message, true);
  if (error instanceof ApiDecodeError) return new ClientOverRefundRecoveryError('CLIENT_RECOVERY_SCHEMA_MISMATCH', error.message);
  if (error instanceof ApiHttpError) return new ClientOverRefundRecoveryError(error.code, error.message, error.retryable, error.status);
  return new ClientOverRefundRecoveryError('CLIENT_RECOVERY_UNKNOWN', extractErrorMessage(error));
}
