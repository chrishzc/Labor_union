/**
 * File: two_step_auth_errors.ts
 * Description: 將登入邊界錯誤轉為不攜帶原始機密 payload 的安全錯誤。
 */
import {
  ApiDecodeError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
} from '../shared/typed_errors';

export type AuthFlowErrorCode =
  | 'invalid_credentials_or_factor'
  | 'mfa_enrollment_required'
  | 'login_rate_limited'
  | 'challenge_expired'
  | 'admin_auth_unavailable'
  | 'validation_error'
  | 'schema_mismatch'
  | 'timeout'
  | 'network'
  | 'unknown';

export class AuthFlowError extends Error {
  public readonly name = 'AuthFlowError';
  public readonly code: AuthFlowErrorCode;
  public readonly retryable: boolean;

  constructor(code: AuthFlowErrorCode, retryable: boolean) {
    super(code);
    this.code = code;
    this.retryable = retryable;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export function sanitizeAuthError(error: unknown): AuthFlowError {
  if (error instanceof ApiHttpError) {
    const knownCodes: AuthFlowErrorCode[] = [
      'invalid_credentials_or_factor',
      'mfa_enrollment_required',
      'login_rate_limited',
      'challenge_expired',
      'admin_auth_unavailable',
    ];
    const code = knownCodes.find((candidate) => candidate === error.code)
      ?? (error.status === 422 ? 'validation_error' : 'unknown');
    return new AuthFlowError(code, error.retryable);
  }
  if (error instanceof ApiDecodeError) return new AuthFlowError('schema_mismatch', false);
  if (error instanceof ApiTimeoutError) return new AuthFlowError('timeout', true);
  if (error instanceof ApiNetworkError) return new AuthFlowError('network', true);
  return new AuthFlowError('unknown', false);
}
