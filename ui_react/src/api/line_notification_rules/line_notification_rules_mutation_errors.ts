/**
 * File: line_notification_rules_mutation_errors.ts
 * Description: 收斂通知規則 mutation 的認證、契約、衝突與傳輸錯誤，避免 raw payload 穿透 UI。
 */
import {
  ApiAbortError,
  ApiDecodeError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
} from '../shared/typed_errors';

export class LineNotificationRulesMutationError extends Error {
  public readonly code: string;
  public readonly status: number | null;
  public readonly retryable: boolean;

  constructor(
    code: string,
    message: string,
    options: { status?: number | null; retryable?: boolean } = {}
  ) {
    super(message);
    this.name = 'LineNotificationRulesMutationError';
    this.code = code;
    this.status = options.status ?? null;
    this.retryable = options.retryable ?? false;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class LineNotificationRulesMutationRequestError extends LineNotificationRulesMutationError {
  constructor(message: string) {
    super('line_notification_rule_request_invalid', message, { status: 422 });
    this.name = 'LineNotificationRulesMutationRequestError';
  }
}

export class LineNotificationRulesMutationUnauthenticatedError extends LineNotificationRulesMutationError {
  constructor() {
    super(
      'line_notification_rule_unauthenticated',
      '管理員 Session 已失效，無法修改 LINE 通知規則。',
      { status: 401 }
    );
    this.name = 'LineNotificationRulesMutationUnauthenticatedError';
  }
}

export function mapLineNotificationRulesMutationError(error: unknown): Error {
  if (error instanceof LineNotificationRulesMutationError) return error;
  if (error instanceof ApiDecodeError) {
    return new LineNotificationRulesMutationError(
      'line_notification_rule_contract_mismatch',
      'LINE 通知規則回應不符合已核准的公開契約。'
    );
  }
  if (error instanceof ApiAbortError) {
    return new LineNotificationRulesMutationError(
      'line_notification_rule_aborted',
      'LINE 通知規則操作已取消。'
    );
  }
  if (error instanceof ApiTimeoutError) {
    return new LineNotificationRulesMutationError(
      'line_notification_rule_unavailable',
      'LINE 通知規則服務逾時，請重新查詢後再試。',
      { retryable: true }
    );
  }
  if (error instanceof ApiNetworkError) {
    return new LineNotificationRulesMutationError(
      'line_notification_rule_network',
      'LINE 通知規則服務連線失敗。',
      { retryable: true }
    );
  }
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return new LineNotificationRulesMutationUnauthenticatedError();
    if (error.status === 403) {
      return new LineNotificationRulesMutationError(
        'line_notification_rule_forbidden',
        '目前 Session 沒有修改 LINE 通知規則的權限。',
        { status: 403 }
      );
    }
    if (error.status === 404) {
      return new LineNotificationRulesMutationError(
        error.code,
        '指定的 LINE 通知規則不存在，請重新整理目錄。',
        { status: 404 }
      );
    }
    if (error.status === 409) {
      return new LineNotificationRulesMutationError(
        error.code,
        '通知規則版本或預覽已過期，請重新整理並再次預覽。',
        { status: 409 }
      );
    }
    if (error.status === 422) {
      return new LineNotificationRulesMutationRequestError(
        '通知規則內容未通過後端驗證，請檢查欄位。'
      );
    }
    if ([500, 502, 503, 504].includes(error.status)) {
      return new LineNotificationRulesMutationError(
        error.code,
        'LINE 通知規則服務暫時無法回應。',
        { status: error.status, retryable: true }
      );
    }
    return new LineNotificationRulesMutationError(
      error.code,
      'LINE 通知規則操作遭伺服器拒絕。',
      { status: error.status, retryable: error.retryable }
    );
  }
  return new LineNotificationRulesMutationError(
    'line_notification_rule_unknown',
    'LINE 通知規則操作發生未預期錯誤。'
  );
}
