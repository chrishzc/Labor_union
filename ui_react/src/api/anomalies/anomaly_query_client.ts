/**
 * File: anomaly_query_client.ts
 * Description: Anomalies 四個唯讀 GET 的 bounded client。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import {
  AnomalySummariesResponseSchema,
  ImportWarningTasksResponseSchema,
  type AnomalySummaryView,
  type ImportWarningTaskView,
  type AnomalySummariesResponse,
  type ImportWarningTasksResponse,
  AnomalyDetailResponseSchema,
  ImportWarningReferralResponseSchema,
  type AnomalyDetailView,
  type ImportWarningReferralView,
} from './anomaly_query_schemas';
import {
  AnomalyUnauthenticatedError,
  AnomalyValidationError,
  mapErrorToAnomalyQueryError,
  type FieldValidationError,
} from './anomaly_query_errors';

export interface AnomalyQueryOptions {
  signal?: AbortSignal;
  headers?: Record<string, string>;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface QueryAnomaliesParams {
  activeOnly?: boolean;
  limit?: number;
  offset?: number;
}

export interface QueryImportWarningTasksParams {
  activeOnly?: boolean;
  limit?: number;
  offset?: number;
}

export interface AnomalyDetailParams {
  fingerprint: string;
}

export interface ImportWarningReferralParams {
  occurrenceIdentity: string;
  expectedVersion: number;
}

export interface AnomalyQueryClient {
  queryAnomalies(
    params?: QueryAnomaliesParams,
    options?: AnomalyQueryOptions
  ): Promise<AnomalySummaryView[]>;
  queryImportWarningTasks(
    params?: QueryImportWarningTasksParams,
    options?: AnomalyQueryOptions
  ): Promise<ImportWarningTaskView[]>;
  queryAnomalyDetail(
    params: AnomalyDetailParams,
    options?: AnomalyQueryOptions
  ): Promise<AnomalyDetailView>;
  queryImportWarningReferral(
    params: ImportWarningReferralParams,
    options?: AnomalyQueryOptions
  ): Promise<ImportWarningReferralView>;
}

// ============================================================================
// Internal Helpers
// ============================================================================

function mergeRequestOptions(
  custom?: AnomalyQueryOptions,
  defaults?: AnomalyQueryOptions
): RequestOptions {
  const mergedHeaders: Record<string, string> = {
    ...(defaults?.headers || {}),
    ...(custom?.headers || {}),
  };

  for (const headerName of Object.keys(mergedHeaders)) {
    if (headerName.toLowerCase() === 'authorization') {
      delete mergedHeaders[headerName];
    }
  }

  const token = sessionClient.getToken();
  if (!token) {
    throw new AnomalyUnauthenticatedError('缺少有效的管理員 Session');
  }

  return {
    signal: custom?.signal || defaults?.signal,
    token,
    timeoutMs: custom?.timeoutMs || defaults?.timeoutMs,
    baseUrl: custom?.baseUrl !== undefined ? custom.baseUrl : defaults?.baseUrl,
    headers: mergedHeaders,
  };
}

function validatePaginationParams(
  limit?: number,
  offset?: number
): void {
  const fieldErrors: FieldValidationError[] = [];

  if (limit !== undefined) {
    if (!Number.isInteger(limit) || limit < 1 || limit > 200) {
      fieldErrors.push({
        field: 'limit',
        message: '分頁筆數 (limit) 必須為 1 至 200 之間的整數',
      });
    }
  }

  if (offset !== undefined) {
    if (!Number.isInteger(offset) || offset < 0) {
      fieldErrors.push({
        field: 'offset',
        message: '分頁位移 (offset) 必須為大於或等於 0 的整數',
      });
    }
  }

  if (fieldErrors.length > 0) {
    throw new AnomalyValidationError(
      `請求參數驗證失敗: ${fieldErrors.map((f) => `[${f.field}] ${f.message}`).join(', ')}`,
      fieldErrors
    );
  }
}

function validateFingerprint(fingerprint: string): void {
  if (!/^[0-9a-f]{64}$/.test(fingerprint)) {
    throw new AnomalyValidationError('fingerprint 必須為 64 位小寫十六進位字串', [
      { field: 'fingerprint', message: '格式無效' },
    ]);
  }
}

function validateReferralParams(params: ImportWarningReferralParams): void {
  const fieldErrors: FieldValidationError[] = [];
  if (!params.occurrenceIdentity.trim() || params.occurrenceIdentity.length > 191) {
    fieldErrors.push({
      field: 'occurrence_identity',
      message: 'occurrence_identity 不得為空且不得超過 191 字元',
    });
  }
  if (!Number.isInteger(params.expectedVersion) || params.expectedVersion < 1) {
    fieldErrors.push({
      field: 'expected_version',
      message: 'expected_version 必須為正整數',
    });
  }
  if (fieldErrors.length > 0) {
    throw new AnomalyValidationError('匯入警示導向參數驗證失敗', fieldErrors);
  }
}

function decodeStrictResponse<T>(
  schema: z.ZodType<T>,
  raw: unknown,
  endpoint: string
): T {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw new AnomalyValidationError(
      `[${endpoint}] 回應內容格式無效，預期為 JSON 物件`
    );
  }

  const result = schema.safeParse(raw);
  if (!result.success) {
    const issues: FieldValidationError[] = result.error.issues.map((issue) => ({
      field: issue.path.join('.') || '(root)',
      message: issue.message,
    }));
    const formatted = issues.map((i) => `[${i.field}] ${i.message}`).join(', ');
    throw new AnomalyValidationError(
      `[${endpoint}] 資料結構驗證失敗: ${formatted}`,
      issues
    );
  }

  return result.data;
}

// ============================================================================
// Standalone Query Functions
// ============================================================================

/**
 * 查詢異常清單摘要 (GET /api/v1/anomalies?include_snapshot=false)
 */
