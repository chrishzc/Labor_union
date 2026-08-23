/**
 * File: line_safe_config_client.ts
 * Description: 以 fresh Session、caller correlation 與 AbortSignal 查詢六種 LINE 去敏設定狀態。
 */

import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { LineSafeConfigError, mapLineSafeConfigError } from './line_safe_config_errors';
import {
  LineSafeConfigKindSchema,
  LineSafeConfigResponseSchema,
  type LineSafeConfig,
  type LineSafeConfigKind,
} from './line_safe_config_schemas';

export interface LineSafeConfigRequestOptions {
  correlationId: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
  headers?: Record<string, string>;
}

function requiredText(value: string, field: string): string {
  const normalized = value.trim();
  if (!normalized || normalized.length > 191) {
    throw new LineSafeConfigError('LINE_SAFE_CONFIG_VALIDATION', `${field} 必須是 1 至 191 字元的非空文字。`);
  }
  return normalized;
}

function requestOptions(options: LineSafeConfigRequestOptions): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new LineSafeConfigError('LINE_SAFE_CONFIG_UNAUTHENTICATED', '缺少有效的管理員 Session。', false, 401);
  const headers: Record<string, string> = {};
  for (const [name, value] of Object.entries(options.headers ?? {})) {
    if (['authorization', 'x-correlation-id', 'idempotency-key', 'content-type'].includes(name.toLowerCase())) continue;
    headers[name] = value;
  }
  headers['X-Correlation-ID'] = requiredText(options.correlationId, 'X-Correlation-ID');
  return { token, headers, signal: options.signal, timeoutMs: options.timeoutMs, baseUrl: options.baseUrl };
}

export async function getLineSafeConfig(kind: LineSafeConfigKind, options: LineSafeConfigRequestOptions): Promise<LineSafeConfig> {
  try {
    const parsedKind = LineSafeConfigKindSchema.safeParse(kind);
    if (!parsedKind.success) throw new LineSafeConfigError('LINE_SAFE_CONFIG_VALIDATION', 'LINE configuration kind 不在 closed allowlist。');
    const raw = await transport.get<unknown>(
      `/api/v1/line/configurations/${encodeURIComponent(parsedKind.data)}/safe`,
      requestOptions(options),
    );
    const parsed = LineSafeConfigResponseSchema.safeParse(raw);
    if (!parsed.success) throw new LineSafeConfigError('LINE_SAFE_CONFIG_CONTRACT', 'LINE safe configuration 回應不符合封閉契約。', false, undefined, undefined, parsed.error);
    if (parsed.data.data.kind !== parsedKind.data) throw new LineSafeConfigError('LINE_SAFE_CONFIG_CONTRACT', 'LINE safe configuration kind 與 request 不一致。');
    return parsed.data.data;
  } catch (error) {
    throw mapLineSafeConfigError(error);
  }
}

export const lineSafeConfigClient = { getSafe: getLineSafeConfig };
