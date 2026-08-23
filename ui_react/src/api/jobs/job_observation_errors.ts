/**
 * File: job_observation_errors.ts
 * Description: 收斂背景工作觀察查詢的傳輸、權限、解碼與取消錯誤。
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

export type JobObservationErrorCode =
  | 'JOB_OBSERVATION_UNAUTHENTICATED'
  | 'JOB_OBSERVATION_FORBIDDEN'
  | 'JOB_OBSERVATION_NOT_FOUND'
  | 'JOB_OBSERVATION_INVALID'
  | 'JOB_OBSERVATION_UNAVAILABLE'
  | 'JOB_OBSERVATION_NETWORK'
  | 'JOB_OBSERVATION_TIMEOUT'
  | 'JOB_OBSERVATION_ABORTED';

export class JobObservationError extends ApiError {
  public readonly name = 'JobObservationError';
  public readonly code: JobObservationErrorCode;
  public readonly status?: number;
  public readonly retryable: boolean;
  public readonly originalError?: unknown;

  constructor(
    code: JobObservationErrorCode,
    message: string,
    options?: { status?: number; retryable?: boolean; originalError?: unknown },
  ) {
    super(message);
    this.code = code;
    this.status = options?.status;
    this.retryable = options?.retryable ?? false;
    this.originalError = options?.originalError;
  }
}

export function mapJobObservationError(error: unknown): JobObservationError {
  if (error instanceof JobObservationError) return error;
  if (error instanceof ApiAbortError) return new JobObservationError('JOB_OBSERVATION_ABORTED', error.message);
  if (error instanceof ApiTimeoutError) {
    return new JobObservationError('JOB_OBSERVATION_TIMEOUT', error.message, { retryable: true, originalError: error });
  }
  if (error instanceof ApiDecodeError) {
    return new JobObservationError('JOB_OBSERVATION_INVALID', error.message, { originalError: error });
  }
  if (error instanceof ApiHttpError) {
    const code = error.status === 401
      ? 'JOB_OBSERVATION_UNAUTHENTICATED'
      : error.status === 403
        ? 'JOB_OBSERVATION_FORBIDDEN'
        : error.status === 404
          ? 'JOB_OBSERVATION_NOT_FOUND'
          : [500, 502, 503, 504].includes(error.status)
            ? 'JOB_OBSERVATION_UNAVAILABLE'
            : 'JOB_OBSERVATION_INVALID';
    return new JobObservationError(code, error.message, {
      status: error.status,
      retryable: error.retryable,
      originalError: error,
    });
  }
  if (error instanceof ApiNetworkError) {
    return new JobObservationError('JOB_OBSERVATION_NETWORK', error.message, { retryable: true, originalError: error });
  }
  return new JobObservationError('JOB_OBSERVATION_NETWORK', extractErrorMessage(error), { retryable: true, originalError: error });
}
