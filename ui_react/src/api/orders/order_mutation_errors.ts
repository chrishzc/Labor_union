/**
 * File: order_mutation_errors.ts
 * Description: 解析 Orders 安全變更端點之 Typed Error 信封，並正規化 FastAPI 401/403/422 差距。
 */
import { z } from 'zod';
import {
  ApiError,
  ApiHttpError,
  ApiDecodeError,
  ApiNetworkError,
  ApiTimeoutError,
  ApiAbortError,
  isApiError,
} from '../shared/typed_errors';

export {
  ApiError,
  ApiHttpError,
  ApiDecodeError,
  ApiNetworkError,
  ApiTimeoutError,
  ApiAbortError,
  isApiError,
};

export const MutationFieldErrorSchema = z
  .object({
    field: z.string(),
    code: z.string(),
    message: z.string(),
  })
  .strict();

export type MutationFieldError = z.infer<typeof MutationFieldErrorSchema>;

export const OrderMutationTypedErrorPayloadSchema = z
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
    correlation_id: z.string(),
    field_errors: z.array(MutationFieldErrorSchema),
    domain_blockers: z.array(z.string()),
    retryable: z.boolean(),
    current_version: z.number().int().nullable(),
  })
  .strict();

export type OrderMutationTypedErrorPayload = z.infer<
  typeof OrderMutationTypedErrorPayloadSchema
>;

export interface OrderMutationErrorParams {
  status: number;
  category: string;
  code: string;
  message: string;
  correlationId?: string;
  retryable?: boolean;
  fieldErrors?: readonly MutationFieldError[];
  domainBlockers?: readonly string[];
  currentVersion?: number | null;
  isBackendGap?: boolean;
  rawPayload?: unknown;
}

export abstract class OrderMutationError extends ApiError {
  public abstract readonly name: string;
  public readonly status: number;
  public readonly category: string;
  public readonly code: string;
  public readonly correlationId?: string;
  public readonly retryable: boolean;
  public readonly fieldErrors: readonly MutationFieldError[];
  public readonly domainBlockers: readonly string[];
  public readonly currentVersion: number | null;
  public readonly isBackendGap: boolean;
  public readonly rawPayload?: unknown;

  constructor(params: OrderMutationErrorParams) {
    super(params.message);
    this.status = params.status;
    this.category = params.category;
    this.code = params.code;
    this.correlationId = params.correlationId;
    this.retryable = params.retryable ?? false;
    this.fieldErrors = params.fieldErrors ?? [];
    this.domainBlockers = params.domainBlockers ?? [];
    this.currentVersion = params.currentVersion ?? null;
    this.isBackendGap = params.isBackendGap ?? false;
    this.rawPayload = params.rawPayload;
  }
}

export class OrderMutationValidationError extends OrderMutationError {
  public readonly name = 'OrderMutationValidationError';
  constructor(params: Omit<OrderMutationErrorParams, 'status' | 'category'> & { status?: number }) {
    super({
      ...params,
      status: params.status ?? 422,
      category: 'validation',
    });
  }
}

export class OrderMutationForbiddenError extends OrderMutationError {
  public readonly name = 'OrderMutationForbiddenError';
  constructor(params: Omit<OrderMutationErrorParams, 'status' | 'category'> & { status?: number }) {
    super({
      ...params,
      status: params.status ?? 403,
      category: 'forbidden',
    });
  }
}

export class OrderMutationNotFoundError extends OrderMutationError {
  public readonly name = 'OrderMutationNotFoundError';
  constructor(params: Omit<OrderMutationErrorParams, 'status' | 'category'> & { status?: number }) {
    super({
      ...params,
      status: params.status ?? 404,
      category: 'not_found',
    });
  }
}

export class OrderMutationDomainBlockedError extends OrderMutationError {
  public readonly name = 'OrderMutationDomainBlockedError';
  constructor(params: Omit<OrderMutationErrorParams, 'status' | 'category'> & { status?: number }) {
    super({
      ...params,
      status: params.status ?? 409,
      category: 'domain_blocked',
    });
  }
}

export class OrderMutationConflictError extends OrderMutationError {
  public readonly name = 'OrderMutationConflictError';
  constructor(params: Omit<OrderMutationErrorParams, 'status' | 'category'> & { status?: number }) {
    super({
      ...params,
      status: params.status ?? 409,
      category: 'conflict',
    });
  }
}