export async function queryAnomalies(
  params?: QueryAnomaliesParams,
  options?: AnomalyQueryOptions
): Promise<AnomalySummaryView[]> {
  validatePaginationParams(params?.limit, params?.offset);

  const queryParams: Record<string, string | number | boolean | null | undefined> = {
    include_snapshot: false, // 嚴格固定為 false，不取得未型別化快照
  };

  if (params?.activeOnly !== undefined) {
    queryParams.active_only = params.activeOnly;
  }
  if (params?.limit !== undefined) {
    queryParams.limit = params.limit;
  }
  if (params?.offset !== undefined) {
    queryParams.offset = params.offset;
  }

  const endpoint = '/api/v1/anomalies';
  const reqOptions: RequestOptions = {
    ...mergeRequestOptions(options),
    params: queryParams,
  };

  try {
    const raw = await transport.get<unknown>(endpoint, reqOptions);
    const envelope: AnomalySummariesResponse = decodeStrictResponse(
      AnomalySummariesResponseSchema,
      raw,
      endpoint
    );

    if (!envelope.success) {
      const msg = envelope.error || envelope.message || '取得異常摘要失敗';
      throw new AnomalyValidationError(`[${endpoint}] ${msg}`);
    }

    return envelope.data;
  } catch (err) {
    throw mapErrorToAnomalyQueryError(err, { endpoint });
  }
}

/**
 * 查詢匯入警示追蹤任務清單 (GET /api/v1/import-warning-tracking/tasks)
 */
export async function queryImportWarningTasks(
  params?: QueryImportWarningTasksParams,
  options?: AnomalyQueryOptions
): Promise<ImportWarningTaskView[]> {
  validatePaginationParams(params?.limit, params?.offset);

  const queryParams: Record<string, string | number | boolean | null | undefined> = {};

  if (params?.activeOnly !== undefined) {
    queryParams.active_only = params.activeOnly;
  }
  if (params?.limit !== undefined) {
    queryParams.limit = params.limit;
  }
  if (params?.offset !== undefined) {
    queryParams.offset = params.offset;
  }

  const endpoint = '/api/v1/import-warning-tracking/tasks';
  const reqOptions: RequestOptions = {
    ...mergeRequestOptions(options),
    params: queryParams,
  };

  try {
    const raw = await transport.get<unknown>(endpoint, reqOptions);
    const envelope: ImportWarningTasksResponse = decodeStrictResponse(
      ImportWarningTasksResponseSchema,
      raw,
      endpoint
    );

    if (!envelope.success) {
      const msg = envelope.error || envelope.message || '取得匯入警示追蹤清單失敗';
      throw new AnomalyValidationError(`[${endpoint}] ${msg}`);
    }

    return envelope.data;
  } catch (err) {
    throw mapErrorToAnomalyQueryError(err, { endpoint });
  }
}

