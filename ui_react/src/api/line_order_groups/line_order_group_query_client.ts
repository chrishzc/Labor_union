/**
 * File: line_order_group_query_client.ts
 * Description: 以 fresh Session 查詢 LINE 訂單群組清單、明細與事件，驗證 request identity 與頁面界線。
 */
import type { ZodType } from 'zod';
import { sessionClient } from '../auth/session_client';
import { ApiDecodeError } from '../shared/typed_errors';
import { transport } from '../shared/transport';
import { LineOrderGroupQueryError, mapLineOrderGroupQueryError } from './line_order_group_query_errors';
import {
  LineOrderGroupEventsSchema, LineOrderGroupPageSchema, LineOrderGroupRecordSchema,
  LineOrderGroupStatusSchema, type LineOrderGroupEvent, type LineOrderGroupPage,
  type LineOrderGroupRecord, type LineOrderGroupStatus,
} from './line_order_group_query_schemas';

export interface LineOrderGroupQueryOptions { signal?: AbortSignal; timeoutMs?: number; baseUrl?: string; }
export interface LineOrderGroupListQuery { status?: LineOrderGroupStatus; limit?: number; }

function options(input?: LineOrderGroupQueryOptions) {
  const token = sessionClient.getToken();
  if (!token) throw new LineOrderGroupQueryError('LINE_ORDER_GROUP_UNAUTHENTICATED', '請先登入。', false, 401);
  return { token, signal: input?.signal, timeoutMs: input?.timeoutMs, baseUrl: input?.baseUrl };
}

function decode<T>(schema: ZodType<T>, raw: unknown): T {
  const parsed = schema.safeParse(raw);
  if (!parsed.success) {
    throw new ApiDecodeError(
      'LINE 訂單群組回應結構異常。',
      parsed.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message, code: issue.code })),
      raw,
    );
  }
  return parsed.data;
}

function assertLimit(limit: number | undefined): void {
  if (limit !== undefined && (!Number.isInteger(limit) || limit < 1 || limit > 200)) {
    throw new LineOrderGroupQueryError('LINE_ORDER_GROUP_VALIDATION', 'limit 無效。');
  }
}

function assertCaseNo(caseNo: string): string {
  const canonical = caseNo.trim();
  if (!canonical || canonical !== caseNo) throw new LineOrderGroupQueryError('LINE_ORDER_GROUP_VALIDATION', 'caseNo 無效。');
  return canonical;
}

function assertCaseIdentity(caseNo: string, actual: string): void {
  if (caseNo !== actual) throw new LineOrderGroupQueryError('LINE_ORDER_GROUP_IDENTITY_MISMATCH', '訂單群組與 request identity 不一致。');
}

export const lineOrderGroupQueryClient = {
  async list(query: LineOrderGroupListQuery = {}, input?: LineOrderGroupQueryOptions): Promise<LineOrderGroupPage> {
    try {
      if (query.status) LineOrderGroupStatusSchema.parse(query.status);
      assertLimit(query.limit);
      const data = decode(LineOrderGroupPageSchema, await transport.get('/api/v1/line/order-groups', {
        ...options(input), params: { status: query.status, limit: query.limit },
      }));
      if (data.items.length > data.total || (query.limit !== undefined && data.items.length > query.limit)) {
        throw new LineOrderGroupQueryError('LINE_ORDER_GROUP_PAGE_MISMATCH', '訂單群組 page aggregate 不一致。');
      }
      return data;
    } catch (error) { throw mapLineOrderGroupQueryError(error); }
  },

  async detail(caseNo: string, input?: LineOrderGroupQueryOptions): Promise<LineOrderGroupRecord> {
    try {
      const canonical = assertCaseNo(caseNo);
      const data = decode(LineOrderGroupRecordSchema, await transport.get(`/api/v1/line/order-groups/${encodeURIComponent(canonical)}`, options(input)));
      assertCaseIdentity(canonical, data.case_no);
      return data;
    } catch (error) { throw mapLineOrderGroupQueryError(error); }
  },

  async events(caseNo: string, limit?: number, input?: LineOrderGroupQueryOptions): Promise<LineOrderGroupEvent[]> {
    try {
      const canonical = assertCaseNo(caseNo);
      assertLimit(limit);
      const data = decode(LineOrderGroupEventsSchema, await transport.get(`/api/v1/line/order-groups/${encodeURIComponent(canonical)}/events`, {
        ...options(input), params: { limit },
      }));
      data.forEach((event) => assertCaseIdentity(canonical, event.case_no));
      if (limit !== undefined && data.length > limit) throw new LineOrderGroupQueryError('LINE_ORDER_GROUP_PAGE_MISMATCH', '訂單群組 events 超出 request limit。');
      return data;
    } catch (error) { throw mapLineOrderGroupQueryError(error); }
  },
};
