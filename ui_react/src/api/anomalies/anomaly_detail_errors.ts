/**
 * File: anomaly_detail_errors.ts
 * Description: 將 Anomalies detail／recovery 傳輸失敗轉為 bounded typed error。
 */
import {
  ApiAbortError,
  ApiDecodeError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
  extractErrorMessage,
} from '../shared/typed_errors';

export type AnomalyDetailErrorCode =
  | 'UNAUTHENTICATED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'VALIDATION'
  | 'UNAVAILABLE'
  | 'NETWORK'
  | 'ABORTED';

export class AnomalyDetailError extends Error {
  public readonly name = 'AnomalyDetailError';
  public readonly code: AnomalyDetailErrorCode;
  public readonly retryable: boolean;
  public readonly status?: number;
  public readonly causeValue?: unknown;

  constructor(
    code: AnomalyDetailErrorCode,
    message: string,
    retryable = false,
    status?: number,
    causeValue?: unknown
  ) {
    super(message);
    this.code = code;
    this.retryable = retryable;
    this.status = status;
    this.causeValue = causeValue;
  }
}

export function mapAnomalyDetailError(error: unknown): AnomalyDetailError {
  if (error instanceof AnomalyDetailError) return error;
  if (error instanceof ApiAbortError) {
    return new AnomalyDetailError('ABORTED', error.message, false, undefined, error);
  }
  if (error instanceof ApiTimeoutError) {
    return new AnomalyDetailError('NETWORK', error.message, true, undefined, error);
  }
  if (error instanceof ApiNetworkError) {
    return new AnomalyDetailError('NETWORK', error.message, true, undefined, error);
  }
  if (error instanceof ApiDecodeError) {
    return new AnomalyDetailError('VALIDATION', error.message, false, undefined, error);
  }
  if (error instanceof ApiHttpError) {
    const code = error.status === 401
      ? 'UNAUTHENTICATED'
      : error.status === 403
        ? 'FORBIDDEN'
        : error.status === 404
          ? 'NOT_FOUND'
          : error.status >= 500
            ? 'UNAVAILABLE'
            : 'VALIDATION';
    return new AnomalyDetailError(code, error.message, error.retryable, error.status, error);
  }
  return new AnomalyDetailError('NETWORK', extractErrorMessage(error), true, undefined, error);
}
