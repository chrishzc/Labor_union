/**
 * File: errors.ts
 * Description: 將Client BeClass Preview／Apply失敗分流為去敏typed錯誤，標示安全重試狀態。
 */
import {
  ApiAbortError,
  ApiDecodeError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
} from '../../shared/typed_errors';

export class ClientBeClassWorkbookPreviewError extends Error {
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
    this.name = 'ClientBeClassWorkbookPreviewError';
    this.code = code;
    this.retryable = retryable;
    this.status = status;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class ClientBeClassWorkbookContractError extends ClientBeClassWorkbookPreviewError {}
export class ClientBeClassWorkbookFileError extends ClientBeClassWorkbookPreviewError {}

export class ClientBeClassWorkbookApplyError extends ClientBeClassWorkbookPreviewError {
  constructor(code: string, message: string, retryable = false, status: number | null = null) {
    super(code, message, retryable, status);
    this.name = 'ClientBeClassWorkbookApplyError';
  }
}

export class ClientBeClassWorkbookUnauthenticatedError extends ClientBeClassWorkbookPreviewError {
  constructor(operation: 'preview' | 'apply' = 'preview') {
    super(
      `client_beclass_${operation}_unauthenticated`,
      operation === 'apply' ? '管理員 Session 已失效，無法套用客戶 BeClass 檔案。' : '管理員 Session 已失效，無法預覽客戶 BeClass 檔案。'
    );
  }
}

export function mapClientBeClassWorkbookPreviewError(error: unknown): Error {
  if (error instanceof ClientBeClassWorkbookPreviewError || error instanceof ApiDecodeError) return error;
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return new ClientBeClassWorkbookUnauthenticatedError();
    const message = error.status === 403
      ? '目前 Session 沒有預覽客戶 BeClass 檔案的權限。'
      : error.status === 422
        ? '客戶 BeClass 檔案未通過伺服器預覽驗證。'
        : '客戶 BeClass 檔案預覽目前無法完成。';
    return new ClientBeClassWorkbookPreviewError(
      error.code || `HTTP_${error.status}`,
      message,
      error.retryable,
      error.status
    );
  }
  if (error instanceof ApiTimeoutError) return new ClientBeClassWorkbookPreviewError('client_beclass_preview_timeout', '客戶 BeClass 檔案預覽逾時。', true);
  if (error instanceof ApiNetworkError) return new ClientBeClassWorkbookPreviewError('client_beclass_preview_network_error', '客戶 BeClass 檔案預覽連線失敗。', true);
  if (error instanceof ApiAbortError) return new ClientBeClassWorkbookPreviewError('client_beclass_preview_aborted', '客戶 BeClass 檔案預覽已取消。', true);
  return new ClientBeClassWorkbookPreviewError('client_beclass_preview_unexpected_error', '客戶 BeClass 檔案預覽發生未預期錯誤。');
}

export function mapClientBeClassWorkbookApplyError(error: unknown): Error {
  if (
    error instanceof ClientBeClassWorkbookApplyError
    || error instanceof ClientBeClassWorkbookContractError
    || error instanceof ClientBeClassWorkbookFileError
    || error instanceof ClientBeClassWorkbookUnauthenticatedError
    || error instanceof ApiDecodeError
  ) return error;
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return new ClientBeClassWorkbookUnauthenticatedError('apply');
    const message = error.status === 403
      ? '目前 Session 沒有套用客戶 BeClass 檔案的權限。'
      : error.status === 409
        ? '客戶 BeClass 檔案套用與既有操作衝突，請重新預覽後再試。'
        : error.status === 422
          ? '客戶 BeClass 檔案未通過套用驗證，請重新預覽。'
          : error.status === 503
            ? '客戶 BeClass 匯入服務暫時無法回覆，結果尚未確認。請保留本頁，稍後點選「查詢這次匯入結果」。'
            : '客戶 BeClass 檔案套用目前無法完成。';
    return new ClientBeClassWorkbookApplyError(error.code || `HTTP_${error.status}`, message, error.retryable, error.status);
  }
  if (error instanceof ApiTimeoutError) return new ClientBeClassWorkbookApplyError('client_beclass_apply_timeout', '等待客戶 BeClass 匯入回應逾時，結果尚未確認，資料可能已寫入。請保留本頁並點選「查詢這次匯入結果」，勿重新上傳。', true);
  if (error instanceof ApiNetworkError) return new ClientBeClassWorkbookApplyError('client_beclass_apply_network_error', '客戶 BeClass 匯入連線中斷，結果尚未確認，資料可能已寫入。請保留本頁並點選「查詢這次匯入結果」，勿重新上傳。', true);
  if (error instanceof ApiAbortError) return new ClientBeClassWorkbookApplyError('client_beclass_apply_aborted', '已停止等待客戶 BeClass 匯入回應，結果尚未確認。請保留本頁並點選「查詢這次匯入結果」。', true);
  return new ClientBeClassWorkbookApplyError('client_beclass_apply_unexpected_error', '客戶 BeClass 檔案套用發生未預期錯誤。');
}
