/**
 * File: hcm_import_result_errors.ts
 * Description: 收斂 HCM 結果查詢的驗證、認證與傳輸錯誤，避免raw payload進入畫面。
 */
import { ApiHttpError } from '../shared/typed_errors';

export class HcmImportResultError extends Error {
  public readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'HcmImportResultError';
    this.code = code;
  }
}

export function mapHcmImportResultError(error: unknown): Error {
  if (error instanceof HcmImportResultError) return error;
  if (error instanceof ApiHttpError) {
    return new HcmImportResultError(error.code, 'HCM 匯入結果目前無法取得。');
  }
  return error instanceof Error
    ? error
    : new HcmImportResultError('hcm_result_unknown', 'HCM 匯入結果目前無法取得。');
}
