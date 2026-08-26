/**
 * File: staff_directory_client.ts
 * Description: 以最新記憶體 Session 執行 Staff 摘要唯讀 GET，並防止 cursor 與 identity 漂移。
 */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import { StaffDirectoryResponseSchema, type StaffDirectoryPage } from './staff_directory_schemas';
import {
  StaffDirectoryUnauthenticatedError,
  StaffDirectoryValidationError,
  mapStaffDirectoryError,
} from './staff_directory_errors';

export interface StaffDirectoryQueryParams {
  pageSize?: number;
  afterId?: number;
  staffId?: number;
}

export interface StaffDirectoryQueryOptions {
  signal?: AbortSignal;
  headers?: Record<string, string>;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface StaffDirectoryClient {
  queryPage(params?: StaffDirectoryQueryParams, options?: StaffDirectoryQueryOptions): Promise<StaffDirectoryPage>;
  resetPagination(): void;
}

export async function loadAllStaffDirectoryPages(
  query: (params?: StaffDirectoryQueryParams, options?: StaffDirectoryQueryOptions) => Promise<StaffDirectoryPage>,
  params: Pick<StaffDirectoryQueryParams, 'pageSize'> = {},
  options?: StaffDirectoryQueryOptions,
): Promise<StaffDirectoryPage> {
  const items: StaffDirectoryPage['items'] = [];
  const seenCursors = new Set<number>();
  let afterId: number | undefined;

  while (true) {
    const page = await query({ ...params, ...(afterId === undefined ? {} : { afterId }) }, options);
    items.push(...page.items);
    if (page.next_cursor === null) return { items, next_cursor: null };
    if (page.items.length === 0 || seenCursors.has(page.next_cursor) || page.items[page.items.length - 1].id !== page.next_cursor) {
      throw new StaffDirectoryValidationError('服務人員清單分頁未向前推進，無法取得完整名冊。');
    }
    seenCursors.add(page.next_cursor);
    afterId = page.next_cursor;
  }
}

function validatePositiveInteger(value: number, field: string): void {
  if (!Number.isInteger(value) || value <= 0) {
    throw new StaffDirectoryValidationError(`${field} 必須是正整數。`);
  }
}

function validateParams(params: StaffDirectoryQueryParams): void {
  const pageSize = params.pageSize ?? 200;
  if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 200) {
    throw new StaffDirectoryValidationError('pageSize 必須是 1 至 200 之間的整數。');
  }
  if (params.afterId !== undefined) validatePositiveInteger(params.afterId, 'afterId');
  if (params.staffId !== undefined) validatePositiveInteger(params.staffId, 'staffId');
  if (params.afterId !== undefined && params.staffId !== undefined) {
    throw new StaffDirectoryValidationError('afterId 與 staffId 不得同時提供。');
  }
}

function buildRequestOptions(options?: StaffDirectoryQueryOptions): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new StaffDirectoryUnauthenticatedError();
  const headers = { ...(options?.headers ?? {}) };
  for (const name of Object.keys(headers)) {
    if (name.toLowerCase() === 'authorization') delete headers[name];
  }
  return {
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
    headers,
    token,
  };
}

function decodePage(raw: unknown): StaffDirectoryPage {
  const decoded = StaffDirectoryResponseSchema.safeParse(raw);
  if (!decoded.success) {
    throw new ApiDecodeError(
      '服務人員摘要回應結構異常。',
      decoded.error.issues.map((issue) => ({
        path: issue.path.join('.') || '(root)',
        message: issue.message,
        code: issue.code,
      })),
      raw
    );
  }
  if (!decoded.data.success) {
    throw new StaffDirectoryValidationError(decoded.data.error ?? decoded.data.message);
  }
  return decoded.data.data;
}

class DefaultStaffDirectoryClient implements StaffDirectoryClient {
  private readonly requestedCursors = new Set<number>();
  private readonly pendingCursors = new Set<number>();
  private readonly returnedCursors = new Set<number>();
  private readonly loadedIds = new Set<number>();

  public resetPagination(): void {
    this.requestedCursors.clear();
    this.pendingCursors.clear();
    this.returnedCursors.clear();
    this.loadedIds.clear();
  }

  public async queryPage(
    params: StaffDirectoryQueryParams = {},
    options?: StaffDirectoryQueryOptions
  ): Promise<StaffDirectoryPage> {
    validateParams(params);
    if (params.afterId === undefined && params.staffId === undefined) this.resetPagination();
    if (
      params.afterId !== undefined
      && (this.requestedCursors.has(params.afterId) || this.pendingCursors.has(params.afterId))
    ) {
      throw new StaffDirectoryValidationError(`cursor ${params.afterId} 已查詢過。`);
    }
    if (params.afterId !== undefined) this.pendingCursors.add(params.afterId);
    const query: Record<string, number> = { page_size: params.pageSize ?? 200 };
    if (params.afterId !== undefined) query.after_id = params.afterId;
    if (params.staffId !== undefined) query.staff_id = params.staffId;

    try {
      const raw = await transport.get<unknown>('/api/v1/staff/summaries', {
        ...buildRequestOptions(options),
        params: query,
      });
      const page = decodePage(raw);
      const pageIds = new Set<number>();
      for (const item of page.items) {
        if (pageIds.has(item.id) || this.loadedIds.has(item.id)) {
          throw new StaffDirectoryValidationError(`服務人員摘要包含重複 identity：${item.id}。`);
        }
        pageIds.add(item.id);
      }
      if (page.next_cursor !== null) {
        if (params.afterId !== undefined && page.next_cursor <= params.afterId) {
          throw new StaffDirectoryValidationError('next_cursor 必須向前推進。');
        }
        if (this.returnedCursors.has(page.next_cursor)) {
          throw new StaffDirectoryValidationError(`next_cursor ${page.next_cursor} 已出現過。`);
        }
      }
      if (page.next_cursor !== null) this.returnedCursors.add(page.next_cursor);
      for (const id of pageIds) this.loadedIds.add(id);
      if (params.afterId !== undefined) {
        this.pendingCursors.delete(params.afterId);
        this.requestedCursors.add(params.afterId);
      }
      return page;
    } catch (error) {
      if (params.afterId !== undefined) this.pendingCursors.delete(params.afterId);
      throw mapStaffDirectoryError(error);
    }
  }
}

export function createStaffDirectoryClient(): StaffDirectoryClient {
  return new DefaultStaffDirectoryClient();
}

export const staffDirectoryClient: StaffDirectoryClient = createStaffDirectoryClient();
