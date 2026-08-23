/**
 * File: hcm_workbook_errors.ts
 * Description: 將HCM Preview／Apply失敗分流為去敏typed錯誤，標示安全重試狀態。
 */
import {
  ApiAbortError,
  ApiDecodeError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
} from '../shared/typed_errors';

export class HcmWorkbookPreviewError extends Error {
  public readonly code: string;
  public readonly retryable: boolean;
  public readonly status: number | null;

  constructor(
    code: string,
    message: string,
    options: { retryable?: boolean; status?: number | null } = {}
  ) {
    super(message);
    this.name = 'HcmWorkbookPreviewError';
    this.code = code;
    this.retryable = options.retryable ?? false;
    this.status = options.status ?? null;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class HcmWorkbookFileError extends HcmWorkbookPreviewError {
  constructor(code: string, message: string) {
    super(code, message);
    this.name = 'HcmWorkbookFileError';
  }
}

export class HcmWorkbookUnauthenticatedError extends HcmWorkbookPreviewError {
  constructor(operation: 'preview' | 'apply' = 'preview') {
    super(
      `hcm_${operation}_unauthenticated`,
      operation === 'apply' ? '管理員 Session 已失效，無法套用 HCM 檔案。' : '管理員 Session 已失效，無法預覽 HCM 檔案。'
    );
    this.name = 'HcmWorkbookUnauthenticatedError';
  }
}

export class HcmWorkbookContractError extends HcmWorkbookPreviewError {
  constructor(code: string, message: string) {
    super(code, message);
    this.name = 'HcmWorkbookContractError';
  }
}

export class HcmWorkbookApplyError extends HcmWorkbookPreviewError {
  constructor(code: string, message: string, options: { retryable?: boolean; status?: number | null } = {}) {
    super(code, message, options);
    this.name = 'HcmWorkbookApplyError';
  }
}

export function mapHcmWorkbookPreviewError(error: unknown): Error {
  if (
    error instanceof HcmWorkbookPreviewError ||
    error instanceof ApiDecodeError
  ) {
    return error;
  }

  if (error instanceof ApiHttpError) {
    if (error.status === 401) {
      return new HcmWorkbookUnauthenticatedError();
    }
    if (error.status === 403) {
      return new HcmWorkbookPreviewError(
        'hcm_preview_forbidden',
        '目前 Session 沒有預覽 HCM 檔案的權限。',
        { status: error.status }
      );
    }
    if (error.status === 422) {
      return new HcmWorkbookPreviewError(
        error.code || 'hcm_preview_rejected',
        'HCM 檔案未通過伺服器預覽驗證。',
        { status: error.status }
      );
    }
    return new HcmWorkbookPreviewError(
      error.code || `HTTP_${error.status}`,
      'HCM 檔案預覽目前無法完成。',
      { status: error.status, retryable: error.retryable }
    );
  }

  if (error instanceof ApiTimeoutError) {
    return new HcmWorkbookPreviewError(
      'hcm_preview_timeout',
      'HCM 檔案預覽逾時，尚未產生可用預覽。',
      { retryable: true }
    );
  }

  if (error instanceof ApiNetworkError) {
    return new HcmWorkbookPreviewError(
      'hcm_preview_network_error',
      'HCM 檔案預覽連線失敗，尚未產生可用預覽。',
      { retryable: true }
    );
  }

  if (error instanceof ApiAbortError) {
    return new HcmWorkbookPreviewError(
      'hcm_preview_aborted',
      'HCM 檔案預覽已取消。',
      { retryable: true }
    );
  }

  return new HcmWorkbookPreviewError(
    'hcm_preview_unexpected_error',
    'HCM 檔案預覽發生未預期錯誤。'
  );
}

export function mapHcmWorkbookApplyError(error: unknown): Error {
  if (
    error instanceof HcmWorkbookApplyError
    || error instanceof HcmWorkbookContractError
    || error instanceof HcmWorkbookFileError
    || error instanceof HcmWorkbookUnauthenticatedError
    || error instanceof ApiDecodeError
  ) return error;
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return new HcmWorkbookUnauthenticatedError('apply');
    const message = error.status === 403
      ? '目前 Session 沒有套用 HCM 檔案的權限。'
      : error.status === 409
        ? 'HCM 檔案套用與既有操作衝突，請重新預覽後再試。'
        : error.status === 422
          ? 'HCM 檔案未通過套用驗證，請重新預覽。'
          : error.status === 503
            ? 'HCM 檔案套用服務暫時無法使用，請以相同 Idempotency-Key 重試。'
            : 'HCM 檔案套用目前無法完成。';
    return new HcmWorkbookApplyError(error.code || `HTTP_${error.status}`, message, { retryable: error.retryable, status: error.status });
  }
  if (error instanceof ApiTimeoutError) return new HcmWorkbookApplyError('hcm_apply_timeout', 'HCM 檔案套用逾時，請以相同 Idempotency-Key 重試。', { retryable: true });
  if (error instanceof ApiNetworkError) return new HcmWorkbookApplyError('hcm_apply_network_error', 'HCM 檔案套用連線失敗，請以相同 Idempotency-Key 重試。', { retryable: true });
  if (error instanceof ApiAbortError) return new HcmWorkbookApplyError('hcm_apply_aborted', 'HCM 檔案套用已取消，請先確認結果再重試。', { retryable: true });
  return new HcmWorkbookApplyError('hcm_apply_unexpected_error', 'HCM 檔案套用發生未預期錯誤。');
}
