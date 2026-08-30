/**
 * File: anomaly_detail_client.ts
 * Description: Anomalies detail 與 recovery 的唯讀 GET client。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { AnomalyDetailError, mapAnomalyDetailError } from './anomaly_detail_errors';
import {
  AnomalyDetailResponseSchema,
  AnomalyRecoveryResponseSchema,
  type AnomalyDetailView,
  type AnomalyRecoveryContextView,
} from './anomaly_detail_schemas';

export interface AnomalyDetailOptions {
  signal?: AbortSignal;
  headers?: Record<string, string>;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface AnomalyDetailParams { fingerprint: string }
export interface AnomalyRecoveryParams { issueKey: string }

function requestOptions(options?: AnomalyDetailOptions): RequestOptions {
  const headers = { ...(options?.headers ?? {}) };
  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() === 'authorization') delete headers[key];
  }
  const token = sessionClient.getToken();
  if (!token) throw new AnomalyDetailError('UNAUTHENTICATED', '缺少有效的管理員 Session', false, 401);
  return { ...options, headers, token };
}

function endpointFor(prefix: string, fingerprint: string): string {
  if (!/^[0-9a-f]{64}$/.test(fingerprint)) {
    throw new AnomalyDetailError('VALIDATION', 'fingerprint 必須為 64 位小寫十六進位字串');
  }
  return `${prefix}/${encodeURIComponent(fingerprint)}`;
}

function currentIssueEndpoint(issueKey: string): string {
  if (!/^ci_[0-9a-f]{64}$/.test(issueKey)) {
    throw new AnomalyDetailError('VALIDATION', 'issue_key 必須為 current anomaly opaque key');
  }
  return `/api/v1/anomaly-recovery/${encodeURIComponent(issueKey)}`;
}

function decode<T>(schema: z.ZodType<T>, raw: unknown, endpoint: string): T {
  const parsed = schema.safeParse(raw);
  if (!parsed.success) {
    throw new AnomalyDetailError('VALIDATION', `[${endpoint}] 回應契約驗證失敗: ${parsed.error.issues.map((issue) => issue.path.join('.')).join(', ')}`);
  }
  return parsed.data;
}

async function getData<T>(endpoint: string, schema: z.ZodType<{ success: true; data: T }>, options?: AnomalyDetailOptions): Promise<T> {
  try {
    const raw = await transport.get<unknown>(endpoint, requestOptions(options));
    return decode(schema, raw, endpoint).data;
  } catch (error) {
    throw mapAnomalyDetailError(error);
  }
}

export function queryAnomalyDetail(params: AnomalyDetailParams, options?: AnomalyDetailOptions): Promise<AnomalyDetailView> {
  return getData(endpointFor('/api/v1/anomalies', params.fingerprint), AnomalyDetailResponseSchema, options);
}

export function queryAnomalyRecovery(params: AnomalyRecoveryParams, options?: AnomalyDetailOptions): Promise<AnomalyRecoveryContextView> {
  return getData(currentIssueEndpoint(params.issueKey), AnomalyRecoveryResponseSchema, options);
}

export const anomalyDetailClient = { queryAnomalyDetail, queryAnomalyRecovery };
