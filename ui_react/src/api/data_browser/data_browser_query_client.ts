/**
 * File: data_browser_query_client.ts
 * Description: 查詢單一 allowlisted masked Data Browser source。
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
  DataBrowserSourceIdSchema.parse(params.sourceId);
  if (params.limit !== undefined && (!Number.isInteger(params.limit) || params.limit < 1 || params.limit > 100)) {
    throw new DataBrowserQueryError('invalid', 'limit 必須為 1 至 100 的整數', false, 422);
  }
  if (params.after !== undefined && (!params.after.trim() || params.after.length > 191)) {
    throw new DataBrowserQueryError('invalid', 'cursor 格式無效', false, 422);
  }
  if (params.query !== undefined && params.query.trim().length > 100) {
    throw new DataBrowserQueryError('invalid', '搜尋文字不得超過 100 字元', false, 422);
  }
}

export async function queryDataBrowserSource(
  params: DataBrowserQueryParams,
  options?: DataBrowserQueryOptions
): Promise<DataBrowserMaskedPage> {
  validateParams(params);
  const endpoint = `/api/v1/admin/data-browser/sources/${encodeURIComponent(params.sourceId)}`;
  try {
    const raw = await transport.get<unknown>(endpoint, {
      ...optionsWithSession(options),
      params: {
        limit: params.limit ?? 25,
        after: params.after,
        query: params.query?.trim() || undefined,
      },
    });
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
  } catch (error) {
    throw mapDataBrowserQueryError(error);
  }
}

export function createDataBrowserQueryClient(): DataBrowserQueryClient {
  return { querySource: queryDataBrowserSource };
}

export const dataBrowserQueryClient = createDataBrowserQueryClient();
