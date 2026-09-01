/** File: line_safe_review_link_errors.ts */

import { ApiAbortError, ApiError, ApiHttpError, ApiNetworkError, ApiTimeoutError, extractErrorMessage } from '../shared/typed_errors';

export type SafeReviewLinkClientErrorCode =
  | 'SAFE_REVIEW_LINK_UNAUTHENTICATED'
  | 'SAFE_REVIEW_LINK_FORBIDDEN'
  | 'SAFE_REVIEW_LINK_NOT_FOUND'
  | 'SAFE_REVIEW_LINK_CONFLICT'
  | 'SAFE_REVIEW_LINK_VALIDATION'
  | 'SAFE_REVIEW_LINK_UNAVAILABLE'
  | 'SAFE_REVIEW_LINK_CONTRACT'
  | 'SAFE_REVIEW_LINK_ABORTED'
  | 'SAFE_REVIEW_LINK_NETWORK';

export class SafeReviewLinkClientError extends ApiError {
  public readonly name = 'SafeReviewLinkClientError';
  public readonly code: SafeReviewLinkClientErrorCode;
  public readonly publicCode?: string;

  constructor(code: SafeReviewLinkClientErrorCode, message: string, options: { status?: number; publicCode?: string; originalError?: unknown } = {}) {
    super(message);
    this.code = code;
    this.status = options.status;
    this.publicCode = options.publicCode;
    this.originalError = options.originalError;
  }

  public readonly status?: number;
  public readonly originalError?: unknown;
}

export function mapSafeReviewLinkError(error: unknown): SafeReviewLinkClientError {
  if (error instanceof SafeReviewLinkClientError) return error;
  if (error instanceof ApiAbortError) return new SafeReviewLinkClientError('SAFE_REVIEW_LINK_ABORTED', error.message, { originalError: error });
  if (error instanceof ApiTimeoutError || error instanceof ApiNetworkError) return new SafeReviewLinkClientError('SAFE_REVIEW_LINK_NETWORK', error.message, { originalError: error });
  if (error instanceof ApiHttpError) {
    const publicCode = typeof error.code === 'string' ? error.code : undefined;
    if (error.status === 401) return new SafeReviewLinkClientError('SAFE_REVIEW_LINK_UNAUTHENTICATED', error.message, { status: error.status, publicCode, originalError: error });
    if (error.status === 403) return new SafeReviewLinkClientError('SAFE_REVIEW_LINK_FORBIDDEN', error.message, { status: error.status, publicCode, originalError: error });
    if (error.status === 404) return new SafeReviewLinkClientError('SAFE_REVIEW_LINK_NOT_FOUND', error.message, { status: error.status, publicCode, originalError: error });
    if (error.status === 409 || error.status === 410) return new SafeReviewLinkClientError('SAFE_REVIEW_LINK_CONFLICT', error.message, { status: error.status, publicCode, originalError: error });
    if (error.status >= 500) return new SafeReviewLinkClientError('SAFE_REVIEW_LINK_UNAVAILABLE', error.message, { status: error.status, publicCode, originalError: error });
    return new SafeReviewLinkClientError('SAFE_REVIEW_LINK_VALIDATION', error.message, { status: error.status, publicCode, originalError: error });
  }
  return new SafeReviewLinkClientError('SAFE_REVIEW_LINK_NETWORK', extractErrorMessage(error), { originalError: error });
}
