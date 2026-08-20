/**
 * File: customer_service_client.ts
 * Description: 以即時記憶體 Session 呼叫客服查詢與結案 Preview／Apply 白名單端點。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import {
  CustomerServiceBusinessError,
  CustomerServiceRequestError,
  CustomerServiceUnauthenticatedError,
  mapCustomerServiceError,
} from './customer_service_errors';
import {
  CustomerServiceDetailResponseSchema,
  CustomerServiceListParamsSchema,
  CustomerServicePageResponseSchema,
  CustomerServiceResolveApplyRequestSchema,
  CustomerServiceResolvePreviewRequestSchema,
  CustomerServiceResolvePreviewResponseSchema,
  CustomerServiceSummaryResponseSchema,
  type CustomerServiceDetail,
  type CustomerServiceListParams,
  type CustomerServicePage,
  type CustomerServiceResolveApplyRequest,
  type CustomerServiceResolvePreview,
  type CustomerServiceResolvePreviewRequest,
  type CustomerServiceSummary,
} from './customer_service_schemas';

export interface CustomerServiceRequestOptions {
  signal?: AbortSignal;
  headers?: Record<string, string>;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface CustomerServiceMutationOptions
  extends CustomerServiceRequestOptions {
  correlationId: string;
}

export interface CustomerServiceApplyOptions
  extends CustomerServiceMutationOptions {
  idempotencyKey: string;
}

export interface CustomerServiceClient {
  getSummary(
    options?: CustomerServiceRequestOptions
  ): Promise<CustomerServiceSummary>;
  listTickets(
    params?: CustomerServiceListParams,
    options?: CustomerServiceRequestOptions
  ): Promise<CustomerServicePage>;
  getTicketDetail(
    ticketId: number,
    options?: CustomerServiceRequestOptions
  ): Promise<CustomerServiceDetail>;
  previewResolve(
    ticketId: number,
    payload: CustomerServiceResolvePreviewRequest,
    options: CustomerServiceMutationOptions
  ): Promise<CustomerServiceResolvePreview>;
  applyResolve(
    ticketId: number,
    payload: CustomerServiceResolveApplyRequest,
    options: CustomerServiceApplyOptions
  ): Promise<CustomerServiceDetail>;
}

function validateTicketId(ticketId: number): number {
  if (!Number.isInteger(ticketId)) {
    throw new CustomerServiceRequestError('ticket_id 必須為整數');
  }
  return ticketId;
}

function validateRequiredHeader(name: string, value: string): string {
  if (value.trim().length < 1 || value.length > 191) {
    throw new CustomerServiceRequestError(
      `${name} 必須為 1 至 191 字元的非空字串`
    );
  }
  return value;
}

function parseRequest<TData>(schema: z.ZodType<TData>, value: unknown): TData {
  const result = schema.safeParse(value);
  if (!result.success) {
    throw new CustomerServiceRequestError(
      result.error.issues.map((issue) => issue.message).join('; ')
    );
  }
  return result.data;
}

function currentRequestOptions(
  options?: CustomerServiceRequestOptions,
  protectedHeaders?: Record<string, string>
): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) {
    throw new CustomerServiceUnauthenticatedError();
  }

  const headers: Record<string, string> = { ...options?.headers };
  for (const name of Object.keys(headers)) {
    const normalized = name.toLowerCase();
    if (
      normalized === 'authorization' ||
      normalized === 'x-correlation-id' ||
      normalized === 'idempotency-key'
    ) {
      delete headers[name];
    }
  }

  return {
    signal: options?.signal,
    headers: { ...headers, ...protectedHeaders },
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
    token,
  };
}

interface SuccessfulEnvelope<TData> {
  success: boolean;
  message: string;
  data: TData;
  error: string | null;
}

function decodeSuccessfulEnvelope<TData>(
  schema: z.ZodType<SuccessfulEnvelope<TData>>,
  raw: unknown
): TData {
  const envelope = decodePayload(schema, raw);
  if (!envelope.success) {
    throw new CustomerServiceBusinessError(
      'customer_service_business_error',
      envelope.error ?? envelope.message
    );
  }
  return envelope.data;
}

async function callCustomerService<T>(operation: () => Promise<T>): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    throw mapCustomerServiceError(error);
  }
}

export async function getCustomerServiceSummary(
  options?: CustomerServiceRequestOptions
): Promise<CustomerServiceSummary> {
  return callCustomerService(async () => {
    const raw = await transport.get(
      '/api/v1/customer-service/tickets/summary',
      currentRequestOptions(options)
    );
    return decodeSuccessfulEnvelope(CustomerServiceSummaryResponseSchema, raw);
  });
}

export async function listCustomerServiceTickets(
  params?: CustomerServiceListParams,
  options?: CustomerServiceRequestOptions
): Promise<CustomerServicePage> {
  return callCustomerService(async () => {
    const parsed = CustomerServiceListParamsSchema.safeParse(params ?? {});
    if (!parsed.success) {
      throw new CustomerServiceRequestError(
        parsed.error.issues.map((issue) => issue.message).join('; ')
      );
    }
    const raw = await transport.get('/api/v1/customer-service/tickets', {
      ...currentRequestOptions(options),
      params: parsed.data,
    });
    return decodeSuccessfulEnvelope(CustomerServicePageResponseSchema, raw);
  });
}

export async function getCustomerServiceTicketDetail(
  ticketId: number,
  options?: CustomerServiceRequestOptions
): Promise<CustomerServiceDetail> {
  return callCustomerService(async () => {
    const validTicketId = validateTicketId(ticketId);
    const raw = await transport.get(
      `/api/v1/customer-service/tickets/${encodeURIComponent(String(validTicketId))}`,
      currentRequestOptions(options)
    );
    return decodeSuccessfulEnvelope(CustomerServiceDetailResponseSchema, raw);
  });
}

export async function previewCustomerServiceResolve(
  ticketId: number,
  payload: CustomerServiceResolvePreviewRequest,
  options: CustomerServiceMutationOptions
): Promise<CustomerServiceResolvePreview> {
  return callCustomerService(async () => {
    const validTicketId = validateTicketId(ticketId);
    const validPayload = parseRequest(
      CustomerServiceResolvePreviewRequestSchema,
      payload
    );
    const correlationId = validateRequiredHeader(
      'X-Correlation-ID',
      options.correlationId
    );
    const raw = await transport.post(
      `/api/v1/customer-service/tickets/${encodeURIComponent(String(validTicketId))}/update/preview`,
      validPayload,
      currentRequestOptions(options, {
        'X-Correlation-ID': correlationId,
      })
    );
    return decodeSuccessfulEnvelope(
      CustomerServiceResolvePreviewResponseSchema,
      raw
    );
  });
}

export async function applyCustomerServiceResolve(
  ticketId: number,
  payload: CustomerServiceResolveApplyRequest,
  options: CustomerServiceApplyOptions
): Promise<CustomerServiceDetail> {
  return callCustomerService(async () => {
    const validTicketId = validateTicketId(ticketId);
    const validPayload = parseRequest(
      CustomerServiceResolveApplyRequestSchema,
      payload
    );
    const correlationId = validateRequiredHeader(
      'X-Correlation-ID',
      options.correlationId
    );
    const idempotencyKey = validateRequiredHeader(
      'Idempotency-Key',
      options.idempotencyKey
    );
    const raw = await transport.post(
      `/api/v1/customer-service/tickets/${encodeURIComponent(String(validTicketId))}/update/apply`,
      validPayload,
      currentRequestOptions(options, {
        'X-Correlation-ID': correlationId,
        'Idempotency-Key': idempotencyKey,
      })
    );
    return decodeSuccessfulEnvelope(CustomerServiceDetailResponseSchema, raw);
  });
}

class DefaultCustomerServiceClient implements CustomerServiceClient {
  public getSummary(
    options?: CustomerServiceRequestOptions
  ): Promise<CustomerServiceSummary> {
    return getCustomerServiceSummary(options);
  }

  public listTickets(
    params?: CustomerServiceListParams,
    options?: CustomerServiceRequestOptions
  ): Promise<CustomerServicePage> {
    return listCustomerServiceTickets(params, options);
  }

  public getTicketDetail(
    ticketId: number,
    options?: CustomerServiceRequestOptions
  ): Promise<CustomerServiceDetail> {
    return getCustomerServiceTicketDetail(ticketId, options);
  }

  public previewResolve(
    ticketId: number,
    payload: CustomerServiceResolvePreviewRequest,
    options: CustomerServiceMutationOptions
  ): Promise<CustomerServiceResolvePreview> {
    return previewCustomerServiceResolve(ticketId, payload, options);
  }

  public applyResolve(
    ticketId: number,
    payload: CustomerServiceResolveApplyRequest,
    options: CustomerServiceApplyOptions
  ): Promise<CustomerServiceDetail> {
    return applyCustomerServiceResolve(ticketId, payload, options);
  }
}

export function createCustomerServiceClient(): CustomerServiceClient {
  return new DefaultCustomerServiceClient();
}

export const customerServiceClient: CustomerServiceClient =
  createCustomerServiceClient();
