/**
 * File: weekly_report_metrics_client.ts
 * Description: 查詢與儲存星期一至星期日的每週推廣及詢問數值。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { WeeklyReportMetricSchema } from './weekly_operations_report_schemas';

export type WeeklyReportMetric = z.infer<typeof WeeklyReportMetricSchema>;

const MetricsEnvelopeSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: z.array(WeeklyReportMetricSchema),
  error: z.string().nullable().optional(),
});

const MetricEnvelopeSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: WeeklyReportMetricSchema,
  error: z.string().nullable().optional(),
});

function headers(json = false): Record<string, string> {
  const token = sessionClient.getToken();
  if (!token) throw new Error('請先登入。');
  return {
    Accept: 'application/json',
    Authorization: `Bearer ${token}`,
    ...(json ? { 'Content-Type': 'application/json' } : {}),
  };
}

async function decode<T>(response: Response, schema: z.ZodSchema, fallback: string): Promise<T> {
  if (!response.ok) throw new Error(`${fallback}（HTTP ${response.status}）`);
  const parsed = schema.safeParse(await response.json());
  if (!parsed.success) throw new Error(fallback);
  const envelope = parsed.data as { success: boolean; data: T };
  if (!envelope.success) throw new Error(fallback);
  return envelope.data;
}

export const weeklyReportMetricsClient = {
  async list(startDate: string, endDate: string, signal?: AbortSignal): Promise<WeeklyReportMetric[]> {
    const params = new URLSearchParams({ start_date: startDate, end_date: endDate });
    const response = await fetch(`/api/v1/operations-reports/weekly/metrics?${params.toString()}`, {
      method: 'GET',
      headers: headers(),
      credentials: 'include',
      signal,
    });
    return decode<WeeklyReportMetric[]>(response, MetricsEnvelopeSchema, '無法取得每週推廣與詢問數值。');
  },

  async save(
    weekStartDate: string,
    values: { promotion_count: number | null; inquiry_count: number | null },
    signal?: AbortSignal,
  ): Promise<WeeklyReportMetric> {
    const response = await fetch(`/api/v1/operations-reports/weekly/metrics/${weekStartDate}`, {
      method: 'PUT',
      headers: headers(true),
      credentials: 'include',
      signal,
      body: JSON.stringify(values),
    });
    return decode<WeeklyReportMetric>(response, MetricEnvelopeSchema, '無法儲存每週推廣與詢問數值。');
  },
};
