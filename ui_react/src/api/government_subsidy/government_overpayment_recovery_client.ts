/**
 * File: government_overpayment_recovery_client.ts
 * Description: Government Subsidy bounded Query／Preview／Apply client；不推算業務完成。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiError, ApiHttpError, ApiNetworkError, ApiTimeoutError, ApiAbortError } from '../shared/typed_errors';
import {
  GovernmentOverpaymentDispositionApplyRequestSchema,
  GovernmentOverpaymentDispositionPreviewRequestSchema,
  GovernmentOverpaymentPreviewResponseSchema,
  GovernmentOverpaymentQueryResponseSchema,
  GovernmentOverpaymentReceiptResponseSchema,
  type GovernmentOverpaymentDispositionApplyRequest,
  type GovernmentOverpaymentDispositionPreviewRequest,
  type GovernmentOverpaymentPreview,
  type GovernmentOverpaymentQuery,
  type GovernmentOverpaymentReceipt,
} from './government_overpayment_recovery_schemas';

export class GovernmentOverpaymentRecoveryError extends ApiError {
  public readonly name = 'GovernmentOverpaymentRecoveryError';
  public readonly code: string;
  public readonly retryable: boolean;
  public readonly status?: number;
  constructor(
    code: string,
    message: string,
    retryable = false,
    status?: number,
  ) {
    super(message);
    this.code = code;
    this.retryable = retryable;
    this.status = status;
  }
}

export interface GovernmentOverpaymentRecoveryOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface GovernmentOverpaymentRecoveryApplyOptions extends GovernmentOverpaymentRecoveryOptions {
  idempotencyKey: string;
  correlationId: string;
}

function requestOptions(options: GovernmentOverpaymentRecoveryOptions, correlationId: string, idempotencyKey?: string): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_UNAUTHENTICATED', '請先登入。', false, 401);
  const normalizedCorrelation = correlationId.trim();
  if (!normalizedCorrelation) throw new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_CORRELATION_INVALID', 'X-Correlation-ID 不得為空白。');
  const headers: Record<string, string> = { 'X-Correlation-ID': normalizedCorrelation };
  if (idempotencyKey !== undefined) {
    const normalizedKey = idempotencyKey.trim();
    if (!normalizedKey) throw new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_IDEMPOTENCY_INVALID', 'Idempotency-Key 不得為空白。');
    headers['Idempotency-Key'] = normalizedKey;
  }
  return { token, headers, signal: options.signal, timeoutMs: options.timeoutMs ?? 30_000, baseUrl: options.baseUrl };
}

function decode<T extends z.ZodTypeAny>(schema: T, raw: unknown, label: string): z.output<T> {
  try {
    return decodePayload(schema, raw);
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_SCHEMA_MISMATCH', `${label}回應結構不符合 strict 契約。`);
  }
}

function mapError(error: unknown): GovernmentOverpaymentRecoveryError {
  if (error instanceof GovernmentOverpaymentRecoveryError) return error;
  if (error instanceof ApiTimeoutError) return new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_TIMEOUT', error.message, true);
  if (error instanceof ApiAbortError) return new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_ABORTED', error.message);
  if (error instanceof ApiNetworkError) return new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_NETWORK', error.message, true);
  if (error instanceof ApiDecodeError) return new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_SCHEMA_MISMATCH', error.message);
  if (error instanceof ApiHttpError) return new GovernmentOverpaymentRecoveryError(error.code, error.message, error.retryable, error.status);
  return new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_UNKNOWN', error instanceof Error ? error.message : '政府溢撥處置失敗。');
}

function validPreviewRequest(request: GovernmentOverpaymentDispositionPreviewRequest): GovernmentOverpaymentDispositionPreviewRequest {
  const parsed = GovernmentOverpaymentDispositionPreviewRequestSchema.safeParse(request);
  if (!parsed.success) throw new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_INPUT_INVALID', '政府溢撥處置輸入不符合 strict 契約。');
  if (parsed.data.disposition === 'offset' && (parsed.data.targets.length === 0 || parsed.data.due_date != null)) {
    throw new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_OFFSET_INPUT_INVALID', '抵扣處置必須有標的且不得帶退款日期。');
  }
  if (parsed.data.disposition === 'return' && (parsed.data.targets.length !== 0 || !parsed.data.due_date)) {
    throw new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_RETURN_INPUT_INVALID', '退還處置只能帶退款日期，不得帶抵扣標的。');
  }
  return parsed.data;
}

function validApplyRequest(request: GovernmentOverpaymentDispositionApplyRequest): GovernmentOverpaymentDispositionApplyRequest {
  const parsed = GovernmentOverpaymentDispositionApplyRequestSchema.safeParse(request);
  if (!parsed.success) throw new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_INPUT_INVALID', '政府溢撥 Apply 輸入不符合 strict 契約。');
  return parsed.data;
}

function identity(value: string): string {
  const normalized = value.trim();
  if (!normalized) throw new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_IDENTITY_INVALID', '溢撥 identity 不得為空白。');
  return normalized;
}

export interface GovernmentOverpaymentRecoveryClient {
  query(overpaymentIdentity: string, options?: GovernmentOverpaymentRecoveryOptions): Promise<GovernmentOverpaymentQuery>;
  preview(request: GovernmentOverpaymentDispositionPreviewRequest, options?: GovernmentOverpaymentRecoveryOptions): Promise<GovernmentOverpaymentPreview>;
  apply(request: GovernmentOverpaymentDispositionApplyRequest, options: GovernmentOverpaymentRecoveryApplyOptions): Promise<GovernmentOverpaymentReceipt>;
}

class DefaultGovernmentOverpaymentRecoveryClient implements GovernmentOverpaymentRecoveryClient {
  async query(overpaymentIdentity: string, options: GovernmentOverpaymentRecoveryOptions = {}): Promise<GovernmentOverpaymentQuery> {
    const normalized = identity(overpaymentIdentity);
    try {
      const raw = await transport.get<unknown>(`/api/v1/government-subsidy/overpayments/${encodeURIComponent(normalized)}`, requestOptions(options, `government-overpayment-query-${crypto.randomUUID()}`));
      const envelope = decode(GovernmentOverpaymentQueryResponseSchema, raw, '政府溢撥 Query');
      if (envelope.data.overpayment_identity !== normalized) throw new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_IDENTITY_MISMATCH', 'Query identity 與請求不一致。');
      return envelope.data;
    } catch (error) { throw mapError(error); }
  }

  async preview(request: GovernmentOverpaymentDispositionPreviewRequest, options: GovernmentOverpaymentRecoveryOptions = {}): Promise<GovernmentOverpaymentPreview> {
    const valid = validPreviewRequest(request);
    try {
      const raw = await transport.post<unknown>('/api/v1/government-subsidy/overpayments/disposition/preview', valid, requestOptions(options, `government-overpayment-preview-${crypto.randomUUID()}`));
      const envelope = decode(GovernmentOverpaymentPreviewResponseSchema, raw, '政府溢撥 Preview');
      if (envelope.data.overpayment_identity !== valid.overpayment_identity || envelope.data.disposition_kind !== valid.disposition) {
        throw new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_PREVIEW_IDENTITY_MISMATCH', 'Preview identity 或處置分支不一致。');
      }
      return envelope.data;
    } catch (error) { throw mapError(error); }
  }

  async apply(request: GovernmentOverpaymentDispositionApplyRequest, options: GovernmentOverpaymentRecoveryApplyOptions): Promise<GovernmentOverpaymentReceipt> {
    const valid = validApplyRequest(request);
    try {
      const raw = await transport.post<unknown>('/api/v1/government-subsidy/overpayments/disposition/apply', valid, requestOptions(options, options.correlationId, options.idempotencyKey));
      const envelope = decode(GovernmentOverpaymentReceiptResponseSchema, raw, '政府溢撥 Apply');
      if (envelope.data.overpayment_identity !== valid.overpayment_identity || envelope.data.preview_fingerprint !== valid.preview_fingerprint) {
        throw new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_RECEIPT_IDENTITY_MISMATCH', 'Apply receipt identity 與命令不一致。');
      }
      return envelope.data;
    } catch (error) { throw mapError(error); }
  }
}

export const governmentOverpaymentRecoveryClient: GovernmentOverpaymentRecoveryClient = new DefaultGovernmentOverpaymentRecoveryClient();
