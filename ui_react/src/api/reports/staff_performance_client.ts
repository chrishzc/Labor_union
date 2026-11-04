/** Strict, authenticated transport for staff performance and its XLSX export. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { applicationFetch } from '../shared/application_fetch';

const count = z.number().int().nonnegative();
const date = z.iso.date();
const totals = z.strictObject({ case_count: count.nullable(), service_hours: z.number().nonnegative().nullable(), total_amount_ntd: count.nullable() });
const identity = { staff_id: z.number().int().positive(), union_no: z.string().nullable(), staff_name: z.string() };
const trend = z.strictObject({ start_date: date, end_date: date, label: z.string(), totals });
const row = z.strictObject({ ...identity, totals, previous_totals: totals,
  cases: z.array(z.strictObject({ case_no: z.string(), service_start: date.nullable(), service_end: date.nullable(),
    work_days: count, service_hours: z.number().nonnegative().nullable(), total_amount_ntd: count.nullable(),
    actual_start_date: date.nullable(), primary_staff_id: z.number().int().positive(),
    recognized_case_count: z.number().int().min(0).max(1).nullable(), recognized_amount_ntd: count.nullable() })), trend: z.array(trend) });
export const StaffPerformanceSchema = z.strictObject({
  schema_version: z.literal('staff-performance.v2'), period: z.enum(['month', 'quarter', 'year']),
  year: z.number().int(), month: z.number().int().nullable(), quarter: z.number().int().nullable(),
  start_date: date, end_date: date, through_date: date, previous_start_date: date, previous_end_date: date,
  generated_at: z.iso.datetime({ offset: true }), selected_staff_id: z.number().int().positive().nullable(),
  available_years: z.array(z.number().int()), staff_options: z.array(z.strictObject(identity)),
  service_staff_count: count, totals, rows: z.array(row), trend: z.array(trend),
});
const response = z.strictObject({ success: z.literal(true), message: z.string(), data: StaffPerformanceSchema, error: z.null().optional() });
export type StaffPerformanceReport = z.infer<typeof StaffPerformanceSchema>;
export type StaffPerformanceRow = StaffPerformanceReport['rows'][number];
export type PerformanceMetric = 'case_count' | 'service_hours' | 'total_amount_ntd';
export type PerformanceFilters = { year: number; period: 'month' | 'quarter' | 'year'; month?: number; quarter?: number; staff_id?: number };

function params(filters: PerformanceFilters) {
  return { year: filters.year, period: filters.period,
    ...(filters.period === 'month' ? { month: filters.month } : {}),
    ...(filters.period === 'quarter' ? { quarter: filters.quarter } : {}),
    ...(filters.staff_id ? { staff_id: filters.staff_id } : {}) };
}

export const staffPerformanceClient = {
  async query(filters: PerformanceFilters, signal?: AbortSignal): Promise<StaffPerformanceReport> {
    const token = sessionClient.getToken();
    if (!token) throw new Error('請先登入。');
    const raw = await transport.get<unknown>('/api/v1/operations-reports/staff-performance', { params: params(filters), token, signal, cache: 'no-store' });
    const decoded = response.safeParse(raw);
    if (!decoded.success) throw new Error('月嫂表現分析回應格式不正確。');
    const data = decoded.data.data;
    if (data.year !== filters.year || data.period !== filters.period || data.selected_staff_id !== (filters.staff_id ?? null)
      || data.month !== (filters.period === 'month' ? filters.month : null)
      || data.quarter !== (filters.period === 'quarter' ? filters.quarter : null)) throw new Error('分析結果與目前篩選不一致，請重新查詢。');
    return data;
  },
  async download(filters: PerformanceFilters, sortBy: PerformanceMetric, signal?: AbortSignal) {
    const token = sessionClient.getToken();
    if (!token) throw new Error('請先登入。');
    const query = new URLSearchParams(Object.entries({ ...params(filters), sort_by: sortBy }).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)]));
    const result = await applicationFetch(`/api/v1/operations-reports/staff-performance/export?${query}`, { headers: { Authorization: `Bearer ${token}` }, signal });
    if (!result.ok) throw new Error('月嫂表現分析匯出失敗，請重試。');
    if (!result.headers.get('content-type')?.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
      || result.headers.get('X-Staff-Performance-Version') !== 'staff-performance.v2') throw new Error('匯出檔案格式不正確。');
    const blob = await result.blob();
    if (!blob.size) throw new Error('匯出檔案為空。');
    return { blob, filename: `staff-performance-${filters.year}-${filters.period}.xlsx` };
  },
};
