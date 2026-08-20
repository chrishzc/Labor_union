/**
 * File: accounts_payable_query_errors.ts
 * Description: 收斂Accounts Payable查詢的認證、HTTP、解碼、逾時與取消錯誤。
 */
import { ApiAbortError, ApiDecodeError, ApiError, ApiHttpError, ApiNetworkError, ApiTimeoutError, extractErrorMessage } from '../shared/typed_errors';
export class AccountsPayableQueryError extends ApiError {
  public readonly name: string = 'AccountsPayableQueryError';
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
export function mapAccountsPayableQueryError(error: unknown): AccountsPayableQueryError {
  if (error instanceof AccountsPayableQueryError) return error;
  if (error instanceof ApiAbortError) return new AccountsPayableQueryError('ACCOUNTS_PAYABLE_ABORTED', error.message);
  if (error instanceof ApiTimeoutError) return new AccountsPayableQueryError('ACCOUNTS_PAYABLE_TIMEOUT', error.message, true);
  if (error instanceof ApiNetworkError) return new AccountsPayableQueryError('ACCOUNTS_PAYABLE_NETWORK', error.message, true);
  if (error instanceof ApiDecodeError) return new AccountsPayableQueryError('ACCOUNTS_PAYABLE_SCHEMA_MISMATCH', error.message);
  if (error instanceof ApiHttpError) return new AccountsPayableQueryError(error.code, error.message, error.retryable, error.status);
  return new AccountsPayableQueryError('ACCOUNTS_PAYABLE_UNKNOWN', extractErrorMessage(error));
}
