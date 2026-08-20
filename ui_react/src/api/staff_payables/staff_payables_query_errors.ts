/**
 * File: staff_payables_query_errors.ts
 * Description: 收斂Staff Payables查詢的認證、HTTP、解碼、逾時與取消錯誤。
 */
import { ApiAbortError, ApiDecodeError, ApiError, ApiHttpError, ApiNetworkError, ApiTimeoutError, extractErrorMessage } from '../shared/typed_errors';
export class StaffPayablesQueryError extends ApiError {
  public readonly name: string = 'StaffPayablesQueryError';
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
export function mapStaffPayablesQueryError(error: unknown): StaffPayablesQueryError {
  if (error instanceof StaffPayablesQueryError) return error;
  if (error instanceof ApiAbortError) return new StaffPayablesQueryError('STAFF_PAYABLES_ABORTED', error.message);
  if (error instanceof ApiTimeoutError) return new StaffPayablesQueryError('STAFF_PAYABLES_TIMEOUT', error.message, true);
  if (error instanceof ApiNetworkError) return new StaffPayablesQueryError('STAFF_PAYABLES_NETWORK', error.message, true);
  if (error instanceof ApiDecodeError) return new StaffPayablesQueryError('STAFF_PAYABLES_SCHEMA_MISMATCH', error.message);
  if (error instanceof ApiHttpError) return new StaffPayablesQueryError(error.code, error.message, error.retryable, error.status);
  return new StaffPayablesQueryError('STAFF_PAYABLES_UNKNOWN', extractErrorMessage(error));
}
