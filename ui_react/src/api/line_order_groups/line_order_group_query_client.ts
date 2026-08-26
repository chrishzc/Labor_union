/**
 * File: line_order_group_query_client.ts
 * Description: 以 fresh Session 查詢 LINE 訂單群組 numbered 清單、明細與事件，驗證 identity 與分頁界線。
 */
import type { ZodType } from 'zod';
import { sessionClient } from '../auth/session_client';
import { ApiDecodeError } from '../shared/typed_errors';
import { transport } from '../shared/transport';
import { LineOrderGroupQueryError, mapLineOrderGroupQueryError } from './line_order_group_query_errors';
import {
  LineOrderGroupEventPageSchema, LineOrderGroupPageSchema, LineOrderGroupRecordSchema,
  LineOrderGroupStatusSchema, type LineOrderGroupEventPage, type LineOrderGroupPage,
  type LineOrderGroupRecord, type LineOrderGroupStatus,
} from './line_order_group_query_schemas';

export interface LineOrderGroupQueryOptions { signal?: AbortSignal; timeoutMs?: number; baseUrl?: string; }
export interface LineOrderGroupListQuery { status?: LineOrderGroupStatus; page?: number; pageSize?: number; }
export interface LineOrderGroupEventQuery { page?: number; pageSize?: number; }

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

function assertPageBoundary(value: number | undefined, field: 'page' | 'pageSize'): void {
  if (value !== undefined && (!Number.isInteger(value) || value < 1 || (field === 'pageSize' && value > 200))) {
    throw new LineOrderGroupQueryError('LINE_ORDER_GROUP_VALIDATION', `${field} 無效。`);
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
      assertPageBoundary(query.page, 'page');
      assertPageBoundary(query.pageSize, 'pageSize');
      const page = query.page ?? 1;
      const pageSize = query.pageSize ?? 25;
      const data = decode(LineOrderGroupPageSchema, await transport.get('/api/v1/line/order-groups/numbered', {
        ...options(input), params: { status: query.status, page, page_size: pageSize },
      }));
      if (
        data.page !== page || data.page_size !== pageSize || data.items.length > pageSize ||
        data.items.length > data.total || data.total_pages !== Math.ceil(data.total / pageSize)
      ) {
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

  async events(caseNo: string, query: LineOrderGroupEventQuery = {}, input?: LineOrderGroupQueryOptions): Promise<LineOrderGroupEventPage> {
    try {
      const canonical = assertCaseNo(caseNo);
      assertPageBoundary(query.page, 'page');
      assertPageBoundary(query.pageSize, 'pageSize');
      const page = query.page ?? 1;
      const pageSize = query.pageSize ?? 25;
      const data = decode(LineOrderGroupEventPageSchema, await transport.get(`/api/v1/line/order-groups/${encodeURIComponent(canonical)}/events/numbered`, {
        ...options(input), params: { page, page_size: pageSize },
      }));
      data.items.forEach((event) => assertCaseIdentity(canonical, event.case_no));
      if (
        data.page !== page || data.page_size !== pageSize || data.items.length > pageSize ||
        data.items.length > data.total || data.total_pages !== Math.ceil(data.total / pageSize)
      ) throw new LineOrderGroupQueryError('LINE_ORDER_GROUP_PAGE_MISMATCH', '訂單群組 events page aggregate 不一致。');
      return data;
    } catch (error) { throw mapLineOrderGroupQueryError(error); }
  },
};