/** 查詢選取異常的 typed detail（GET-only；raw snapshot 會 fail closed）。 */
export async function queryAnomalyDetail(
  params: AnomalyDetailParams,
  options?: AnomalyQueryOptions
): Promise<AnomalyDetailView> {
  validateFingerprint(params.fingerprint);
  const endpoint = `/api/v1/anomalies/${encodeURIComponent(params.fingerprint)}`;
  try {
    const raw = await transport.get<unknown>(endpoint, mergeRequestOptions(options));
    const envelope = decodeStrictResponse(
      AnomalyDetailResponseSchema,
      raw,
      endpoint
    );
    if (!envelope.success) {
      throw new AnomalyValidationError(
        `[${endpoint}] ${envelope.error || envelope.message || '取得異常詳情失敗'}`
      );
    }
    return envelope.data;
  } catch (err) {
    throw mapErrorToAnomalyQueryError(err, { endpoint });
  }
}

/** 查詢 HCM warning 的 owning referral（GET-only；不解鎖 transition）。 */
export async function queryImportWarningReferral(
  params: ImportWarningReferralParams,
  options?: AnomalyQueryOptions
): Promise<ImportWarningReferralView> {
  validateReferralParams(params);
  const endpoint = `/api/v1/import-warning-tracking/tasks/${encodeURIComponent(params.occurrenceIdentity)}/referral`;
  try {
    const raw = await transport.get<unknown>(endpoint, {
      ...mergeRequestOptions(options),
      params: { expected_version: params.expectedVersion },
    });
    const envelope = decodeStrictResponse(
      ImportWarningReferralResponseSchema,
      raw,
      endpoint
    );
    if (!envelope.success) {
      throw new AnomalyValidationError(
        `[${endpoint}] ${envelope.error || envelope.message || '取得匯入警示導向失敗'}`
      );
    }
    return envelope.data;
  } catch (err) {
    throw mapErrorToAnomalyQueryError(err, { endpoint });
  }
}

// ============================================================================
// Default Client Implementation & Factory / Singleton
// ============================================================================

export class DefaultAnomalyQueryClient implements AnomalyQueryClient {
  private readonly defaultOptions?: AnomalyQueryOptions;

  constructor(defaultOptions?: AnomalyQueryOptions) {
    this.defaultOptions = defaultOptions;
  }

  public queryAnomalies(
    params?: QueryAnomaliesParams,
    options?: AnomalyQueryOptions
  ): Promise<AnomalySummaryView[]> {
    return queryAnomalies(
      params,
      mergeRequestOptions(options, this.defaultOptions)
    );
  }

  public queryImportWarningTasks(
    params?: QueryImportWarningTasksParams,
    options?: AnomalyQueryOptions
  ): Promise<ImportWarningTaskView[]> {
    return queryImportWarningTasks(
      params,
      mergeRequestOptions(options, this.defaultOptions)
    );
  }

  public queryAnomalyDetail(
    params: AnomalyDetailParams,
    options?: AnomalyQueryOptions
  ): Promise<AnomalyDetailView> {
    return queryAnomalyDetail(params, mergeRequestOptions(options, this.defaultOptions));
  }

  public queryImportWarningReferral(
    params: ImportWarningReferralParams,
    options?: AnomalyQueryOptions
  ): Promise<ImportWarningReferralView> {
    return queryImportWarningReferral(
      params,
      mergeRequestOptions(options, this.defaultOptions)
    );
  }
}

export function createAnomalyQueryClient(
  defaultOptions?: AnomalyQueryOptions
): AnomalyQueryClient {
  return new DefaultAnomalyQueryClient(defaultOptions);
}

export const anomalyQueryClient: AnomalyQueryClient =
  new DefaultAnomalyQueryClient();
