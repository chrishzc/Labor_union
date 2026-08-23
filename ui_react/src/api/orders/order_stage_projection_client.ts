/**
 * File: order_stage_projection_client.ts
 * Description: 以相對路徑取得 Orders typed 七階段 projection，拒絕未驗證 payload。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';
import {
  OrderOperationalTimelinePageSchema,
  type OrderOperationalTimelinePage,
} from './order_stage_projection_schemas';

export interface OrderStageProjectionQueryOptions {
  signal?: AbortSignal;
  token?: string | null;
  headers?: Record<string, string>;
  timeoutMs?: number;
  ifNoneMatch?: string;
  baseUrl?: string;
}

export interface OrderStageProjectionQueryParams {
  page_size?: number;
  after_case_no?: string;
}

export interface OrderStageProjectionClient {
  getOperationalTimelines(
    params?: OrderStageProjectionQueryParams,
    options?: OrderStageProjectionQueryOptions,
  ): Promise<OrderOperationalTimelinePage>;
}

const ParamsSchema = z.strictObject({
  page_size: z.number().int().min(1).max(200).optional(),
  after_case_no: z.string().min(1).max(50).optional(),
});

function requestOptions(options?: OrderStageProjectionQueryOptions): RequestOptions {
  const headers = { ...(options?.headers ?? {}) };
  if (options?.ifNoneMatch) headers['If-None-Match'] = options.ifNoneMatch;
  return {
    signal: options?.signal,
    token: options?.token !== undefined ? options.token : sessionClient.getToken(),
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
    headers,
  };
}

function decodeStageEnvelope(raw: unknown): OrderOperationalTimelinePage {
  const envelope = decodePayload(
    z.strictObject({
      success: z.boolean(),
      message: z.string(),
      data: OrderOperationalTimelinePageSchema,
      error: z.string().nullable(),
    }),
    raw,
  );
  if (!envelope.success) {
    throw new ApiHttpError(400, 'ORDERS_STAGE_PROJECTION_BUSINESS_ERROR', envelope.error ?? envelope.message, false, raw);
  }
  return envelope.data;
}

export async function getOrderOperationalTimelines(
  params: OrderStageProjectionQueryParams = {},
  options?: OrderStageProjectionQueryOptions,
): Promise<OrderOperationalTimelinePage> {
  const parsed = ParamsSchema.parse(params);
  const query: NonNullable<RequestOptions['params']> = {};
  if (parsed.page_size !== undefined) query.page_size = parsed.page_size;
  if (parsed.after_case_no) query.after_case_no = parsed.after_case_no.trim();
  const raw = await transport.get('/api/orders/operational-timelines', { ...requestOptions(options), params: query });
  return decodeStageEnvelope(raw);
}

class DefaultOrderStageProjectionClient implements OrderStageProjectionClient {
  private readonly defaults?: OrderStageProjectionQueryOptions;

  constructor(defaults?: OrderStageProjectionQueryOptions) {
    this.defaults = defaults;
  }

  getOperationalTimelines(params?: OrderStageProjectionQueryParams, options?: OrderStageProjectionQueryOptions) {
    return getOrderOperationalTimelines(params, {
      ...this.defaults,
      ...options,
      headers: { ...(this.defaults?.headers ?? {}), ...(options?.headers ?? {}) },
    });
  }
}

export function createOrderStageProjectionClient(defaults?: OrderStageProjectionQueryOptions): OrderStageProjectionClient {
  return new DefaultOrderStageProjectionClient(defaults);
}

export const orderStageProjectionClient: OrderStageProjectionClient = createOrderStageProjectionClient();
