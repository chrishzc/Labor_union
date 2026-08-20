/**
 * File: hcm_workbook_errors.ts
 * Description: 將 HCM Preview 的本機、HTTP 與傳輸失敗收斂為去敏型別錯誤。
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
  constructor() {
    super('hcm_preview_unauthenticated', '管理員 Session 已失效，無法預覽 HCM 檔案。');
    this.name = 'HcmWorkbookUnauthenticatedError';
  }
}

export class HcmWorkbookContractError extends HcmWorkbookPreviewError {
  constructor(code: string, message: string) {
    super(code, message);
    this.name = 'HcmWorkbookContractError';
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
