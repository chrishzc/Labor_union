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
  LineOrderGroupWorkspacePageSchema, LineOrderGroupWorkspaceRecordSchema,
  LineOrderGroupWorkspaceEventPageSchema, type LineOrderGroupWorkspacePage,
  type LineOrderGroupWorkspaceRecord, type LineOrderGroupWorkspaceEventPage,
} from './line_order_group_query_schemas';

export interface LineOrderGroupQueryOptions { signal?: AbortSignal; timeoutMs?: number; baseUrl?: string; }
export interface LineOrderGroupListQuery { status?: LineOrderGroupStatus; page?: number; pageSize?: number; }
export interface LineOrderGroupEventQuery { page?: number; pageSize?: number; }
export interface LineOrderGroupWorkspaceQuery extends LineOrderGroupListQuery { search?: string; }

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
  async workspaceList(query: LineOrderGroupWorkspaceQuery = {}, input?: LineOrderGroupQueryOptions): Promise<LineOrderGroupWorkspacePage> {
    try {
      if (query.status) LineOrderGroupStatusSchema.parse(query.status);
      if (query.search !== undefined && query.search.length > 50) throw new LineOrderGroupQueryError('LINE_ORDER_GROUP_VALIDATION', '搜尋內容過長。');
      assertPageBoundary(query.page, 'page');
      assertPageBoundary(query.pageSize, 'pageSize');
      const page = query.page ?? 1;
      const pageSize = query.pageSize ?? 25;
      const data = decode(LineOrderGroupWorkspacePageSchema, await transport.get('/api/v1/line/order-groups/workspace/numbered', {
        ...options(input), params: { search: query.search?.trim() || undefined, status: query.status, page, page_size: pageSize },
      }));
      assertWorkspacePage(data, page, pageSize);
      if (new Set(data.items.map(item => item.case_no)).size !== data.items.length) throw new LineOrderGroupQueryError('LINE_ORDER_GROUP_IDENTITY_MISMATCH', '案件重複。');
      return data;
    } catch (error) { throw mapLineOrderGroupQueryError(error); }
  },

  async workspaceDetail(caseNo: string, input?: LineOrderGroupQueryOptions): Promise<LineOrderGroupWorkspaceRecord> {
    try {
      const canonical = assertCaseNo(caseNo);
      const data = decode(LineOrderGroupWorkspaceRecordSchema, await transport.get(`/api/v1/line/order-groups/workspace/${encodeURIComponent(canonical)}`, options(input)));
      assertCaseIdentity(canonical, data.case_no);
      return data;
    } catch (error) { throw mapLineOrderGroupQueryError(error); }
  },

  async workspaceEvents(caseNo: string, query: LineOrderGroupEventQuery = {}, input?: LineOrderGroupQueryOptions): Promise<LineOrderGroupWorkspaceEventPage> {
    try {
      const canonical = assertCaseNo(caseNo);
      assertPageBoundary(query.page, 'page');
      assertPageBoundary(query.pageSize, 'pageSize');
      const page = query.page ?? 1;
      const pageSize = query.pageSize ?? 25;
      const data = decode(LineOrderGroupWorkspaceEventPageSchema, await transport.get(`/api/v1/line/order-groups/workspace/${encodeURIComponent(canonical)}/events/numbered`, {
        ...options(input), params: { page, page_size: pageSize },
      }));
      assertWorkspacePage(data, page, pageSize);
      data.items.forEach(event => assertCaseIdentity(canonical, event.case_no));
      if (new Set(data.items.map(event => event.event_key)).size !== data.items.length) throw new LineOrderGroupQueryError('LINE_ORDER_GROUP_IDENTITY_MISMATCH', '事件重複。');
      return data;
    } catch (error) { throw mapLineOrderGroupQueryError(error); }
  },
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

function assertWorkspacePage(data: { items: unknown[]; page: number; page_size: number; total: number; total_pages: number }, page: number, pageSize: number): void {
  if (data.page !== page || data.page_size !== pageSize || data.items.length > pageSize || data.items.length > data.total || data.total_pages !== Math.ceil(data.total / pageSize)) {
    throw new LineOrderGroupQueryError('LINE_ORDER_GROUP_PAGE_MISMATCH', '群組查詢分頁不一致。');
  }
}

export type LineOrderGroupWorkspaceClient = Pick<typeof lineOrderGroupQueryClient, 'workspaceList' | 'workspaceDetail' | 'workspaceEvents'>;
