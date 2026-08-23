/**
 * File: order_card_projection_client.ts
 * Description: 案件開啟 card/drawer 時才取得 typed composite projection。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';
import { OrdersCardProjectionSchema, type OrdersCardProjection } from './order_card_projection_schemas';

export interface OrderCardProjectionQueryOptions {
  signal?: AbortSignal;
  token?: string | null;
  headers?: Record<string, string>;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface OrderCardProjectionClient {
  getCardProjection(caseNo: string, options?: OrderCardProjectionQueryOptions): Promise<OrdersCardProjection>;
}

function validCaseNo(caseNo: string): string {
  const value = caseNo.trim();
  if (!value) throw new Error('案件編號不得為空字串');
  if (value.length > 50) throw new Error('案件編號超過長度限制');
  return value;
}

function requestOptions(options?: OrderCardProjectionQueryOptions): RequestOptions {
  return {
    signal: options?.signal,
    token: options?.token !== undefined ? options.token : sessionClient.getToken(),
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
    headers: { ...(options?.headers ?? {}) },
  };
}

export async function getOrderCardProjection(
  caseNo: string,
  options?: OrderCardProjectionQueryOptions,
): Promise<OrdersCardProjection> {
  const value = validCaseNo(caseNo);
  const raw = await transport.get(`/api/v1/orders/${encodeURIComponent(value)}/card-projection`, requestOptions(options));
  const envelope = decodePayload(z.strictObject({
    success: z.boolean(),
    message: z.string(),
    data: OrdersCardProjectionSchema,
    error: z.string().nullable(),
  }), raw);
  if (!envelope.success) {
    throw new ApiHttpError(400, 'ORDERS_CARD_PROJECTION_BUSINESS_ERROR', envelope.error ?? envelope.message, false, raw);
  }
  if (envelope.data.case_no !== value) {
    throw new ApiHttpError(409, 'ORDERS_CARD_PROJECTION_IDENTITY_MISMATCH', '案件卡片回應識別不一致。', false, raw);
  }
  return envelope.data;
}

class DefaultOrderCardProjectionClient implements OrderCardProjectionClient {
  private readonly defaults?: OrderCardProjectionQueryOptions;

  constructor(defaults?: OrderCardProjectionQueryOptions) {
    this.defaults = defaults;
  }

  getCardProjection(caseNo: string, options?: OrderCardProjectionQueryOptions) {
    return getOrderCardProjection(caseNo, {
      ...this.defaults,
      ...options,
      headers: { ...(this.defaults?.headers ?? {}), ...(options?.headers ?? {}) },
    });
  }
}

export function createOrderCardProjectionClient(defaults?: OrderCardProjectionQueryOptions): OrderCardProjectionClient {
  return new DefaultOrderCardProjectionClient(defaults);
}

export const orderCardProjectionClient: OrderCardProjectionClient = createOrderCardProjectionClient();
