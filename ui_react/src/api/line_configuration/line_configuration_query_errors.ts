/**
 * File: line_configuration_query_errors.ts
 * Description: 收斂 LINE 設定唯讀查詢的認證、契約與傳輸失敗，不暴露原始回應。
 */
import {
  ApiAbortError,
  ApiDecodeError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
} from '../shared/typed_errors';

export type LineConfigurationQueryErrorCode =
  | 'line_configuration_query_unauthenticated'
  | 'line_configuration_query_forbidden'
  | 'line_configuration_query_not_found'
  | 'line_configuration_query_contract_mismatch'
  | 'line_configuration_query_request_invalid'
  | 'line_configuration_query_unavailable'
  | 'line_configuration_query_network'
  | 'line_configuration_query_aborted';

export class LineConfigurationQueryError extends Error {
  public readonly code: LineConfigurationQueryErrorCode;
  public readonly status: number | null;
  public readonly retryable: boolean;

  constructor(
    code: LineConfigurationQueryErrorCode,
    message: string,
    options: { status?: number | null; retryable?: boolean } = {}
  ) {
    super(message);
    this.name = 'LineConfigurationQueryError';
    this.code = code;
    this.status = options.status ?? null;
    this.retryable = options.retryable ?? false;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class LineConfigurationQueryUnauthenticatedError extends LineConfigurationQueryError {
  constructor() {
    super(
      'line_configuration_query_unauthenticated',
      '管理員 Session 已失效，無法讀取 LINE 設定。',
      { status: 401 }
    );
    this.name = 'LineConfigurationQueryUnauthenticatedError';
  }
}

export class LineConfigurationQueryContractError extends LineConfigurationQueryError {
  constructor(message = 'LINE 設定回應不符合已核准的公開契約。') {
    super('line_configuration_query_contract_mismatch', message);
    this.name = 'LineConfigurationQueryContractError';
  }
}

export class LineConfigurationQueryRequestError extends LineConfigurationQueryError {
  constructor(message: string) {
    super('line_configuration_query_request_invalid', message, { status: 422 });
    this.name = 'LineConfigurationQueryRequestError';
  }
}

export function mapLineConfigurationQueryError(error: unknown): Error {
  if (error instanceof LineConfigurationQueryError) return error;
  if (error instanceof ApiDecodeError) {
    return new LineConfigurationQueryContractError();
  }
  if (error instanceof ApiAbortError) {
    return new LineConfigurationQueryError(
      'line_configuration_query_aborted',
      'LINE 設定查詢已取消。'
    );
  }
  if (error instanceof ApiTimeoutError) {
    return new LineConfigurationQueryError(
      'line_configuration_query_unavailable',
      'LINE 設定查詢逾時，尚未取得可用資料。',
      { retryable: true }
    );
  }
  if (error instanceof ApiNetworkError) {
    return new LineConfigurationQueryError(
      'line_configuration_query_network',
      'LINE 設定查詢連線失敗，尚未取得可用資料。',
      { retryable: true }
    );
  }
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return new LineConfigurationQueryUnauthenticatedError();
    if (error.status === 403) {
      return new LineConfigurationQueryError(
        'line_configuration_query_forbidden',
        '目前 Session 沒有讀取 LINE 設定的權限。',
        { status: 403 }
      );
    }
    if (error.status === 404) {
      return new LineConfigurationQueryError(
        'line_configuration_query_not_found',
        '指定的 Rich Menu 發布紀錄不存在。',
        { status: 404 }
      );
    }
    if ([500, 502, 503, 504].includes(error.status)) {
      return new LineConfigurationQueryError(
        'line_configuration_query_unavailable',
        'LINE 設定查詢服務暫時無法回應。',
        { status: error.status, retryable: true }
      );
    }
    return new LineConfigurationQueryError(
      'line_configuration_query_request_invalid',
      'LINE 設定查詢遭伺服器拒絕。',
      { status: error.status, retryable: error.retryable }
    );
  }
  return new LineConfigurationQueryError(
    'line_configuration_query_network',
    'LINE 設定查詢發生未預期的連線錯誤。',
    { retryable: true }
  );
}
