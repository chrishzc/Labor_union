/**
 * File: customer_service_escalation_client.ts
 * Description: 以 fresh Session 與 caller command identity 呼叫 M4 escalation 正式 API。
 */

import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { CustomerServiceEscalationError, mapCustomerServiceEscalationError, type CustomerServiceEscalationOperation } from './customer_service_escalation_errors';
import {
  CustomerServiceEscalationClaimRequestSchema,
  CustomerServiceEscalationCreateRequestSchema,
  CustomerServiceEscalationHandlingRequestSchema,
  CustomerServiceEscalationReceiptResponseSchema,
  CustomerServiceEscalationResolveRequestSchema,
  CustomerServiceEscalationViewResponseSchema,
  type CustomerServiceEscalationClaimRequest,
  type CustomerServiceEscalationCreateRequest,
  type CustomerServiceEscalationHandlingRequest,
  type CustomerServiceEscalationReceipt,
  type CustomerServiceEscalationResolveRequest,
  type CustomerServiceEscalationView,
} from './customer_service_escalation_schemas';

export interface CustomerServiceEscalationOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
  headers?: Record<string, string>;
}

export interface CustomerServiceEscalationDetailOptions extends CustomerServiceEscalationOptions {
  correlationId: string;
}

function requiredText(value: string, field: string): string {
  const normalized = value.trim();
  if (!normalized || normalized.length > 191) throw new CustomerServiceEscalationError('CUSTOMER_SERVICE_ESCALATION_VALIDATION', `${field} 必須是 1 至 191 字元的非空文字。`);
  return normalized;
}

function requireId(value: number): number {
  if (!Number.isInteger(value) || value < 1) throw new CustomerServiceEscalationError('CUSTOMER_SERVICE_ESCALATION_VALIDATION', 'escalation_id 必須是正整數。');
  return value;
}

function options(source: CustomerServiceEscalationOptions, correlationId: string, idempotencyKey?: string): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new CustomerServiceEscalationError('CUSTOMER_SERVICE_ESCALATION_UNAUTHENTICATED', '缺少有效的管理員 Session。', { status: 401 });
  const headers: Record<string, string> = {};
  for (const [name, value] of Object.entries(source.headers ?? {})) {
    if (['authorization', 'x-correlation-id', 'idempotency-key', 'content-type'].includes(name.toLowerCase())) continue;
    headers[name] = value;
  }
  headers['X-Correlation-ID'] = requiredText(correlationId, 'X-Correlation-ID');
  if (idempotencyKey !== undefined) headers['Idempotency-Key'] = requiredText(idempotencyKey, 'Idempotency-Key');
  return { token, headers, signal: source.signal, timeoutMs: source.timeoutMs, baseUrl: source.baseUrl };
}

function validate<T>(schema: z.ZodType<T>, value: T): T {
  const parsed = schema.safeParse(value);
  if (!parsed.success) throw new CustomerServiceEscalationError('CUSTOMER_SERVICE_ESCALATION_VALIDATION', 'M4 escalation request 不符合封閉契約。', { originalError: parsed.error });
  return parsed.data;
}

function decode<T>(schema: z.ZodType<{ data: T }>, raw: unknown): T {
  const parsed = schema.safeParse(raw);
  if (!parsed.success) throw new CustomerServiceEscalationError('CUSTOMER_SERVICE_ESCALATION_CONTRACT', 'M4 escalation 回應不符合封閉契約。', { originalError: parsed.error });
  return parsed.data.data;
}

async function mutation<T>(
  operation: CustomerServiceEscalationOperation,
  expectedReceiptOperation: CustomerServiceEscalationReceipt['operation'],
  escalationId: number | null,
  path: string,
  schema: z.ZodType<T>,
  request: T,
  source: CustomerServiceEscalationOptions,
): Promise<CustomerServiceEscalationReceipt> {
  try {
    const body = validate(schema, request);
    const identity = body as { correlation_id: string; idempotency_key: string };
    const raw = await transport.post<unknown>(path, body, options(source, identity.correlation_id, identity.idempotency_key));
    const receipt = decode(CustomerServiceEscalationReceiptResponseSchema, raw);
    if (![expectedReceiptOperation, 'replay'].includes(receipt.operation)) throw new CustomerServiceEscalationError('CUSTOMER_SERVICE_ESCALATION_CONTRACT', 'M4 escalation receipt operation 與 request 不一致。');
    if (escalationId !== null && receipt.escalation_id !== escalationId) throw new CustomerServiceEscalationError('CUSTOMER_SERVICE_ESCALATION_CONTRACT', 'M4 escalation receipt identity 與 request 不一致。');
    if (receipt.correlation_id !== identity.correlation_id) throw new CustomerServiceEscalationError('CUSTOMER_SERVICE_ESCALATION_CONTRACT', 'M4 escalation receipt correlation 與 request 不一致。');
    return receipt;
  } catch (error) {
    throw mapCustomerServiceEscalationError(error, operation);
  }
}

export async function createCustomerServiceEscalation(request: CustomerServiceEscalationCreateRequest, source: CustomerServiceEscalationOptions = {}): Promise<CustomerServiceEscalationReceipt> {
  return mutation('create', 'create', null, '/api/v1/customer-service/escalations', CustomerServiceEscalationCreateRequestSchema, request, source);
}

export async function getCustomerServiceEscalationDetail(escalationId: number, source: CustomerServiceEscalationDetailOptions): Promise<CustomerServiceEscalationView> {
  try {
    const id = requireId(escalationId);
    const raw = await transport.get<unknown>(`/api/v1/customer-service/escalations/${id}`, options(source, source.correlationId));
    const detail = decode(CustomerServiceEscalationViewResponseSchema, raw);
    if (detail.escalation_id !== id) throw new CustomerServiceEscalationError('CUSTOMER_SERVICE_ESCALATION_CONTRACT', 'M4 escalation detail identity 與 request 不一致。');
    return detail;
  } catch (error) {
    throw mapCustomerServiceEscalationError(error, 'detail');
  }
}

export async function claimCustomerServiceEscalation(escalationId: number, request: CustomerServiceEscalationClaimRequest, source: CustomerServiceEscalationOptions = {}): Promise<CustomerServiceEscalationReceipt> {
  const id = requireId(escalationId);
  return mutation('claim', 'claim', id, `/api/v1/customer-service/escalations/${id}/claim`, CustomerServiceEscalationClaimRequestSchema, request, source);
}

export async function startCustomerServiceEscalationHandling(escalationId: number, request: CustomerServiceEscalationHandlingRequest, source: CustomerServiceEscalationOptions = {}): Promise<CustomerServiceEscalationReceipt> {
  const id = requireId(escalationId);
  return mutation('handling', 'handling_started', id, `/api/v1/customer-service/escalations/${id}/handling`, CustomerServiceEscalationHandlingRequestSchema, request, source);
}

export async function resolveCustomerServiceEscalation(escalationId: number, request: CustomerServiceEscalationResolveRequest, source: CustomerServiceEscalationOptions = {}): Promise<CustomerServiceEscalationReceipt> {
  const id = requireId(escalationId);
  return mutation('resolve', 'resolve', id, `/api/v1/customer-service/escalations/${id}/resolve`, CustomerServiceEscalationResolveRequestSchema, request, source);
}

export const customerServiceEscalationClient = {
  create: createCustomerServiceEscalation,
  getDetail: getCustomerServiceEscalationDetail,
  claim: claimCustomerServiceEscalation,
  startHandling: startCustomerServiceEscalationHandling,
  resolve: resolveCustomerServiceEscalation,
};
