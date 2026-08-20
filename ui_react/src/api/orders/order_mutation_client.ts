/**
 * File: order_mutation_client.ts
 * Description: Orders 安全變更 typed API client，支援服務日期確認與受控重開之 Preview/Apply 與標頭注入。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';
import { decodeMutationError } from './order_mutation_errors';
import {
  ServiceDateConfirmationQueryViewSchema,
  ServiceDateConfirmationPreviewViewSchema,
  ServiceDateConfirmationReceiptViewSchema,
  ServiceDatePreviewPayloadSchema,
  ServiceDateApplyPayloadSchema,
  OrderReopenPreviewViewSchema,
  OrderReopenReceiptViewSchema,
  OrderReopenApplyPayloadSchema,
  createOrderMutationEnvelopeSchema,
  type ServiceDateConfirmationQueryView,
  type ServiceDateConfirmationPreviewView,
  type ServiceDateConfirmationReceiptView,
  type ServiceDatePreviewPayload,
  type ServiceDateApplyPayload,
  type OrderReopenPreviewView,
  type OrderReopenReceiptView,
  type OrderReopenApplyPayload,
} from './order_mutation_schemas';

export interface OrderMutationRequestOptions {
  correlationId?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  headers?: Record<string, string>;
}

export interface OrderMutationApplyOptions extends OrderMutationRequestOptions {
  idempotencyKey: string;
}

export interface OrdersMutationClient {
  getServiceDates(
    caseNo: string,
    options?: OrderMutationRequestOptions
  ): Promise<ServiceDateConfirmationQueryView>;

  previewServiceDates(
    caseNo: string,
    payload: ServiceDatePreviewPayload,
    options?: OrderMutationRequestOptions
  ): Promise<ServiceDateConfirmationPreviewView>;

  applyServiceDates(
    caseNo: string,
    payload: ServiceDateApplyPayload,
    options: OrderMutationApplyOptions
  ): Promise<ServiceDateConfirmationReceiptView>;

  previewReopen(
    caseNo: string,
    options?: OrderMutationRequestOptions
  ): Promise<OrderReopenPreviewView>;

  applyReopen(
    caseNo: string,
    payload: OrderReopenApplyPayload,
    options: OrderMutationApplyOptions
  ): Promise<OrderReopenReceiptView>;
}

function resolveTransportOptions(
  options?: OrderMutationRequestOptions,
  extraHeaders?: Record<string, string>
): RequestOptions {
  const token = sessionClient.getToken();
  const headers: Record<string, string> = {
    ...options?.headers,
    ...extraHeaders,
  };

  const reqOptions: RequestOptions = {
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
    headers,
  };

  if (token) {
    reqOptions.token = token;
  }

  return reqOptions;
}

function decodeOrderMutationEnvelope<T extends z.ZodTypeAny>(
  dataSchema: T,
  raw: unknown
): z.output<T> {
  const envelope = decodePayload(
    createOrderMutationEnvelopeSchema(dataSchema),
    raw
  );

  if (!envelope.success) {
    throw new ApiHttpError(
      400,
      'BUSINESS_ERROR',
      envelope.error ?? envelope.message,
      false,
      raw
    );
  }

  if (envelope.data === null) {
    throw new ApiDecodeError('Orders 變更成功信封缺少 data 本體', [], raw);
  }

  return envelope.data;
}

function requireValidIdempotencyKey(key: unknown): string {
  if (typeof key !== 'string') {
    throw new Error('Idempotency-Key 必須為非空字串');
  }
  const trimmed = key.trim();
  if (trimmed.length < 1 || trimmed.length > 191) {
    throw new Error('Idempotency-Key 長度必須介於 1 至 191 字元');
  }
  return trimmed;
}

// ============================================================================
// 1. getServiceDates (Query)
// ============================================================================
export async function getServiceDates(
  caseNo: string,
  options?: OrderMutationRequestOptions
): Promise<ServiceDateConfirmationQueryView> {
  const encoded = encodeURIComponent(caseNo);
  const endpoint = `/api/v1/orders/${encoded}/service-dates`;
  const transportOptions = resolveTransportOptions(options);

  try {
    const raw = await transport.get(endpoint, transportOptions);
    return decodeOrderMutationEnvelope(
      ServiceDateConfirmationQueryViewSchema,
      raw
    );
  } catch (err) {
    throw decodeMutationError(err, { caseNo, endpoint });
  }
}

// ============================================================================
// 2. previewServiceDates (Preview)
// ============================================================================
export async function previewServiceDates(
  caseNo: string,
  payload: ServiceDatePreviewPayload,
  options?: OrderMutationRequestOptions
): Promise<ServiceDateConfirmationPreviewView> {
  const validatedPayload = ServiceDatePreviewPayloadSchema.parse(payload);
  const encoded = encodeURIComponent(caseNo);
  const endpoint = `/api/v1/orders/${encoded}/service-dates/preview`;

  const correlationId =
    options?.correlationId ?? `orders-date-preview-${caseNo}-${Date.now()}`;
  const transportOptions = resolveTransportOptions(options, {
    'X-Correlation-ID': correlationId,
  });

  try {
    const raw = await transport.post(
      endpoint,
      validatedPayload,
      transportOptions
    );
    return decodeOrderMutationEnvelope(
      ServiceDateConfirmationPreviewViewSchema,
      raw
    );
  } catch (err) {
    throw decodeMutationError(err, { caseNo, endpoint });
  }
}

// ============================================================================
// 3. applyServiceDates (Apply)
// ============================================================================
export async function applyServiceDates(
  caseNo: string,
  payload: ServiceDateApplyPayload,
  options: OrderMutationApplyOptions
): Promise<ServiceDateConfirmationReceiptView> {
  const validatedPayload = ServiceDateApplyPayloadSchema.parse(payload);
  const idempotencyKey = requireValidIdempotencyKey(options?.idempotencyKey);
  const encoded = encodeURIComponent(caseNo);
  const endpoint = `/api/v1/orders/${encoded}/service-dates/apply`;

  const correlationId =
    options?.correlationId ?? `orders-date-apply-${caseNo}-${Date.now()}`;
  const transportOptions = resolveTransportOptions(options, {
    'X-Correlation-ID': correlationId,
    'Idempotency-Key': idempotencyKey,
  });

  try {
    const raw = await transport.post(
      endpoint,
      validatedPayload,
      transportOptions
    );
    return decodeOrderMutationEnvelope(
      ServiceDateConfirmationReceiptViewSchema,
      raw
    );
  } catch (err) {
    throw decodeMutationError(err, { caseNo, endpoint });
  }
}

// ============================================================================
// 4. previewReopen (Preview)
// ============================================================================
export async function previewReopen(
  caseNo: string,
  options?: OrderMutationRequestOptions
): Promise<OrderReopenPreviewView> {
  const encoded = encodeURIComponent(caseNo);
  const endpoint = `/api/v1/orders/${encoded}/reopen/preview`;

  const correlationId =
    options?.correlationId ?? `orders-reopen-preview-${caseNo}-${Date.now()}`;
  const transportOptions = resolveTransportOptions(options, {
    'X-Correlation-ID': correlationId,
  });

  try {
    const raw = await transport.post(endpoint, undefined, transportOptions);
    return decodeOrderMutationEnvelope(OrderReopenPreviewViewSchema, raw);
  } catch (err) {
    throw decodeMutationError(err, { caseNo, endpoint });
  }
}

// ============================================================================
// 5. applyReopen (Apply)
// ============================================================================
export async function applyReopen(
  caseNo: string,
  payload: OrderReopenApplyPayload,
  options: OrderMutationApplyOptions
): Promise<OrderReopenReceiptView> {
  const validatedPayload = OrderReopenApplyPayloadSchema.parse(payload);
  const idempotencyKey = requireValidIdempotencyKey(options?.idempotencyKey);
  const encoded = encodeURIComponent(caseNo);
  const endpoint = `/api/v1/orders/${encoded}/reopen/apply`;

  const correlationId =
    options?.correlationId ?? `orders-reopen-apply-${caseNo}-${Date.now()}`;
  const transportOptions = resolveTransportOptions(options, {
    'X-Correlation-ID': correlationId,
    'Idempotency-Key': idempotencyKey,
  });

  try {
    const raw = await transport.post(
      endpoint,
      validatedPayload,
      transportOptions
    );
    return decodeOrderMutationEnvelope(OrderReopenReceiptViewSchema, raw);
  } catch (err) {
    throw decodeMutationError(err, { caseNo, endpoint });
  }
}

// ============================================================================
// Default Client Implementation & Factory / Singleton
// ============================================================================

export class DefaultOrdersMutationClient implements OrdersMutationClient {
  private readonly defaultOptions?: OrderMutationRequestOptions;

  constructor(defaultOptions?: OrderMutationRequestOptions) {
    this.defaultOptions = defaultOptions;
  }

  private mergeOptions(
    overrideOptions?: OrderMutationRequestOptions
  ): OrderMutationRequestOptions | undefined {
    if (!this.defaultOptions) return overrideOptions;
    if (!overrideOptions) return this.defaultOptions;
    return {
      ...this.defaultOptions,
      ...overrideOptions,
      headers: {
        ...this.defaultOptions.headers,
        ...overrideOptions.headers,
      },
    };
  }

  private mergeApplyOptions(
    options: OrderMutationApplyOptions
  ): OrderMutationApplyOptions {
    if (!this.defaultOptions) return options;
    return {
      ...this.defaultOptions,
      ...options,
      headers: {
        ...this.defaultOptions.headers,
        ...options.headers,
      },
    };
  }

  public getServiceDates(
    caseNo: string,
    options?: OrderMutationRequestOptions
  ): Promise<ServiceDateConfirmationQueryView> {
    return getServiceDates(caseNo, this.mergeOptions(options));
  }

  public previewServiceDates(
    caseNo: string,
    payload: ServiceDatePreviewPayload,
    options?: OrderMutationRequestOptions
  ): Promise<ServiceDateConfirmationPreviewView> {
    return previewServiceDates(caseNo, payload, this.mergeOptions(options));
  }

  public applyServiceDates(
    caseNo: string,
    payload: ServiceDateApplyPayload,
    options: OrderMutationApplyOptions
  ): Promise<ServiceDateConfirmationReceiptView> {
    return applyServiceDates(caseNo, payload, this.mergeApplyOptions(options));
  }

  public previewReopen(
    caseNo: string,
    options?: OrderMutationRequestOptions
  ): Promise<OrderReopenPreviewView> {
    return previewReopen(caseNo, this.mergeOptions(options));
  }

  public applyReopen(
    caseNo: string,
    payload: OrderReopenApplyPayload,
    options: OrderMutationApplyOptions
  ): Promise<OrderReopenReceiptView> {
    return applyReopen(caseNo, payload, this.mergeApplyOptions(options));
  }
}

export function createOrdersMutationClient(
  defaultOptions?: OrderMutationRequestOptions
): OrdersMutationClient {
  return new DefaultOrdersMutationClient(defaultOptions);
}

export const ordersMutationClient = new DefaultOrdersMutationClient();
