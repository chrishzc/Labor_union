/**
 * @file anomaly_query_errors.ts
 * @description 定義異常查詢領域之結構化錯誤型別階層、HTTP 狀態碼映射與型別保護函式。
 * 契約依據: PROV-20260816 Phase 2D CONTRACT_MATRIX.md 與錯誤分類規範。
 * 變更範圍: 異常查詢專用錯誤類別與轉譯函式。
 * 驗證依據: Vitest 錯誤處理測試 (401/403/422/503/網路/取消)。
 * 無副作用宣告: 純錯誤類別與無副作用純函式。
 */
import {
  ApiError,
  ApiHttpError,
  ApiDecodeError,
  ApiNetworkError,
  ApiTimeoutError,
  ApiAbortError,
  extractErrorMessage,
} from '../shared/typed_errors';

export {
  ApiError,
  ApiHttpError,
  ApiDecodeError,
  ApiNetworkError,
  ApiTimeoutError,
  ApiAbortError,
};

export type AnomalyQueryErrorCode =
  | 'ANOMALY_QUERY_UNAUTHENTICATED'
  | 'ANOMALY_QUERY_FORBIDDEN'
  | 'ANOMALY_QUERY_VALIDATION_ERROR'
  | 'ANOMALY_QUERY_SERVICE_UNAVAILABLE'
  | 'ANOMALY_QUERY_NETWORK_ERROR'
  | 'ANOMALY_QUERY_ABORTED';

export interface FieldValidationError {
  field: string;
  message: string;
}

/**
 * 異常查詢領域基礎錯誤類別
 */
export class AnomalyQueryError extends ApiError {
  public readonly name: string = 'AnomalyQueryError';
  public readonly code: AnomalyQueryErrorCode;
  public readonly status?: number;
  public readonly retryable: boolean;
  public readonly fieldErrors?: FieldValidationError[];
  public readonly originalError?: unknown;

  constructor(
    code: AnomalyQueryErrorCode,
    message: string,
    options?: {
      status?: number;
      retryable?: boolean;
      fieldErrors?: FieldValidationError[];
      originalError?: unknown;
    }
  ) {
    super(message);
    this.code = code;
    this.status = options?.status;
    this.retryable =
      options?.retryable ??
      (code === 'ANOMALY_QUERY_SERVICE_UNAVAILABLE' ||
        code === 'ANOMALY_QUERY_NETWORK_ERROR');
    this.fieldErrors = options?.fieldErrors;
    this.originalError = options?.originalError;
  }
}

/**
 * HTTP 401 Unauthorized: 未登入或認證憑證無效
 */
export class AnomalyUnauthenticatedError extends AnomalyQueryError {
  public override readonly name = 'AnomalyUnauthenticatedError';

  constructor(message = '未登入或認證憑證已過期，請重新登入 (HTTP 401)') {
    super('ANOMALY_QUERY_UNAUTHENTICATED', message, {
      status: 401,
      retryable: false,
    });
  }
}

/**
 * HTTP 403 Forbidden: 權限不足
 */
export class AnomalyForbiddenError extends AnomalyQueryError {
  public override readonly name = 'AnomalyForbiddenError';

  constructor(message = '您沒有存取異常或匯入警示資料的權限 (HTTP 403)') {
    super('ANOMALY_QUERY_FORBIDDEN', message, {
      status: 403,
      retryable: false,
    });
  }
}

/**
 * HTTP 422 Unprocessable Entity 或 Zod 解碼失敗: 參數或回應綱要驗證失敗
 */
export class AnomalyValidationError extends AnomalyQueryError {
  public override readonly name = 'AnomalyValidationError';

  constructor(
    message = '異常查詢請求參數或資料結構驗證失敗 (HTTP 422)',
    fieldErrors: FieldValidationError[] = []
  ) {
    super('ANOMALY_QUERY_VALIDATION_ERROR', message, {
      status: 422,
      retryable: false,
      fieldErrors,
    });
  }
}

/**
 * HTTP 503 Service Unavailable / 500 Server Error: 後端服務暫時無法回應
 */
export class AnomalyServiceUnavailableError extends AnomalyQueryError {
  public override readonly name = 'AnomalyServiceUnavailableError';

  constructor(message = '異常查詢服務暫時無法回應，請稍後重試 (HTTP 503)') {
    super('ANOMALY_QUERY_SERVICE_UNAVAILABLE', message, {
      status: 503,
      retryable: true,
    });
  }
}

