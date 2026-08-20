/**
 * File: subsidy_report_query_errors.ts
 * Description: 收斂補助報表查詢的認證、HTTP、解碼、逾時與取消錯誤。
 */
import { ApiAbortError, ApiDecodeError, ApiError, ApiHttpError, ApiNetworkError, ApiTimeoutError, extractErrorMessage } from '../shared/typed_errors';
export class SubsidyReportQueryError extends ApiError {
  public readonly name: string = 'SubsidyReportQueryError';
  public readonly code: string;
  public readonly retryable: boolean;
  public readonly status?: number;
  constructor(code: string, message: string, retryable = false, status?: number) { super(message); this.code = code; this.retryable = retryable; this.status = status; }
}
export function mapSubsidyReportQueryError(error: unknown): SubsidyReportQueryError {
  if (error instanceof SubsidyReportQueryError) return error;
  if (error instanceof ApiAbortError) return new SubsidyReportQueryError('SUBSIDY_REPORT_ABORTED', error.message);
  if (error instanceof ApiTimeoutError) return new SubsidyReportQueryError('SUBSIDY_REPORT_TIMEOUT', error.message, true);
  if (error instanceof ApiNetworkError) return new SubsidyReportQueryError('SUBSIDY_REPORT_NETWORK', error.message, true);
  if (error instanceof ApiDecodeError) return new SubsidyReportQueryError('SUBSIDY_REPORT_SCHEMA_MISMATCH', error.message);
  if (error instanceof ApiHttpError) return new SubsidyReportQueryError(error.code, error.message, error.retryable, error.status);
  return new SubsidyReportQueryError('SUBSIDY_REPORT_UNKNOWN', extractErrorMessage(error));
}
