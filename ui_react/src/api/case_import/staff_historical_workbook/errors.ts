/**
 * File: errors.ts
 * Description: 將Staff Historical Preview／Apply失敗分流為去敏typed錯誤，標示安全重試狀態。
 */
import { ApiAbortError, ApiDecodeError, ApiHttpError, ApiNetworkError, ApiTimeoutError } from '../../shared/typed_errors';

export class StaffHistoricalWorkbookPreviewError extends Error {
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
    this.name = 'StaffHistoricalWorkbookPreviewError';
    this.code = code;
    this.retryable = retryable;
    this.status = status;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class StaffHistoricalWorkbookContractError extends StaffHistoricalWorkbookPreviewError {}
export class StaffHistoricalWorkbookFileError extends StaffHistoricalWorkbookPreviewError {}

export class StaffHistoricalWorkbookApplyError extends StaffHistoricalWorkbookPreviewError {
  constructor(code: string, message: string, retryable = false, status: number | null = null) {
    super(code, message, retryable, status);
    this.name = 'StaffHistoricalWorkbookApplyError';
  }
}

export class StaffHistoricalWorkbookUnauthenticatedError extends StaffHistoricalWorkbookPreviewError {
  constructor(operation: 'preview' | 'apply' = 'preview') {
    super(
      `staff_historical_${operation}_unauthenticated`,
      operation === 'apply' ? '管理員 Session 已失效，無法套用月嫂歷史檔案。' : '管理員 Session 已失效，無法預覽月嫂歷史檔案。'
    );
  }
}

export function mapStaffHistoricalWorkbookPreviewError(error: unknown): Error {
  if (error instanceof StaffHistoricalWorkbookPreviewError || error instanceof ApiDecodeError) return error;
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return new StaffHistoricalWorkbookUnauthenticatedError();
    const message = error.status === 403
      ? '目前 Session 沒有預覽月嫂歷史檔案的權限。'
      : error.status === 422
        ? '月嫂歷史檔案未通過伺服器預覽驗證。'
        : '月嫂歷史檔案預覽目前無法完成。';
    return new StaffHistoricalWorkbookPreviewError(error.code || `HTTP_${error.status}`, message, error.retryable, error.status);
  }
  if (error instanceof ApiTimeoutError) return new StaffHistoricalWorkbookPreviewError('staff_historical_preview_timeout', '月嫂歷史檔案預覽逾時。', true);
  if (error instanceof ApiNetworkError) return new StaffHistoricalWorkbookPreviewError('staff_historical_preview_network_error', '月嫂歷史檔案預覽連線失敗。', true);
  if (error instanceof ApiAbortError) return new StaffHistoricalWorkbookPreviewError('staff_historical_preview_aborted', '月嫂歷史檔案預覽已取消。', true);
  return new StaffHistoricalWorkbookPreviewError('staff_historical_preview_unexpected_error', '月嫂歷史檔案預覽發生未預期錯誤。');
}

export function mapStaffHistoricalWorkbookApplyError(error: unknown): Error {
  if (
    error instanceof StaffHistoricalWorkbookApplyError
    || error instanceof StaffHistoricalWorkbookContractError
    || error instanceof StaffHistoricalWorkbookFileError
    || error instanceof StaffHistoricalWorkbookUnauthenticatedError
    || error instanceof ApiDecodeError
  ) return error;
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return new StaffHistoricalWorkbookUnauthenticatedError('apply');
    const message = error.status === 403
      ? '目前 Session 沒有套用月嫂歷史檔案的權限。'
      : error.status === 409
        ? '月嫂歷史檔案套用與既有操作衝突，請重新預覽後再試。'
        : error.status === 422
          ? '月嫂歷史檔案未通過套用驗證，請重新預覽。'
          : error.status === 503
            ? '月嫂歷史檔案套用服務暫時無法使用，請稍後以相同 Idempotency-Key 重試。'
            : '月嫂歷史檔案套用目前無法完成。';
    return new StaffHistoricalWorkbookApplyError(error.code || `HTTP_${error.status}`, message, error.retryable, error.status);
  }
  if (error instanceof ApiTimeoutError) return new StaffHistoricalWorkbookApplyError('staff_historical_apply_timeout', '月嫂歷史檔案套用逾時，請以相同 Idempotency-Key 重試。', true);
  if (error instanceof ApiNetworkError) return new StaffHistoricalWorkbookApplyError('staff_historical_apply_network_error', '月嫂歷史檔案套用連線失敗，請以相同 Idempotency-Key 重試。', true);
  if (error instanceof ApiAbortError) return new StaffHistoricalWorkbookApplyError('staff_historical_apply_aborted', '月嫂歷史檔案套用已取消，請先確認結果再重試。', true);
  return new StaffHistoricalWorkbookApplyError('staff_historical_apply_unexpected_error', '月嫂歷史檔案套用發生未預期錯誤。');
}
