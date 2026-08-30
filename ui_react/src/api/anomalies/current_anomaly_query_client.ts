/** Strict current-state client for the Anomalies list. */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import {
  CurrentAnomalyPageResponseSchema,
  type CurrentAnomalyPage,
} from './current_anomaly_query_schemas';
import {
  AnomalyUnauthenticatedError,
  AnomalyValidationError,
  mapErrorToAnomalyQueryError,
  type FieldValidationError,
} from './anomaly_query_errors';

export interface CurrentAnomalyQueryOptions {
  signal?: AbortSignal;
  headers?: Record<string, string>;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface CurrentAnomalyQueryParams {
  definitionCode?: string;
  ownerDomain?: string;
  blocking?: boolean;
  limit?: number;
  cursor?: string;
}

function requestOptions(options?: CurrentAnomalyQueryOptions): RequestOptions {
  const headers = { ...(options?.headers ?? {}) };
  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() === 'authorization') delete headers[key];
  }
  const token = sessionClient.getToken();
  if (!token) throw new AnomalyUnauthenticatedError('缺少有效的管理員 Session');
  return { ...options, headers, token };
}

function validate(params: CurrentAnomalyQueryParams): void {
  const errors: FieldValidationError[] = [];
  if (params.limit !== undefined && (!Number.isInteger(params.limit) || params.limit < 1 || params.limit > 100)) {
    errors.push({ field: 'limit', message: 'limit 必須為 1 至 100 的整數' });
  }
  for (const [field, value] of [
    ['definition_code', params.definitionCode],
    ['owner_domain', params.ownerDomain],
  ] as const) {
    if (value !== undefined && (!value.trim() || value.length > 191)) {
      errors.push({ field, message: `${field} 不得為空且不得超過 191 字元` });
    }
  }
  if (params.cursor !== undefined && (!params.cursor.trim() || params.cursor.length > 2048)) {
    errors.push({ field: 'cursor', message: 'cursor 格式無效' });
  }
  if (errors.length) throw new AnomalyValidationError('目前異常查詢參數無效', errors);
}

export async function queryCurrentAnomalies(
  params: CurrentAnomalyQueryParams = {},
  options?: CurrentAnomalyQueryOptions
): Promise<CurrentAnomalyPage> {
  validate(params);
  const endpoint = '/api/v1/anomalies';
  try {
    const raw = await transport.get<unknown>(endpoint, {
      ...requestOptions(options),
      params: {
        definition_code: params.definitionCode,
        owner_domain: params.ownerDomain,
        blocking: params.blocking,
        limit: params.limit,
        cursor: params.cursor,
      },
    });
    const parsed = CurrentAnomalyPageResponseSchema.safeParse(raw);
    if (!parsed.success) {
      throw new AnomalyValidationError(
        `[${endpoint}] 回應契約驗證失敗: ${parsed.error.issues.map((issue) => issue.path.join('.')).join(', ')}`
      );
    }
    return parsed.data.data;
  } catch (error) {
    throw mapErrorToAnomalyQueryError(error, { endpoint });
  }
}

export const currentAnomalyQueryClient = { queryCurrentAnomalies };
