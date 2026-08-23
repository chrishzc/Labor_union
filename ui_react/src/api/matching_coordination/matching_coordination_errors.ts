/**
 * File: matching_coordination_errors.ts
 * Description: 將 M3 typed HTTP error 轉為可判別且 fail-closed 的前端錯誤。
 */
import { z } from 'zod';
import {
  ApiAbortError,
  ApiDecodeError,
  ApiError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
} from '../shared/typed_errors';

export {
  ApiAbortError,
  ApiDecodeError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
};

const MatchingFieldErrorSchema = z
  .object({ field: z.string(), code: z.string(), message: z.string() })
  .strict();

const MatchingTypedErrorSchema = z
  .object({
    category: z.enum([
      'validation',
      'forbidden',
      'not_found',
      'domain_blocked',
      'conflict',
      'idempotency_mismatch',
      'unavailable',
      'internal',
    ]),
    code: z.string(),
    message: z.string(),
    field_errors: z.array(MatchingFieldErrorSchema),
    domain_blockers: z.array(z.string()),
    retryable: z.boolean(),
    correlation_id: z.string(),
    current_version: z.number().int().nullable(),
  })
  .strict();

const MatchingTypedHttpErrorSchema = z
  .object({ detail: z.object({ error: MatchingTypedErrorSchema }).strict() })
  .strict();

export type MatchingCoordinationErrorCategory =
  | z.infer<typeof MatchingTypedErrorSchema>['category']
  | 'unauthenticated'
  | 'request'
  | 'business';

export class MatchingCoordinationClientError extends ApiError {
  public readonly name: string = 'MatchingCoordinationClientError';

  constructor(
    public readonly category: MatchingCoordinationErrorCategory,
    public readonly code: string,
    message: string,
    public readonly status?: number,
    public readonly retryable = false,
    public readonly correlationId?: string,
    public readonly fieldErrors: readonly z.infer<
      typeof MatchingFieldErrorSchema
    >[] = [],
    public readonly domainBlockers: readonly string[] = [],
    public readonly currentVersion: number | null = null
  ) {
    super(message);
  }
}

export class MatchingCoordinationRequestError extends MatchingCoordinationClientError {
  public override readonly name = 'MatchingCoordinationRequestError';

  constructor(message: string) {
    super('request', 'matching_coordination_request_invalid', message, 422);
  }
}

export class MatchingCoordinationUnauthenticatedError extends MatchingCoordinationClientError {
  public override readonly name = 'MatchingCoordinationUnauthenticatedError';

  constructor() {
    super(
      'unauthenticated',
      'matching_coordination_unauthenticated',
      '管理員會話不存在或已失效，請重新登入',
      401
    );
  }
}

export class MatchingCoordinationBusinessError extends MatchingCoordinationClientError {
  public override readonly name = 'MatchingCoordinationBusinessError';

  constructor(code: string, message: string) {
    super('business', code, message, 400);
  }
}

export function mapMatchingCoordinationError(error: unknown): Error {
  if (error instanceof MatchingCoordinationClientError) return error;
  if (
    error instanceof ApiDecodeError ||
    error instanceof ApiAbortError ||
    error instanceof ApiNetworkError ||
    error instanceof ApiTimeoutError
  ) {
    return error;
  }
  if (error instanceof ApiHttpError) {
    const parsed = MatchingTypedHttpErrorSchema.safeParse(error.raw);
    if (parsed.success) {
      const typed = parsed.data.detail.error;
      return new MatchingCoordinationClientError(
        typed.category,
        typed.code,
        typed.message,
        error.status,
        typed.retryable,
        typed.correlation_id,
        typed.field_errors,
        typed.domain_blockers,
        typed.current_version
      );
    }
    const category =
      error.status === 401
        ? 'unauthenticated'
        : error.status === 403
          ? 'forbidden'
          : error.status === 404
            ? 'not_found'
            : error.status === 409
              ? 'conflict'
              : error.status === 422
                ? 'validation'
                : error.status === 503
                  ? 'unavailable'
                  : 'internal';
    return new MatchingCoordinationClientError(
      category,
      error.code,
      error.message,
      error.status,
      error.retryable
    );
  }
  return error instanceof Error
    ? error
    : new MatchingCoordinationClientError(
        'internal',
        'matching_coordination_unexpected_error',
        '媒合協調服務發生無法辨識的錯誤'
      );
}
