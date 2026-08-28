/**
 * File: staff_overpayment_recovery_errors.ts
 * Description: Staff recovery API 的 typed transport、schema、owner blocker 錯誤。
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

export class StaffOverpaymentRecoveryError extends ApiError {
  public readonly name = 'StaffOverpaymentRecoveryError';
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

export function mapStaffOverpaymentRecoveryError(error: unknown): StaffOverpaymentRecoveryError {
  if (error instanceof StaffOverpaymentRecoveryError) return error;
  if (error instanceof ApiAbortError) return new StaffOverpaymentRecoveryError('STAFF_RECOVERY_ABORTED', error.message);
  if (error instanceof ApiTimeoutError) return new StaffOverpaymentRecoveryError('STAFF_RECOVERY_TIMEOUT', error.message, true);
  if (error instanceof ApiNetworkError) return new StaffOverpaymentRecoveryError('STAFF_RECOVERY_NETWORK', error.message, true);
  if (error instanceof ApiDecodeError) return new StaffOverpaymentRecoveryError('STAFF_RECOVERY_SCHEMA_MISMATCH', error.message);
  if (error instanceof ApiHttpError) return new StaffOverpaymentRecoveryError(error.code, error.message, error.retryable, error.status);
  return new StaffOverpaymentRecoveryError('STAFF_RECOVERY_UNKNOWN', extractErrorMessage(error));
}
