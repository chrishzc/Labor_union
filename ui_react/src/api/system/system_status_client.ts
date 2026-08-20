/**
 * @file system_status_client.ts
 * @description 系統效能狀態 API 客戶端，串接後端效能快照遙測端點並完成信封解碼。
 */
import { decodeEnvelope } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import {
  PerformanceSnapshotSchema,
  type PerformanceSnapshot,
} from './system_status_schema';

export const SYSTEM_STATUS_ENDPOINT = '/api/v1/system/status/performance-snapshot';

export async function fetchPerformanceSnapshot(
  options?: Omit<RequestOptions, 'method' | 'body'>
): Promise<PerformanceSnapshot> {
  const raw = await transport.get(SYSTEM_STATUS_ENDPOINT, options);
  return decodeEnvelope(PerformanceSnapshotSchema, raw);
}

export { PerformanceSnapshotSchema, type PerformanceSnapshot };