/**
 * 網路傳輸或連線失敗
 */
export class AnomalyNetworkError extends AnomalyQueryError {
  public override readonly name = 'AnomalyNetworkError';

  constructor(message = '網路連線失敗，請檢查網路狀態', originalError?: unknown) {
    super('ANOMALY_QUERY_NETWORK_ERROR', message, {
      retryable: true,
      originalError,
    });
  }
}

/**
 * 請求已被 AbortSignal 中斷取消
 */
export class AnomalyAbortedError extends AnomalyQueryError {
  public override readonly name = 'AnomalyAbortedError';

  constructor(message = '異常查詢請求已被取消') {
    super('ANOMALY_QUERY_ABORTED', message, {
      retryable: false,
    });
  }
}

// ============================================================================
// Type Guards
// ============================================================================

export function isAnomalyQueryError(err: unknown): err is AnomalyQueryError {
  return err instanceof AnomalyQueryError;
}

export function isAnomalyUnauthenticatedError(
  err: unknown
): err is AnomalyUnauthenticatedError {
  return err instanceof AnomalyUnauthenticatedError;
}

export function isAnomalyForbiddenError(
  err: unknown
): err is AnomalyForbiddenError {
  return err instanceof AnomalyForbiddenError;
}

export function isAnomalyValidationError(
  err: unknown
): err is AnomalyValidationError {
  return err instanceof AnomalyValidationError;
}

export function isAnomalyServiceUnavailableError(
  err: unknown
): err is AnomalyServiceUnavailableError {
  return err instanceof AnomalyServiceUnavailableError;
}

export function isAnomalyNetworkError(
  err: unknown
): err is AnomalyNetworkError {
  return err instanceof AnomalyNetworkError;
}

export function isAnomalyAbortedError(
  err: unknown
): err is AnomalyAbortedError {
  return err instanceof AnomalyAbortedError;
}

// ============================================================================
// Error Mapping
// ============================================================================

/**
 * 將底層網路、HTTP 或解碼錯誤統一映射為 AnomalyQueryError
 */
export function mapErrorToAnomalyQueryError(
  err: unknown,
  context?: { endpoint?: string }
): AnomalyQueryError {
  if (err instanceof AnomalyQueryError) {
    return err;
  }

  if (err instanceof ApiAbortError) {
    return new AnomalyAbortedError(err.message);
  }

  if (err instanceof ApiTimeoutError) {
    return new AnomalyNetworkError(`請求逾時 (${err.timeoutMs} 毫秒)`, err);
  }

  if (err instanceof ApiNetworkError) {
    return new AnomalyNetworkError(err.message, err.originalError);
  }

  if (err instanceof ApiDecodeError) {
    const fieldErrors: FieldValidationError[] = err.issues.map((i) => ({
      field: i.path,
      message: i.message,
    }));
    return new AnomalyValidationError(err.message, fieldErrors);
  }

  if (err instanceof ApiHttpError) {
    if (err.status === 401) {
      return new AnomalyUnauthenticatedError(err.message);
    }
    if (err.status === 403) {
      return new AnomalyForbiddenError(err.message);
    }
    if (err.status === 422) {
      const raw = err.raw as Record<string, unknown> | undefined;
      const fieldErrors: FieldValidationError[] = [];
      if (raw && Array.isArray(raw.detail)) {
        for (const d of raw.detail as Array<{ loc?: unknown; msg?: unknown }>) {
          const field = Array.isArray(d.loc)
            ? d.loc.join('.')
            : typeof d.loc === 'string'
              ? d.loc
              : '';
          const message = typeof d.msg === 'string' ? d.msg : '';
          fieldErrors.push({ field, message });
        }
      }
      return new AnomalyValidationError(err.message, fieldErrors);
    }
    if (
      err.status === 503 ||
      err.status === 500 ||
      err.status === 502 ||
      err.status === 504
    ) {
      return new AnomalyServiceUnavailableError(err.message);
    }
    return new AnomalyQueryError(
      'ANOMALY_QUERY_VALIDATION_ERROR',
      `[HTTP ${err.status}] ${err.message}${context?.endpoint ? ` (${context.endpoint})` : ''}`,
      {
        status: err.status,
        retryable: err.retryable,
        originalError: err,
      }
    );
  }

  return new AnomalyNetworkError(extractErrorMessage(err), err);
}
