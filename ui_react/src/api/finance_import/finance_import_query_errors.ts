/**
 * File: finance_import_query_errors.ts
 * Description: 收斂Finance Import查詢的認證、HTTP、解碼、逾時與取消錯誤。
 */
import { ApiAbortError, ApiDecodeError, ApiError, ApiHttpError, ApiNetworkError, ApiTimeoutError, extractErrorMessage } from '../shared/typed_errors';
export class FinanceImportQueryError extends ApiError {
  public readonly name: string = 'FinanceImportQueryError';
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
export function mapFinanceImportQueryError(error: unknown): FinanceImportQueryError {
  if (error instanceof FinanceImportQueryError) return error;
  if (error instanceof ApiAbortError) return new FinanceImportQueryError('FINANCE_IMPORT_ABORTED', error.message);
  if (error instanceof ApiTimeoutError) return new FinanceImportQueryError('FINANCE_IMPORT_TIMEOUT', error.message, true);
  if (error instanceof ApiNetworkError) return new FinanceImportQueryError('FINANCE_IMPORT_NETWORK', error.message, true);
  if (error instanceof ApiDecodeError) return new FinanceImportQueryError('FINANCE_IMPORT_SCHEMA_MISMATCH', error.message);
  if (error instanceof ApiHttpError) return new FinanceImportQueryError(error.code, error.message, error.retryable, error.status);
  return new FinanceImportQueryError('FINANCE_IMPORT_UNKNOWN', extractErrorMessage(error));
}
