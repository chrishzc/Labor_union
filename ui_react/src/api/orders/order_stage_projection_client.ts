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
  lifecycle_scope?: 'all' | 'unfinished';
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
  lifecycle_scope: z.enum(['all', 'unfinished']).optional(),
});

export class OrderStageProjectionContinuationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'OrderStageProjectionContinuationError';
  }
}

export async function loadAllOrderOperationalTimelines(
  query: (params: OrderStageProjectionQueryParams, options?: OrderStageProjectionQueryOptions) => Promise<OrderOperationalTimelinePage>,
  params: OrderStageProjectionQueryParams = {},
  options?: OrderStageProjectionQueryOptions,
): Promise<OrderOperationalTimelinePage> {
  const parsed = ParamsSchema.parse(params);
  const itemsByCaseNo = new Map<string, OrderOperationalTimelinePage['items'][number]>();
  const seenCursors = new Set<string>();
  let afterCaseNo = parsed.after_case_no?.trim();
  let lastCursor: string | undefined = afterCaseNo;
  let lastPage: OrderOperationalTimelinePage | null = null;

  while (true) {
    const page = await query(
      { ...parsed, ...(afterCaseNo ? { after_case_no: afterCaseNo } : {}) },
      options,
    );
    lastPage = page;
    for (const item of page.items) itemsByCaseNo.set(item.case_no, item);
    const nextCursor = page.next_cursor;
    if (nextCursor === null) break;
    if (page.items.length === 0 || seenCursors.has(nextCursor) || (lastCursor !== undefined && nextCursor <= lastCursor)) {
      throw new OrderStageProjectionContinuationError('Orders 階段 continuation cursor 未前進，無法取得完整分類。');
    }
    const lastItem = page.items[page.items.length - 1];
    if (lastItem.case_no !== nextCursor) {
      throw new OrderStageProjectionContinuationError('Orders 階段 continuation cursor 與頁尾案件不一致。');
    }
    seenCursors.add(nextCursor);
    lastCursor = nextCursor;
    afterCaseNo = nextCursor;
  }

  if (!lastPage) throw new OrderStageProjectionContinuationError('Orders 階段未取得任何頁面。');
  const items = [...itemsByCaseNo.values()].sort((left, right) => left.case_no.localeCompare(right.case_no));
  const stageCounts: OrderOperationalTimelinePage['stage_counts'] = {
    intake_terms: 0,
    matching_willingness: 0,
    client_review: 0,
    contract_deposit: 0,
    date_confirmation: 0,
    active_service: 0,
    settlement_payout: 0,
  };
  for (const item of items) {
    if (item.current_stage_code !== null) stageCounts[item.current_stage_code] += 1;
  }
  return { items, stage_counts: stageCounts, next_cursor: null, etag: lastPage.etag };
}

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
  if (parsed.lifecycle_scope) query.lifecycle_scope = parsed.lifecycle_scope;
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
