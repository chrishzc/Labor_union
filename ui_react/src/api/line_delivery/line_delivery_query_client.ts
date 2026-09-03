/**
 * File: line_delivery_query_client.ts
 * Description: 以 fresh Session 查詢 LINE Delivery canonical summary、bounded page 與 detail，拒絕 aggregate 漂移。
 */
import { sessionClient } from '../auth/session_client';
import { ApiDecodeError } from '../shared/typed_errors';
import { transport } from '../shared/transport';
import { LineDeliveryQueryError, mapLineDeliveryQueryError } from './line_delivery_query_errors';
import {
  LineDeliveryDetailResponseSchema, LineDeliveryPageResponseSchema,
  LineDeliveryStatusSchema, LineDeliverySummaryResponseSchema, LineDeliverySourceTypeSchema,
  type LineDeliveryDetail, type LineDeliveryPage, type LineDeliverySourceType,
  type LineDeliveryStatus, type LineDeliverySummary,
} from './line_delivery_query_schemas';

export interface LineDeliveryQueryOptions { signal?: AbortSignal; timeoutMs?: number; baseUrl?: string; }
export interface LineDeliveryListQuery {
  status?: LineDeliveryStatus;
  sourceType?: LineDeliverySourceType;
  scheduledFrom?: string;
  scheduledTo?: string;
  page?: number;
  pageSize?: number;
}

function options(input?: LineDeliveryQueryOptions) {
  const token = sessionClient.getToken();
  if (!token) throw new LineDeliveryQueryError('LINE_DELIVERY_UNAUTHENTICATED', '請先登入。', false, 401);
  return { token, signal: input?.signal, timeoutMs: input?.timeoutMs, baseUrl: input?.baseUrl };
}

function decode<T>(schema: { safeParse: (value: unknown) => { success: true; data: { success: boolean; message: string; data: T; error?: string | null } } | { success: false; error: { issues: Array<{ path: PropertyKey[]; message: string; code?: string }> } } }, raw: unknown): T {
  const parsed = schema.safeParse(raw);
  if (!parsed.success) throw new ApiDecodeError('LINE 發送任務回應結構異常。', parsed.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message, code: issue.code })), raw);
  if (!parsed.data.success) throw new LineDeliveryQueryError('LINE_DELIVERY_FAILURE', parsed.data.error ?? parsed.data.message);
  return parsed.data.data;
}

function validateList(query: LineDeliveryListQuery) {
  if (query.status) LineDeliveryStatusSchema.parse(query.status);
  if (query.sourceType) LineDeliverySourceTypeSchema.parse(query.sourceType);
  if (query.page !== undefined && (!Number.isInteger(query.page) || query.page < 1)) throw new LineDeliveryQueryError('LINE_DELIVERY_VALIDATION', 'page 無效。');
  if (query.pageSize !== undefined && (!Number.isInteger(query.pageSize) || query.pageSize < 1 || query.pageSize > 100)) throw new LineDeliveryQueryError('LINE_DELIVERY_VALIDATION', 'pageSize 無效。');
  for (const value of [query.scheduledFrom, query.scheduledTo]) if (value !== undefined && Number.isNaN(Date.parse(value))) throw new LineDeliveryQueryError('LINE_DELIVERY_VALIDATION', '排程時間篩選無效。');
}

function assertSummary(value: LineDeliverySummary): LineDeliverySummary {
  const statuses = value.pending + value.processing + value.sent + value.retryable_failed + value.failed + value.cancelled;
  if (value.total !== statuses || value.overdue > value.total || value.sent_today > value.sent) throw new LineDeliveryQueryError('LINE_DELIVERY_AGGREGATE_MISMATCH', 'LINE 發送任務 summary aggregate 不一致。');
  return value;
}

function assertItemIdentity<T extends { id: number; task_id: number }>(item: T): T {
  if (item.id !== item.task_id) throw new LineDeliveryQueryError('LINE_DELIVERY_IDENTITY_MISMATCH', 'LINE 發送任務 identity 不一致。');
  return item;
}

export const lineDeliveryQueryClient = {
  async summary(input?: LineDeliveryQueryOptions): Promise<LineDeliverySummary> {
    try { return assertSummary(decode(LineDeliverySummaryResponseSchema, await transport.get('/api/v1/line/tasks/summary', options(input)))); }
    catch (error) { throw mapLineDeliveryQueryError(error); }
  },
  async list(query: LineDeliveryListQuery = {}, input?: LineDeliveryQueryOptions): Promise<LineDeliveryPage> {
    try {
      validateList(query);
      const data = decode(LineDeliveryPageResponseSchema, await transport.get('/api/v1/line/tasks', {
        ...options(input), params: { status: query.status, source_type: query.sourceType, scheduled_from: query.scheduledFrom, scheduled_to: query.scheduledTo, page: query.page, page_size: query.pageSize },
      }));
      data.items.forEach(assertItemIdentity);
      if (data.items.length > data.page_size || data.items.length > data.total) throw new LineDeliveryQueryError('LINE_DELIVERY_PAGE_MISMATCH', 'LINE 發送任務 page aggregate 不一致。');
      return data;
    } catch (error) { throw mapLineDeliveryQueryError(error); }
  },
  async detail(taskId: number, input?: LineDeliveryQueryOptions): Promise<LineDeliveryDetail> {
    try {
      if (!Number.isInteger(taskId) || taskId < 1) throw new LineDeliveryQueryError('LINE_DELIVERY_VALIDATION', 'taskId 無效。');
      const data = decode(LineDeliveryDetailResponseSchema, await transport.get(`/api/v1/line/tasks/${taskId}`, options(input)));
      assertItemIdentity(data.task);
      if (data.task.task_id !== taskId) throw new LineDeliveryQueryError('LINE_DELIVERY_IDENTITY_MISMATCH', 'LINE 發送任務 detail 與 request 不一致。');
      return data;
    } catch (error) { throw mapLineDeliveryQueryError(error); }
  },
};
