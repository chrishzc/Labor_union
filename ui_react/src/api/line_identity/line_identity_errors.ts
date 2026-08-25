/**
 * File: line_identity_errors.ts
 * Description: 將 LINE 身分查詢、審核、更正、解除及維護錯誤映射為不洩漏原始內容的前端 typed error。
 */
import {
  ApiAbortError,
  ApiDecodeError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
} from '../shared/typed_errors';
import { ZodError } from 'zod';

export type LineIdentityOperation = 'query' | 'preview' | 'apply';

export type LineIdentityDomainErrorCode =
  | 'line_identity_binding_not_found'
  | 'line_identity_binding_version_conflict'
  | 'line_identity_revocation_in_progress'
  | 'line_identity_default_menu_not_published'
  | 'line_identity_owner_projection_conflict'
  | 'line_identity_menu_reset_failed'
  | 'line_identity_manual_completion_forbidden'
  | 'line_identity_binding_not_bound'
  | 'line_identity_subject_unchanged'
  | 'line_identity_replacement_subject_not_found'
  | 'line_identity_replacement_subject_already_bound'
  | 'line_identity_revocation_not_retryable'
  | 'line_review_state_conflict'
  | 'line_review_version_conflict'
  | 'line_review_data_conflict';

export type LineIdentityClientErrorCode =
  | 'UNAUTHENTICATED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'CONFLICT'
  | 'REQUEST_INVALID'
  | 'CONTRACT_MISMATCH'
  | 'SERVICE_UNAVAILABLE'
  | 'NETWORK_FAILURE'
  | 'TIMEOUT'
  | 'ABORTED'
  | 'BACKEND_REJECTED';

const DOMAIN_ERROR_CODES = new Set<LineIdentityDomainErrorCode>([
  'line_identity_binding_not_found',
  'line_identity_binding_version_conflict',
  'line_identity_revocation_in_progress',
  'line_identity_default_menu_not_published',
  'line_identity_owner_projection_conflict',
  'line_identity_menu_reset_failed',
  'line_identity_manual_completion_forbidden',
  'line_identity_binding_not_bound',
  'line_identity_subject_unchanged',
  'line_identity_replacement_subject_not_found',
  'line_identity_replacement_subject_already_bound',
  'line_identity_revocation_not_retryable',
  'line_review_state_conflict',
  'line_review_version_conflict',
  'line_review_data_conflict',
]);

export class LineIdentityClientError extends Error {
  public readonly name = 'LineIdentityClientError';
  public readonly code: LineIdentityClientErrorCode;
  public readonly status?: number;
  public readonly retryable: boolean;
  public readonly outcomeUnknown: boolean;
  public readonly domainCode?: LineIdentityDomainErrorCode;

  constructor(
    code: LineIdentityClientErrorCode,
    message: string,
    options: {
      status?: number;
      retryable?: boolean;
      outcomeUnknown?: boolean;
      domainCode?: LineIdentityDomainErrorCode;
    } = {}
  ) {
    super(message);
    Object.setPrototypeOf(this, new.target.prototype);
    this.code = code;
    this.status = options.status;
    this.retryable = options.retryable ?? false;
    this.outcomeUnknown = options.outcomeUnknown ?? false;
    this.domainCode = options.domainCode;
  }
}

function asDomainCode(code: string): LineIdentityDomainErrorCode | undefined {
  if (DOMAIN_ERROR_CODES.has(code as LineIdentityDomainErrorCode)) {
    return code as LineIdentityDomainErrorCode;
  }
  return undefined;
}

function isUnknownApplyOutcome(operation: LineIdentityOperation): boolean {
  return operation === 'apply';
}

export function mapLineIdentityError(
  error: unknown,
  operation: LineIdentityOperation
): LineIdentityClientError {
  if (error instanceof LineIdentityClientError) {
    return error;
  }

  if (error instanceof ApiDecodeError) {
    return new LineIdentityClientError(
      'CONTRACT_MISMATCH',
      'LINE 身分管理服務回應不符合已凍結契約，操作已安全停止。'
    );
  }

  if (error instanceof ZodError) {
    return new LineIdentityClientError(
      'REQUEST_INVALID',
      'LINE 身分管理請求欄位不符合已凍結契約。'
    );
  }

  if (error instanceof ApiAbortError) {
    return new LineIdentityClientError('ABORTED', 'LINE 身分管理請求已取消。');
  }

  if (error instanceof ApiTimeoutError) {
    return new LineIdentityClientError('TIMEOUT', 'LINE 身分管理請求逾時。', {
      retryable: true,
      outcomeUnknown: isUnknownApplyOutcome(operation),
    });
  }

  if (error instanceof ApiNetworkError) {
    return new LineIdentityClientError(
      'NETWORK_FAILURE',
      'LINE 身分管理服務連線失敗。',
      {
        retryable: true,
        outcomeUnknown: isUnknownApplyOutcome(operation),
      }
    );
  }

  if (error instanceof ApiHttpError) {
    const domainCode = asDomainCode(error.code);
    if (error.status === 401) {
      return new LineIdentityClientError('UNAUTHENTICATED', '登入已失效，請重新登入。', {
        status: 401,
      });
    }
    if (error.status === 403) {
      return new LineIdentityClientError('FORBIDDEN', '目前帳號無法執行此操作。', {
        status: 403,
      });
    }
    if (error.status === 404) {
      return new LineIdentityClientError('NOT_FOUND', '找不到指定的 LINE 身分或審核紀錄。', {
        status: 404,
        domainCode,
      });
    }
    if (error.status === 409) {
      return new LineIdentityClientError(
        'CONFLICT',
        'LINE 身分或審核紀錄已變更，請重新查詢並再次預覽。',
        { status: 409, domainCode }
      );
    }
    if (error.status === 422) {
      return new LineIdentityClientError(
        'REQUEST_INVALID',
        'LINE 身分管理請求欄位不符合契約。',
        { status: 422 }
      );
    }
    if ([500, 502, 503, 504].includes(error.status)) {
      return new LineIdentityClientError(
        'SERVICE_UNAVAILABLE',
        'LINE 身分管理服務暫時無法使用。',
        {
          status: error.status,
          retryable: true,
          outcomeUnknown: isUnknownApplyOutcome(operation),
          domainCode,
        }
      );
    }
    return new LineIdentityClientError(
      'BACKEND_REJECTED',
      'LINE 身分管理服務拒絕此次請求。',
      { status: error.status, domainCode }
    );
  }

  return new LineIdentityClientError(
    'NETWORK_FAILURE',
    'LINE 身分管理請求發生未分類錯誤。',
    { outcomeUnknown: isUnknownApplyOutcome(operation) }
  );
}
