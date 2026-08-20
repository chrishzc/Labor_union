/**
 * @file system_status_schema.ts
 * @description 定義系統效能快照遙測資料之 Zod 驗證綱要與 TypeScript 型別。
 */
import { z } from 'zod';

export const PerformanceSnapshotSchema = z.object({
  started_at: z.string(),
  request_count: z.number().int().min(0),
  average_response_time_ms: z.number().min(0).nullable(),
  p50_response_time_upper_bound_ms: z.number().int().min(0).nullable(),
  p95_response_time_upper_bound_ms: z.number().int().min(0).nullable(),
  maximum_response_time_ms: z.number().min(0).nullable(),
});

export type PerformanceSnapshot = z.infer<typeof PerformanceSnapshotSchema>;
