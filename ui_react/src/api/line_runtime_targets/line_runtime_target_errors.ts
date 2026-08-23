/**
 * File: line_runtime_target_errors.ts
 * Description: 將 LINE runtime target 認證、衝突、outcome unknown 與契約錯誤型別化。
 */

import { z } from 'zod';
import { ApiAbortError, ApiError, ApiHttpError, ApiNetworkError, ApiTimeoutError, extractErrorMessage } from '../shared/typed_errors';

export type LineRuntimeTargetErrorCode =
  | 'LINE_RUNTIME_TARGET_UNAUTHENTICATED'
  | 'LINE_RUNTIME_TARGET_FORBIDDEN'
  | 'LINE_RUNTIME_TARGET_NOT_FOUND'
  | 'LINE_RUNTIME_TARGET_VALIDATION'
  | 'LINE_RUNTIME_TARGET_CONFLICT'
  | 'LINE_RUNTIME_TARGET_IDEMPOTENCY_MISMATCH'
  | 'LINE_RUNTIME_TARGET_UNAVAILABLE'
  | 'LINE_RUNTIME_TARGET_OUTCOME_UNKNOWN'
  | 'LINE_RUNTIME_TARGET_CONTRACT'
  | 'LINE_RUNTIME_TARGET_ABORTED'
  | 'LINE_RUNTIME_TARGET_NETWORK';

export type LineRuntimeTargetOperation = 'list' | 'candidates' | 'add' | 'reset' | 'toggle';

const RuntimeTargetTypedErrorSchema = z.strictObject({
  detail: z.strictObject({
    error: z.strictObject({
      category: z.enum(['validation', 'not_found', 'conflict', 'idempotency_mismatch', 'unavailable', 'internal']),
      code: z.string().min(1),
      message: z.string().min(1),
      correlation_id: z.string().min(1),
      field_errors: z.array(z.never()),
      domain_blockers: z.array(z.never()),
      retryable: z.boolean(),
    }),
  }),
});

export class LineRuntimeTargetError extends ApiError {
  public readonly name = 'LineRuntimeTargetError';
  public readonly code: LineRuntimeTargetErrorCode;
  public readonly options: { status?: number; retryable?: boolean; outcomeUnknown?: boolean; publicCode?: string; originalError?: unknown };

  constructor(
    code: LineRuntimeTargetErrorCode,
    message: string,
    options: { status?: number; retryable?: boolean; outcomeUnknown?: boolean; publicCode?: string; originalError?: unknown } = {},
  ) {
    super(message);
    this.code = code;
    this.options = options;
  }

  get status(): number | undefined { return this.options.status; }
  get retryable(): boolean { return this.options.retryable ?? false; }
  get outcomeUnknown(): boolean { return this.options.outcomeUnknown ?? false; }
  get publicCode(): string | undefined { return this.options.publicCode; }
}

function isMutation(operation: LineRuntimeTargetOperation): boolean {
  return !['list', 'candidates'].includes(operation);
}

export function mapLineRuntimeTargetError(error: unknown, operation: LineRuntimeTargetOperation): LineRuntimeTargetError {
  if (error instanceof LineRuntimeTargetError) return error;
  if (error instanceof ApiAbortError) return new LineRuntimeTargetError('LINE_RUNTIME_TARGET_ABORTED', error.message, { originalError: error });
  if (error instanceof ApiTimeoutError || error instanceof ApiNetworkError) {
    const unknown = isMutation(operation);
    return new LineRuntimeTargetError(unknown ? 'LINE_RUNTIME_TARGET_OUTCOME_UNKNOWN' : 'LINE_RUNTIME_TARGET_NETWORK', error.message, { retryable: true, outcomeUnknown: unknown, originalError: error });
  }
  if (error instanceof ApiHttpError) {
    const parsed = RuntimeTargetTypedErrorSchema.safeParse(error.raw);
    const serverError = parsed.success ? parsed.data.detail.error : null;
    const publicCode = serverError?.code ?? error.code;
    const options = { status: error.status, retryable: serverError?.retryable ?? error.retryable, publicCode, originalError: error };
    if (isMutation(operation) && [502, 503, 504].includes(error.status)) return new LineRuntimeTargetError('LINE_RUNTIME_TARGET_OUTCOME_UNKNOWN', error.message, { ...options, retryable: true, outcomeUnknown: true });
    if (error.status === 401) return new LineRuntimeTargetError('LINE_RUNTIME_TARGET_UNAUTHENTICATED', error.message, options);
    if (error.status === 403) return new LineRuntimeTargetError('LINE_RUNTIME_TARGET_FORBIDDEN', error.message, options);
    if (error.status === 404) return new LineRuntimeTargetError('LINE_RUNTIME_TARGET_NOT_FOUND', error.message, options);
    if (error.status === 409 && publicCode.includes('idempotency')) return new LineRuntimeTargetError('LINE_RUNTIME_TARGET_IDEMPOTENCY_MISMATCH', error.message, options);
    if (error.status === 409) return new LineRuntimeTargetError('LINE_RUNTIME_TARGET_CONFLICT', error.message, options);
    if ([502, 503, 504].includes(error.status)) return new LineRuntimeTargetError('LINE_RUNTIME_TARGET_UNAVAILABLE', error.message, { ...options, retryable: true });
    return new LineRuntimeTargetError('LINE_RUNTIME_TARGET_VALIDATION', error.message, options);
  }
  return new LineRuntimeTargetError(
    isMutation(operation) ? 'LINE_RUNTIME_TARGET_OUTCOME_UNKNOWN' : 'LINE_RUNTIME_TARGET_NETWORK',
    extractErrorMessage(error),
    { retryable: true, outcomeUnknown: isMutation(operation), originalError: error },
  );
}
