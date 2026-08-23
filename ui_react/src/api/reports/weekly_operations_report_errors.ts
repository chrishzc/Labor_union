/**
 * File: weekly_operations_report_errors.ts
 * Description: 收斂營運週報查詢與匯出的驗證、認證、傳輸、解碼及取消錯誤。
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

export class WeeklyOperationsReportError extends ApiError {
  public readonly name = 'WeeklyOperationsReportError';
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

export function mapWeeklyOperationsReportError(error: unknown): WeeklyOperationsReportError {
  if (error instanceof WeeklyOperationsReportError) return error;
  if (error instanceof ApiAbortError) return new WeeklyOperationsReportError('WEEKLY_REPORT_ABORTED', error.message);
  if (error instanceof ApiTimeoutError) return new WeeklyOperationsReportError('WEEKLY_REPORT_TIMEOUT', error.message, true);
  if (error instanceof ApiNetworkError) return new WeeklyOperationsReportError('WEEKLY_REPORT_NETWORK', error.message, true);
  if (error instanceof ApiDecodeError) return new WeeklyOperationsReportError('WEEKLY_REPORT_SCHEMA_MISMATCH', error.message);
  if (error instanceof ApiHttpError) return new WeeklyOperationsReportError(error.code, error.message, error.retryable, error.status);
  return new WeeklyOperationsReportError('WEEKLY_REPORT_UNKNOWN', extractErrorMessage(error));
}
