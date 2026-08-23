/**
 * File: order_query_errors.ts
 * Description: 將 Orders 查詢 HTTP 錯誤安全轉成 bounded typed errors。
 */
import { z } from 'zod';
import {
  ApiAbortError,
  ApiDecodeError,
  ApiError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
  isApiError,
} from '../shared/typed_errors';

export {
  ApiAbortError,
  ApiDecodeError,
  ApiError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
  isApiError,
};

export abstract class OrderQueryError extends ApiError {
  public abstract readonly name: string;
}

export class OrderRetiredEndpointError extends OrderQueryError {
  public readonly name = 'OrderRetiredEndpointError';
  public readonly status = 410;
  public readonly endpoint: string;

  constructor(
    endpoint: string,
    message = '此訂單端點已退役並停止服務'
  ) {
    super(`${message}: ${endpoint}`);
    this.endpoint = endpoint;
  }
}

export class OrderNotModifiedError extends OrderQueryError {
  public readonly name = 'OrderNotModifiedError';
  public readonly status = 304;

  public readonly etag?: string;

  constructor(etag?: string) {
    super('資源未修改');
    this.etag = etag;
  }
}

export class OrderNotFoundError extends OrderQueryError {
  public readonly name = 'OrderNotFoundError';
  public readonly status = 404;

  public readonly caseNo: string;

  constructor(caseNo: string, message = '查無此訂單或案件資料') {
    super(`[案件編號: ${caseNo}] ${message}`);
    this.caseNo = caseNo;
  }
}

export class OrderValidationError extends OrderQueryError {
  public readonly name = 'OrderValidationError';
  public readonly status = 422;

  public readonly code: string;
  public readonly fieldErrors: ReadonlyArray<{ field: string; message: string }>;

  constructor(
    message = '訂單查詢請求參數驗證失敗',
    fieldErrors: ReadonlyArray<{ field: string; message: string }> = [],
    code = 'ORDER_VALIDATION_ERROR'
  ) {
    super(message);
    this.code = code;
    this.fieldErrors = fieldErrors;
  }
}

export class OrderConflictError extends OrderQueryError {
  public readonly name = 'OrderConflictError';
  public readonly status = 409;

  public readonly code: string;
  public readonly currentVersion: number | null;
  public readonly domainBlockers: readonly string[];

  constructor(
    message = '訂單版本衝突或領域聚合狀態受阻',
    currentVersion: number | null = null,
    domainBlockers: readonly string[] = [],
    code = 'ORDER_CONFLICT'
  ) {
    super(message);
    this.code = code;
    this.currentVersion = currentVersion;
    this.domainBlockers = domainBlockers;
  }
}

export class OrderServiceUnavailableError extends OrderQueryError {
  public readonly name = 'OrderServiceUnavailableError';
  public readonly status = 503;
  public readonly retryable = true;

  constructor(message = '訂單服務暫時無法回應，請稍後重試') {
    super(message);
  }
}

const TypedErrorEnvelopeSchema = z.strictObject({
  detail: z.strictObject({
    error: z.strictObject({
      category: z.string(),
      code: z.string(),
      message: z.string(),
      field_errors: z.array(
        z.strictObject({
          field: z.string(),
          code: z.string(),
          message: z.string(),
        })
      ),
      domain_blockers: z.array(z.string()),
      retryable: z.boolean(),
      correlation_id: z.string(),
      current_version: z.number().int().nullable(),
    }),
  }),
});

function typedErrorFacts(raw: unknown) {
  const result = TypedErrorEnvelopeSchema.safeParse(raw);
  return result.success ? result.data.detail.error : null;
}

export function isOrderRetiredEndpointError(error: unknown): error is OrderRetiredEndpointError {
  return error instanceof OrderRetiredEndpointError;
}

export function isOrderNotModifiedError(error: unknown): error is OrderNotModifiedError {
  return error instanceof OrderNotModifiedError;
}

export function isOrderNotFoundError(error: unknown): error is OrderNotFoundError {
  return error instanceof OrderNotFoundError;
}

export function isOrderConflictError(error: unknown): error is OrderConflictError {
  return error instanceof OrderConflictError;
}

export function isOrderValidationError(error: unknown): error is OrderValidationError {
  return error instanceof OrderValidationError;
}

export function mapHttpErrorToOrderError(
  error: ApiHttpError,
  context: { caseNo?: string; endpoint: string }
): OrderQueryError | ApiHttpError {
  const facts = typedErrorFacts(error.raw);
  if (error.status === 410) {
    return new OrderRetiredEndpointError(context.endpoint, error.message);
  }
  if (error.status === 304) {
    return new OrderNotModifiedError();
  }
  if (error.status === 404) {
    return new OrderNotFoundError(context.caseNo ?? 'unknown', error.message);
  }
  if (error.status === 422) {
    return new OrderValidationError(
      error.message,
      facts?.field_errors.map((item) => ({ field: item.field, message: item.message })) ?? [],
      facts?.code ?? error.code
    );
  }
  if (error.status === 409) {
    return new OrderConflictError(
      error.message,
      facts?.current_version ?? null,
      facts?.domain_blockers ?? [],
      facts?.code ?? error.code
    );
  }
  if (error.status === 503) {
    return new OrderServiceUnavailableError(error.message);
  }
  return error;
}
