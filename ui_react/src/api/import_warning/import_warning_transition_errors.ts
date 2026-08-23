/**
 * File: import_warning_transition_errors.ts
 * Description: 將匯入警示 transition 的認證、409、契約、網路與 outcome unknown 錯誤型別化。
 */

import { z } from 'zod';
import {
  ApiAbortError,
  ApiDecodeError,
  ApiError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
  extractErrorMessage,
} from '../shared/typed_errors';

export type ImportWarningTransitionErrorCode =
  | 'IMPORT_WARNING_UNAUTHENTICATED'
  | 'IMPORT_WARNING_FORBIDDEN'
  | 'IMPORT_WARNING_NOT_FOUND'
  | 'IMPORT_WARNING_VALIDATION'
  | 'IMPORT_WARNING_STALE'
  | 'IMPORT_WARNING_IDEMPOTENCY_MISMATCH'
  | 'IMPORT_WARNING_UNAVAILABLE'
  | 'IMPORT_WARNING_OUTCOME_UNKNOWN'
  | 'IMPORT_WARNING_CONTRACT'
  | 'IMPORT_WARNING_NETWORK'
  | 'IMPORT_WARNING_TIMEOUT'
  | 'IMPORT_WARNING_ABORTED';

export type ImportWarningTransitionOperation = 'preview' | 'apply' | 'receipt';

export class ImportWarningTransitionError extends ApiError {
  public readonly name = 'ImportWarningTransitionError';
  public readonly code: ImportWarningTransitionErrorCode;
  public readonly status?: number;
  public readonly retryable: boolean;
  public readonly outcomeUnknown: boolean;
  public readonly publicCode?: string;
  public readonly correlationId?: string;
  public readonly currentVersion: number | null;
  public readonly originalError?: unknown;

  constructor(
    code: ImportWarningTransitionErrorCode,
    message: string,
    options: {
      status?: number;
      retryable?: boolean;
      outcomeUnknown?: boolean;
      publicCode?: string;
      correlationId?: string;
      currentVersion?: number | null;
      originalError?: unknown;
    } = {},
  ) {
    super(message);
    this.code = code;
    this.status = options.status;
    this.retryable = options.retryable ?? false;
    this.outcomeUnknown = options.outcomeUnknown ?? false;
    this.publicCode = options.publicCode;
    this.correlationId = options.correlationId;
    this.currentVersion = options.currentVersion ?? null;
    this.originalError = options.originalError;
  }
}

const TypedFieldErrorSchema = z.strictObject({
  field: z.string(),
  code: z.string(),
  message: z.string(),
});

const TypedErrorPayloadSchema = z.strictObject({
  category: z.enum([
    'validation', 'forbidden', 'not_found', 'domain_blocked', 'conflict',
    'idempotency_mismatch', 'unavailable', 'internal',
  ]),
  code: z.string().min(1),
  message: z.string().min(1),
  field_errors: z.array(TypedFieldErrorSchema),
  domain_blockers: z.array(z.string()),
  retryable: z.boolean(),
  correlation_id: z.string().min(1),
  current_version: z.number().int().nullable(),
});

const TypedErrorResponseSchema = z.strictObject({
  detail: z.strictObject({ error: TypedErrorPayloadSchema }),
});

type TypedErrorPayload = z.infer<typeof TypedErrorPayloadSchema>;

function typedPayload(raw: unknown): TypedErrorPayload | null {
  const parsed = TypedErrorResponseSchema.safeParse(raw);
  return parsed.success ? parsed.data.detail.error : null;
}

function optionsFromHttp(error: ApiHttpError): { status: number; retryable: boolean; publicCode: string; correlationId?: string; currentVersion: number | null; originalError: ApiHttpError } {
  const payload = typedPayload(error.raw);
  return {
    status: error.status,
    retryable: payload?.retryable ?? error.retryable,
    publicCode: payload?.code ?? error.code,
    correlationId: payload?.correlation_id,
    currentVersion: payload?.current_version ?? null,
    originalError: error,
  };
}

export function mapImportWarningTransitionError(
  error: unknown,
  operation: ImportWarningTransitionOperation,
): ImportWarningTransitionError {
  if (error instanceof ImportWarningTransitionError) return error;
  if (error instanceof ApiAbortError) {
    return new ImportWarningTransitionError('IMPORT_WARNING_ABORTED', error.message, { originalError: error });
  }
  if (error instanceof ApiTimeoutError) {
    return new ImportWarningTransitionError(
      operation === 'apply' ? 'IMPORT_WARNING_OUTCOME_UNKNOWN' : 'IMPORT_WARNING_TIMEOUT',
      error.message,
      { retryable: true, outcomeUnknown: operation === 'apply', originalError: error },
    );
  }
  if (error instanceof ApiNetworkError) {
    return new ImportWarningTransitionError(
      operation === 'apply' ? 'IMPORT_WARNING_OUTCOME_UNKNOWN' : 'IMPORT_WARNING_NETWORK',
      error.message,
      { retryable: true, outcomeUnknown: operation === 'apply', originalError: error },
    );
  }
  if (error instanceof ApiDecodeError) {
    return new ImportWarningTransitionError('IMPORT_WARNING_CONTRACT', error.message, { originalError: error });
  }
  if (error instanceof ApiHttpError) {
    const options = optionsFromHttp(error);
    const payload = typedPayload(error.raw);
    const lowerCode = `${payload?.code ?? error.code}`.toLowerCase();
    if (operation === 'apply' && [502, 503, 504].includes(error.status)) {
      return new ImportWarningTransitionError('IMPORT_WARNING_OUTCOME_UNKNOWN', error.message, { ...options, outcomeUnknown: true, retryable: true });
    }
    if (error.status === 409 && (payload?.category === 'idempotency_mismatch' || lowerCode.includes('idempotency'))) {
      return new ImportWarningTransitionError('IMPORT_WARNING_IDEMPOTENCY_MISMATCH', error.message, options);
    }
    if (error.status === 409 && (payload?.category === 'conflict' || lowerCode.includes('version') || lowerCode.includes('stale'))) {
      return new ImportWarningTransitionError('IMPORT_WARNING_STALE', error.message, options);
    }
    if (error.status === 401) return new ImportWarningTransitionError('IMPORT_WARNING_UNAUTHENTICATED', error.message, options);
    if (error.status === 403) return new ImportWarningTransitionError('IMPORT_WARNING_FORBIDDEN', error.message, options);
    if (error.status === 404) return new ImportWarningTransitionError('IMPORT_WARNING_NOT_FOUND', error.message, options);
    if ([502, 503, 504].includes(error.status)) return new ImportWarningTransitionError('IMPORT_WARNING_UNAVAILABLE', error.message, { ...options, retryable: true });
    return new ImportWarningTransitionError('IMPORT_WARNING_VALIDATION', error.message, options);
  }
  return new ImportWarningTransitionError(
    operation === 'apply' ? 'IMPORT_WARNING_OUTCOME_UNKNOWN' : 'IMPORT_WARNING_NETWORK',
    extractErrorMessage(error),
    { retryable: true, outcomeUnknown: operation === 'apply', originalError: error },
  );
}
