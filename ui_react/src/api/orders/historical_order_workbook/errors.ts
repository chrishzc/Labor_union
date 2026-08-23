/**
 * File: errors.ts
 * Description: 將Historical Orders Preview／Apply失敗分流為去敏typed錯誤，標示安全重試狀態。
 */
import { ApiAbortError, ApiDecodeError, ApiHttpError, ApiNetworkError, ApiTimeoutError } from '../../shared/typed_errors';

export class HistoricalOrderWorkbookPreviewError extends Error {
  public readonly code: string;
  public readonly retryable: boolean;
  public readonly status: number | null;

  constructor(
    code: string,
    message: string,
    retryable = false,
    status: number | null = null
  ) {
    super(message);
    this.name = 'HistoricalOrderWorkbookPreviewError';
    this.code = code;
    this.retryable = retryable;
    this.status = status;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class HistoricalOrderWorkbookContractError extends HistoricalOrderWorkbookPreviewError {}
export class HistoricalOrderWorkbookFileError extends HistoricalOrderWorkbookPreviewError {}

export class HistoricalOrderWorkbookApplyError extends HistoricalOrderWorkbookPreviewError {
  constructor(code: string, message: string, retryable = false, status: number | null = null) {
    super(code, message, retryable, status);
    this.name = 'HistoricalOrderWorkbookApplyError';
  }
}

export class HistoricalOrderWorkbookUnauthenticatedError extends HistoricalOrderWorkbookPreviewError {
  constructor(operation: 'preview' | 'apply' = 'preview') {
    super(
      `historical_order_${operation}_unauthenticated`,
      operation === 'apply' ? '管理員 Session 已失效，無法套用歷史訂單檔案。' : '管理員 Session 已失效，無法預覽歷史訂單檔案。'
    );
  }
}

export function mapHistoricalOrderWorkbookPreviewError(error: unknown): Error {
  if (error instanceof HistoricalOrderWorkbookPreviewError || error instanceof ApiDecodeError) return error;
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return new HistoricalOrderWorkbookUnauthenticatedError();
    const message = error.status === 403
      ? '目前 Session 沒有預覽歷史訂單檔案的權限。'
      : error.status === 422
        ? '歷史訂單檔案未通過伺服器預覽驗證。'
        : '歷史訂單檔案預覽目前無法完成。';
    return new HistoricalOrderWorkbookPreviewError(error.code || `HTTP_${error.status}`, message, error.retryable, error.status);
  }
  if (error instanceof ApiTimeoutError) return new HistoricalOrderWorkbookPreviewError('historical_order_preview_timeout', '歷史訂單檔案預覽逾時。', true);
  if (error instanceof ApiNetworkError) return new HistoricalOrderWorkbookPreviewError('historical_order_preview_network_error', '歷史訂單檔案預覽連線失敗。', true);
  if (error instanceof ApiAbortError) return new HistoricalOrderWorkbookPreviewError('historical_order_preview_aborted', '歷史訂單檔案預覽已取消。', true);
  return new HistoricalOrderWorkbookPreviewError('historical_order_preview_unexpected_error', '歷史訂單檔案預覽發生未預期錯誤。');
}

export function mapHistoricalOrderWorkbookApplyError(error: unknown): Error {
  if (
    error instanceof HistoricalOrderWorkbookApplyError
    || error instanceof HistoricalOrderWorkbookContractError
    || error instanceof HistoricalOrderWorkbookFileError
    || error instanceof HistoricalOrderWorkbookUnauthenticatedError
    || error instanceof ApiDecodeError
  ) return error;
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return new HistoricalOrderWorkbookUnauthenticatedError('apply');
    const message = error.status === 403
      ? '目前 Session 沒有套用歷史訂單檔案的權限。'
      : error.status === 409
        ? '歷史訂單檔案套用與既有操作衝突，請重新預覽後再試。'
        : error.status === 422
          ? '歷史訂單檔案未通過套用驗證，請重新預覽。'
          : error.status === 503
            ? '歷史訂單檔案套用服務暫時無法使用，請以相同 Idempotency-Key 重試。'
            : '歷史訂單檔案套用目前無法完成。';
    return new HistoricalOrderWorkbookApplyError(error.code || `HTTP_${error.status}`, message, error.retryable, error.status);
  }
  if (error instanceof ApiTimeoutError) return new HistoricalOrderWorkbookApplyError('historical_order_apply_timeout', '歷史訂單檔案套用逾時，請以相同 Idempotency-Key 重試。', true);
  if (error instanceof ApiNetworkError) return new HistoricalOrderWorkbookApplyError('historical_order_apply_network_error', '歷史訂單檔案套用連線失敗，請以相同 Idempotency-Key 重試。', true);
  if (error instanceof ApiAbortError) return new HistoricalOrderWorkbookApplyError('historical_order_apply_aborted', '歷史訂單檔案套用已取消，請先確認結果再重試。', true);
  return new HistoricalOrderWorkbookApplyError('historical_order_apply_unexpected_error', '歷史訂單檔案套用發生未預期錯誤。');
}