export class OrderMutationIdempotencyMismatchError extends OrderMutationError {
  public readonly name = 'OrderMutationIdempotencyMismatchError';
  constructor(params: Omit<OrderMutationErrorParams, 'status' | 'category'> & { status?: number }) {
    super({
      ...params,
      status: params.status ?? 409,
      category: 'idempotency_mismatch',
    });
  }
}

export class OrderMutationUnavailableError extends OrderMutationError {
  public readonly name = 'OrderMutationUnavailableError';
  constructor(params: Omit<OrderMutationErrorParams, 'status' | 'category'> & { status?: number }) {
    super({
      ...params,
      status: params.status ?? 503,
      category: 'unavailable',
      retryable: params.retryable ?? true,
    });
  }
}

export class OrderMutationInternalError extends OrderMutationError {
  public readonly name = 'OrderMutationInternalError';
  constructor(params: Omit<OrderMutationErrorParams, 'status' | 'category'> & { status?: number }) {
    super({
      ...params,
      status: params.status ?? 500,
      category: 'internal',
    });
  }
}

export class OrderMutationBackendGapError extends OrderMutationError {
  public readonly name = 'OrderMutationBackendGapError';
  constructor(params: OrderMutationErrorParams) {
    super({
      ...params,
      isBackendGap: true,
    });
  }
}

function mapStatusToCategory(status: number): string {
  switch (status) {
    case 400:
    case 422:
      return 'validation';
    case 401:
    case 403:
      return 'forbidden';
    case 404:
      return 'not_found';
    case 409:
      return 'conflict';
    case 502:
    case 503:
    case 504:
      return 'unavailable';
    default:
      return 'internal';
  }
}

export function decodeMutationError(
  err: unknown,
  context?: { caseNo?: string; endpoint?: string }
): OrderMutationError | ApiError {
  if (err instanceof OrderMutationError) {
    return err;
  }

  if (err instanceof ApiHttpError) {
    const raw = err.raw;
    if (typeof raw === 'object' && raw !== null) {
      const record = raw as Record<string, unknown>;
      const detail = record.detail;
      if (typeof detail === 'object' && detail !== null) {
        const detailRecord = detail as Record<string, unknown>;
        const rawError = detailRecord.error;
        if (rawError !== undefined && rawError !== null) {
          const parseResult = OrderMutationTypedErrorPayloadSchema.safeParse(rawError);
          if (parseResult.success) {
            const payload = parseResult.data;
            const params: OrderMutationErrorParams = {
              status: err.status,
              category: payload.category,
              code: payload.code,
              message: payload.message,
              correlationId: payload.correlation_id,
              retryable: payload.retryable,
              fieldErrors: payload.field_errors,
              domainBlockers: payload.domain_blockers,
              currentVersion: payload.current_version,
              isBackendGap: false,
              rawPayload: raw,
            };

            switch (payload.category) {
              case 'validation':
                return new OrderMutationValidationError(params);
              case 'forbidden':
                return new OrderMutationForbiddenError(params);
              case 'not_found':
                return new OrderMutationNotFoundError(params);
              case 'domain_blocked':
                return new OrderMutationDomainBlockedError(params);
              case 'conflict':
                return new OrderMutationConflictError(params);
              case 'idempotency_mismatch':
                return new OrderMutationIdempotencyMismatchError(params);
              case 'unavailable':
                return new OrderMutationUnavailableError(params);
              case 'internal':
                return new OrderMutationInternalError(params);
            }
          }
        }
      }
    }

    // Backend Gap: FastAPI pre-route 401/403/422 or un-enveloped error
    const category = mapStatusToCategory(err.status);
    return new OrderMutationBackendGapError({
      status: err.status,
      category,
      code: err.code || 'BACKEND_GAP',
      message: err.message,
      retryable: err.retryable,
      isBackendGap: true,
      rawPayload: err.raw,
      correlationId: undefined,
      fieldErrors: [],
      domainBlockers: [],
      currentVersion: null,
    });
  }

  if (
    err instanceof ApiTimeoutError ||
    err instanceof ApiNetworkError ||
    err instanceof ApiAbortError ||
    err instanceof ApiDecodeError
  ) {
    return err;
  }

  const message = err instanceof Error ? err.message : '訂單安全變更操作發生未預期錯誤';
  return new OrderMutationInternalError({
    status: 500,
    code: 'UNEXPECTED_CLIENT_ERROR',
    message: context?.caseNo ? `[案件 ${context.caseNo}] ${message}` : message,
    retryable: false,
    isBackendGap: true,
    rawPayload: err,
  });
}
