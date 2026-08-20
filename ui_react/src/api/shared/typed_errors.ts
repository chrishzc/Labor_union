/**
 * @file typed_errors.ts
 * @description 定義前端 API 結構化錯誤型別階層，統一網路、超時、HTTP 與解碼錯誤。
 */

export abstract class ApiError extends Error {
  public abstract readonly name: string;

  constructor(message: string) {
    super(message);
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class ApiNetworkError extends ApiError {
  public readonly name = 'ApiNetworkError';
  public readonly originalError?: unknown;

  constructor(message = '網路連線失敗，請檢查網路狀態', originalError?: unknown) {
    super(message);
    this.originalError = originalError;
  }
}

export class ApiTimeoutError extends ApiError {
  public readonly name = 'ApiTimeoutError';
  public readonly timeoutMs: number;

  constructor(timeoutMs: number, message?: string) {
    super(message ?? `請求逾時 (${timeoutMs} 毫秒)`);
    this.timeoutMs = timeoutMs;
  }
}

export class ApiAbortError extends ApiError {
  public readonly name = 'ApiAbortError';

  constructor(message = '請求已被主動取消') {
    super(message);
  }
}

export class ApiHttpError extends ApiError {
  public readonly name = 'ApiHttpError';
  public readonly status: number;
  public readonly code: string;
  public readonly retryable: boolean;
  public readonly raw?: unknown;

  constructor(
    status: number,
    code: string,
    message: string,
    retryable = false,
    raw?: unknown
  ) {
    super(message);
    this.status = status;
    this.code = code;
    this.retryable = retryable;
    this.raw = raw;
  }
}

export interface DecodeIssue {
  path: string;
  message: string;
  code?: string;
}

export class ApiDecodeError extends ApiError {
  public readonly name = 'ApiDecodeError';
  public readonly issues: DecodeIssue[];
  public readonly raw?: unknown;

  constructor(message: string, issues: DecodeIssue[] = [], raw?: unknown) {
    super(message);
    this.issues = issues;
    this.raw = raw;
  }
}

export function isApiError(err: unknown): err is ApiError {
  return err instanceof ApiError;
}

export function extractErrorMessage(err: unknown): string {
  if (err instanceof Error) {
    return err.message;
  }
  if (typeof err === 'string') {
    return err;
  }
  return '發生未知的系統錯誤';
}

export function extractErrorCode(err: unknown): string | undefined {
  if (err instanceof ApiHttpError) {
    return err.code;
  }
  return undefined;
}

export function isRetryableError(err: unknown): boolean {
  if (err instanceof ApiHttpError) {
    return err.retryable;
  }
  if (err instanceof ApiTimeoutError || err instanceof ApiNetworkError) {
    return true;
  }
  return false;
}
