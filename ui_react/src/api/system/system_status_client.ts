/**
 * File: system_status_client.ts
 * Description: 以最新 memory token 查詢系統效能快照並嚴格解碼。
 */
import { sessionClient } from '../auth/session_client';
import { decodeEnvelope } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';
import {
  PerformanceSnapshotSchema,
  type PerformanceSnapshot,
} from './system_status_schema';

export const SYSTEM_STATUS_ENDPOINT = '/api/v1/system/status/performance-snapshot';

let inFlightSnapshot: {
  token: string;
  optionsKey: string;
  promise: Promise<PerformanceSnapshot>;
} | null = null;

function coalescingKey(
  options: Omit<RequestOptions, 'method' | 'body'> | undefined,
  headers: Record<string, string>
): string | null {
  if (options?.signal !== undefined) return null;
  const sortEntries = (values: Record<string, unknown>) =>
    Object.entries(values).sort(([left], [right]) => left.localeCompare(right));
  return JSON.stringify({
    headers: sortEntries(headers),
    params: sortEntries(options?.params ?? {}),
    timeoutMs: options?.timeoutMs ?? null,
    baseUrl: options?.baseUrl ?? '',
  });
}

export async function fetchPerformanceSnapshot(
  options?: Omit<RequestOptions, 'method' | 'body'>
): Promise<PerformanceSnapshot> {
  const token = sessionClient.getToken();
  if (!token) {
    throw new ApiHttpError(
      401,
      'SYSTEM_STATUS_UNAUTHENTICATED',
      '請先完成管理員登入後再查詢系統狀態。',
    );
  }

  const headers = { ...(options?.headers ?? {}) };
  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() === 'authorization') delete headers[key];
  }

  const optionsKey = coalescingKey(options, headers);
  if (
    optionsKey !== null &&
    inFlightSnapshot?.token === token &&
    inFlightSnapshot.optionsKey === optionsKey
  ) {
    return inFlightSnapshot.promise;
  }

  const promise = transport
    .get(SYSTEM_STATUS_ENDPOINT, {
      ...options,
      headers,
      token,
    })
    .then((raw) => decodeEnvelope(PerformanceSnapshotSchema, raw));

  if (optionsKey !== null) {
    inFlightSnapshot = { token, optionsKey, promise };
    const clear = () => {
      if (inFlightSnapshot?.promise === promise) inFlightSnapshot = null;
    };
    void promise.then(clear, clear);
  }

  return promise;
}

export { PerformanceSnapshotSchema, type PerformanceSnapshot };
