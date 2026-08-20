/**
 * File: customer_service_errors.ts
 * Description: 將客服 API 的 HTTP 狀態與錯誤代碼轉為可判別的前端錯誤。
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

export type CustomerServiceErrorCategory =
  | 'validation'
  | 'unauthenticated'
  | 'forbidden'
  | 'not_found'
  | 'domain_blocked'
  | 'conflict'
  | 'idempotency_mismatch'
  | 'rate_limited'
  | 'unavailable'
  | 'internal'
  | 'business'
  | 'request';

export const CustomerServiceFieldErrorSchema = z
  .object({
    field: z.string(),
    code: z.string(),
    message: z.string(),
  })
  .strict();
export type CustomerServiceFieldError = z.infer<
  typeof CustomerServiceFieldErrorSchema
>;

export const CustomerServiceTypedErrorSchema = z
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
    field_errors: z.array(CustomerServiceFieldErrorSchema),
    domain_blockers: z.array(z.string()),
    retryable: z.boolean(),
    current_version: z.number().int().nullable(),
  })
  .strict();

const CustomerServiceTypedHttpErrorSchema = z
  .object({
    detail: z
      .object({
        error: CustomerServiceTypedErrorSchema,
      })
      .strict(),
  })
  .strict();

export class CustomerServiceClientError extends ApiError {
  public readonly name: string = 'CustomerServiceClientError';
  public readonly category: CustomerServiceErrorCategory;
  public readonly code: string;
  public readonly status?: number;
  public readonly retryable: boolean;
  public readonly correlationId?: string;
  public readonly fieldErrors: readonly CustomerServiceFieldError[];
  public readonly domainBlockers: readonly string[];
  public readonly currentVersion: number | null;

  constructor(
    category: CustomerServiceErrorCategory,
    code: string,
    message: string,
    status?: number,
    retryable = false,
    correlationId?: string,
    fieldErrors: readonly CustomerServiceFieldError[] = [],
    domainBlockers: readonly string[] = [],
    currentVersion: number | null = null
  ) {
    super(message);
    this.category = category;
    this.code = code;
    this.status = status;
    this.retryable = retryable;
    this.correlationId = correlationId;
    this.fieldErrors = fieldErrors;
    this.domainBlockers = domainBlockers;
    this.currentVersion = currentVersion;
  }
}

export class CustomerServiceRequestError extends CustomerServiceClientError {
  public override readonly name = 'CustomerServiceRequestError';

  constructor(message: string) {
    super('request', 'customer_service_request_invalid', message, 422, false);
  }
}

export class CustomerServiceUnauthenticatedError extends CustomerServiceClientError {
  public override readonly name = 'CustomerServiceUnauthenticatedError';

  constructor(message = '管理員會話不存在或已失效，請重新登入') {
    super(
      'unauthenticated',
      'customer_service_unauthenticated',
      message,
      401,
      false
    );
  }
}

export class CustomerServiceBusinessError extends CustomerServiceClientError {
  public override readonly name = 'CustomerServiceBusinessError';

  constructor(code: string, message: string) {
    super('business', code, message, 400, false);
  }
}

export function mapCustomerServiceError(error: unknown): Error {
  if (error instanceof CustomerServiceClientError) {
    return error;
  }
  if (
    error instanceof ApiDecodeError ||
    error instanceof ApiAbortError ||
    error instanceof ApiNetworkError ||
    error instanceof ApiTimeoutError
  ) {
    return error;
  }
  if (error instanceof ApiHttpError) {
    const typedResult = CustomerServiceTypedHttpErrorSchema.safeParse(error.raw);
    if (typedResult.success) {
      const typed = typedResult.data.detail.error;
      return new CustomerServiceClientError(
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
    if (error.status === 401) {
      return new CustomerServiceClientError(
        'unauthenticated',
        error.code,
        error.message,
        error.status,
        false
      );
    }
    if (error.status === 403) {
      return new CustomerServiceClientError(
        'forbidden',
        error.code,
        error.message,
        error.status,
        false
      );
    }
    if (error.status === 404) {
      return new CustomerServiceClientError(
        'not_found',
        error.code,
        error.message,
        error.status,
        false
      );
    }
    if (error.status === 409) {
      return new CustomerServiceClientError(
        'conflict',
        error.code,
        error.message,
        error.status,
        false
      );
    }
    if (error.status === 422) {
      return new CustomerServiceClientError(
        'validation',
        error.code,
        error.message,
        error.status,
        false
      );
    }
    if (error.status === 429) {
      return new CustomerServiceClientError(
        'rate_limited',
        error.code,
        error.message,
        error.status,
        error.retryable
      );
    }
    if (error.status === 503) {
      return new CustomerServiceClientError(
        'unavailable',
        error.code,
        error.message,
        error.status,
        error.retryable
      );
    }
    return error;
  }
  if (error instanceof Error) {
    return error;
  }
  return new CustomerServiceClientError(
    'business',
    'customer_service_unexpected_error',
    '客服服務發生無法辨識的錯誤'
  );
}
