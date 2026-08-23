/**
 * File: data_browser_query_client.ts
 * Description: 查詢單一 allowlisted masked Data Browser source，並合併完全相同的無signal in-flight GET。
 */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import {
  DataBrowserMaskedPageEnvelopeSchema,
  DataBrowserSourceIdSchema,
  type DataBrowserMaskedPage,
  type DataBrowserSourceId,
} from './data_browser_query_schemas';
import {
  DataBrowserQueryError,
  mapDataBrowserQueryError,
} from './data_browser_query_errors';

export interface DataBrowserQueryParams {
  sourceId: DataBrowserSourceId;
  limit?: number;
  after?: string;
  query?: string;
}

export type DataBrowserQueryOptions = Omit<RequestOptions, 'method' | 'body' | 'token' | 'params'>;

export interface DataBrowserQueryClient {
  querySource(
    params: DataBrowserQueryParams,
    options?: DataBrowserQueryOptions
  ): Promise<DataBrowserMaskedPage>;
}

const inFlightQueries = new Map<string, Promise<DataBrowserMaskedPage>>();

function optionsWithSession(options?: DataBrowserQueryOptions): RequestOptions {
  const headers = { ...(options?.headers ?? {}) };
  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() === 'authorization') delete headers[key];
  }
  const token = sessionClient.getToken();
  if (!token) {
    throw new DataBrowserQueryError('unauthenticated', '缺少有效的管理員 Session', false, 401);
  }
  return { ...options, headers, token };
}

function validateParams(params: DataBrowserQueryParams): void {
  const source = DataBrowserSourceIdSchema.safeParse(params.sourceId);
  if (!source.success) {
    throw new DataBrowserQueryError('invalid', '資料來源不在 allowlist', false, 422);
  }
  if (params.limit !== undefined && (!Number.isInteger(params.limit) || params.limit < 1 || params.limit > 100)) {
    throw new DataBrowserQueryError('invalid', 'limit 必須為 1 至 100 的整數', false, 422);
  }
  if (params.after !== undefined && (
    typeof params.after !== 'string' || !params.after.trim() || params.after.length > 191
  )) {
    throw new DataBrowserQueryError('invalid', 'cursor 格式無效', false, 422);
  }
  if (params.query !== undefined && (
    typeof params.query !== 'string' || params.query.trim().length > 100
  )) {
    throw new DataBrowserQueryError('invalid', '搜尋文字不得超過 100 字元', false, 422);
  }
}

function sortedEntries(
  values: Record<string, string | number | boolean | null | undefined>
): Array<[string, string | number | boolean | null | undefined]> {
  return Object.entries(values).sort(([left], [right]) => left.localeCompare(right));
}

function coalescingKey(endpoint: string, options: RequestOptions): string | null {
  if (options.signal !== undefined) return null;
  return JSON.stringify({
    endpoint,
    token: options.token ?? null,
    headers: sortedEntries(options.headers ?? {}),
    params: sortedEntries(options.params ?? {}),
    timeoutMs: options.timeoutMs ?? null,
    baseUrl: options.baseUrl ?? '',
  });
}

function executeCoalesced(
  endpoint: string,
  options: RequestOptions,
  execute: () => Promise<DataBrowserMaskedPage>
): Promise<DataBrowserMaskedPage> {
  const key = coalescingKey(endpoint, options);
  if (key === null) return execute();
  const existing = inFlightQueries.get(key);
  if (existing !== undefined) return existing;
  const promise = execute();
  inFlightQueries.set(key, promise);
  const clear = () => {
    if (inFlightQueries.get(key) === promise) inFlightQueries.delete(key);
  };
  void promise.then(clear, clear);
  return promise;
}

export async function queryDataBrowserSource(
  params: DataBrowserQueryParams,
  options?: DataBrowserQueryOptions
): Promise<DataBrowserMaskedPage> {
  try {
    validateParams(params);
    const endpoint = `/api/v1/admin/data-browser/sources/${encodeURIComponent(params.sourceId)}`;
    const requestOptions: RequestOptions = {
      ...optionsWithSession(options),
      params: {
        limit: params.limit ?? 25,
        after: params.after,
        query: params.query?.trim() || undefined,
      },
    };
    return await executeCoalesced(endpoint, requestOptions, async () => {
      const raw = await transport.get<unknown>(endpoint, requestOptions);
      const decoded = DataBrowserMaskedPageEnvelopeSchema.safeParse(raw);
      if (!decoded.success) {
        throw new ApiDecodeError(
          'Data Browser 回應結構不符 strict contract',
          decoded.error.issues.map((issue) => ({
            path: issue.path.join('.') || '(root)',
            message: issue.message,
            code: issue.code,
          })),
          raw
        );
      }
      if (!decoded.data.success) {
        throw new DataBrowserQueryError(
          'invalid',
          decoded.data.error || decoded.data.message || '資料來源查詢失敗',
          false
        );
      }
      return decoded.data.data;
    });
  } catch (error) {
    throw mapDataBrowserQueryError(error);
  }
}

export function createDataBrowserQueryClient(): DataBrowserQueryClient {
  return { querySource: queryDataBrowserSource };
}

export const dataBrowserQueryClient = createDataBrowserQueryClient();
