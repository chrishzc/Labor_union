/**
 * File: line_rich_menu_publication_errors.ts
 * Description: 將 Rich Menu 發布 transport、契約與業務失敗轉為可判別的 typed error。
 */
import {
  ApiAbortError,
  ApiDecodeError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
} from '../shared/typed_errors';

export type LineRichMenuPublicationErrorCategory =
  | 'request'
  | 'unauthenticated'
  | 'forbidden'
  | 'not_found'
  | 'conflict'
  | 'validation'
  | 'unavailable'
  | 'contract';

export class LineRichMenuPublicationError extends Error {
  public override readonly name: string = 'LineRichMenuPublicationError';
  public readonly category: LineRichMenuPublicationErrorCategory;
  public readonly code: string;
  public readonly status?: number;
  public readonly retryable: boolean;

  constructor(
    category: LineRichMenuPublicationErrorCategory,
    code: string,
    message: string,
    status?: number,
    retryable = false
  ) {
    super(message);
    this.category = category;
    this.code = code;
    this.status = status;
    this.retryable = retryable;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class LineRichMenuPublicationRequestError extends LineRichMenuPublicationError {
  public override readonly name: string = 'LineRichMenuPublicationRequestError';

  constructor(message: string) {
    super('request', 'line_rich_menu_publication_request_invalid', message, 422);
  }
}

export class LineRichMenuPublicationUnauthenticatedError extends LineRichMenuPublicationError {
  public override readonly name: string = 'LineRichMenuPublicationUnauthenticatedError';

  constructor() {
    super(
      'unauthenticated',
      'line_rich_menu_publication_unauthenticated',
      '管理員 Session 已失效，請重新登入。',
      401
    );
  }
}

export function mapLineRichMenuPublicationError(error: unknown): Error {
  if (error instanceof LineRichMenuPublicationError || error instanceof ApiAbortError) {
    return error;
  }
  if (error instanceof ApiDecodeError) {
    return new LineRichMenuPublicationError(
      'contract',
      'line_rich_menu_publication_contract_mismatch',
      'Rich Menu 發布回應未通過安全驗證。'
    );
  }
  if (error instanceof ApiHttpError) {
    const category: LineRichMenuPublicationErrorCategory =
      error.status === 401 ? 'unauthenticated'
        : error.status === 403 ? 'forbidden'
          : error.status === 404 ? 'not_found'
            : error.status === 409 ? 'conflict'
              : error.status === 422 ? 'validation'
                : 'unavailable';
    return new LineRichMenuPublicationError(
      category,
      error.code,
      error.message,
      error.status,
      error.retryable
    );
  }
  if (error instanceof ApiNetworkError || error instanceof ApiTimeoutError) {
    return new LineRichMenuPublicationError(
      'unavailable',
      'line_rich_menu_publication_transport_unavailable',
      error.message,
      undefined,
      true
    );
  }
  return error instanceof Error
    ? error
    : new LineRichMenuPublicationError(
        'unavailable',
        'line_rich_menu_publication_unexpected_error',
        'Rich Menu 發布發生無法辨識的錯誤。'
      );
}
