/**
 * File: staff_payout_remediation_errors.ts
 * Description: PAYOUT-001 工作台的 typed transport、schema、owner 與終態錯誤。
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

export class StaffPayoutRemediationError extends ApiError {
  public readonly name = 'StaffPayoutRemediationError';
  public readonly code: string;
  public readonly retryable: boolean;
  public readonly status?: number;
  constructor(
    code: string,
    message: string,
    retryable = false,
    status?: number,
  ) { super(message); this.code = code; this.retryable = retryable; this.status = status; }
}

export function mapStaffPayoutRemediationError(error: unknown): StaffPayoutRemediationError {
  if (error instanceof StaffPayoutRemediationError) return error;
  if (error instanceof ApiAbortError) return new StaffPayoutRemediationError('STAFF_PAYOUT_ABORTED', error.message);
  if (error instanceof ApiTimeoutError) return new StaffPayoutRemediationError('STAFF_PAYOUT_TIMEOUT', error.message, true);
  if (error instanceof ApiNetworkError) return new StaffPayoutRemediationError('STAFF_PAYOUT_NETWORK', error.message, true);
  if (error instanceof ApiDecodeError) return new StaffPayoutRemediationError('STAFF_PAYOUT_SCHEMA_MISMATCH', error.message);
  if (error instanceof ApiHttpError) return new StaffPayoutRemediationError(error.code, error.message, error.retryable, error.status);
  return new StaffPayoutRemediationError('STAFF_PAYOUT_UNKNOWN', extractErrorMessage(error));
}
