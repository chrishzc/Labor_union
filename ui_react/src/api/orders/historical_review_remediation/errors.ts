/**
 * File: errors.ts
 * Description: 將歷史訂單 review 更正失敗分流為去敏 typed error 並保留重試語意。
 */
import { ApiAbortError, ApiDecodeError, ApiHttpError, ApiNetworkError, ApiTimeoutError } from '../../shared/typed_errors';

export type HistoricalReviewRemediationOperation = 'query' | 'preview' | 'apply';

export class HistoricalReviewRemediationError extends Error {
  public readonly code: string;
  public readonly retryable: boolean;
  public readonly status: number | null;

  constructor(code: string, message: string, retryable = false, status: number | null = null) {
    super(message);
    this.name = 'HistoricalReviewRemediationError';
    this.code = code;
    this.retryable = retryable;
    this.status = status;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class HistoricalReviewRemediationContractError extends HistoricalReviewRemediationError {}
export class HistoricalReviewRemediationFileError extends HistoricalReviewRemediationError {}

export class HistoricalReviewRemediationUnauthenticatedError extends HistoricalReviewRemediationError {
  constructor(operation: HistoricalReviewRemediationOperation) {
    super(
      `historical_review_remediation_${operation}_unauthenticated`,
      operation === 'apply' ? '管理員 Session 已失效，無法套用歷史訂單更正。' : '管理員 Session 已失效，無法讀取歷史訂單更正。',
    );
    this.name = 'HistoricalReviewRemediationUnauthenticatedError';
  }
}

function mapError(error: unknown, operation: HistoricalReviewRemediationOperation): Error {
  if (error instanceof HistoricalReviewRemediationError || error instanceof ApiDecodeError) return error;
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return new HistoricalReviewRemediationUnauthenticatedError(operation);
    const message = error.status === 403
      ? '目前 Session 沒有歷史訂單 review 更正權限。'
      : error.status === 404
        ? '找不到指定的歷史訂單 review，請重新查詢。'
        : error.status === 409
          ? '歷史訂單 review 已變更或 Preview 已失效，請重新查詢後預覽。'
          : error.status === 422
            ? '歷史訂單更正資料未通過伺服器驗證，請依欄位衝突修正。'
            : error.status === 503
              ? '歷史訂單更正服務暫時無法使用，請保留相同 Idempotency-Key 重試。'
              : '歷史訂單 review 更正目前無法完成。';
    return new HistoricalReviewRemediationError(error.code || `HTTP_${error.status}`, message, error.retryable, error.status);
  }
  if (error instanceof ApiTimeoutError) {
    return new HistoricalReviewRemediationError(`historical_review_remediation_${operation}_timeout`, `${operation === 'apply' ? '套用' : operation === 'preview' ? '預覽' : '讀取'}逾時；請先重新查詢結果再決定是否重試。`, true);
  }
  if (error instanceof ApiNetworkError) return new HistoricalReviewRemediationError(`historical_review_remediation_${operation}_network_error`, '歷史訂單 review 更正連線失敗，請確認結果後重試。', true);
  if (error instanceof ApiAbortError) return new HistoricalReviewRemediationError(`historical_review_remediation_${operation}_aborted`, '歷史訂單 review 更正請求已取消，請先重新查詢結果。', true);
  return new HistoricalReviewRemediationError(`historical_review_remediation_${operation}_unexpected_error`, '歷史訂單 review 更正發生未預期錯誤。');
}

export function mapHistoricalReviewRemediationQueryError(error: unknown): Error {
  return mapError(error, 'query');
}
export function mapHistoricalReviewRemediationPreviewError(error: unknown): Error {
  return mapError(error, 'preview');
}
export function mapHistoricalReviewRemediationApplyError(error: unknown): Error {
  return mapError(error, 'apply');
}

export function mapHistoricalReviewRemediationError(error: unknown): HistoricalReviewRemediationError {
  const mapped = mapError(error, 'query');
  return mapped instanceof HistoricalReviewRemediationError
    ? mapped
    : new HistoricalReviewRemediationError('historical_review_remediation_error', mapped.message);
}
