/**
 * File: weekly_operations_report_query_client.ts
 * Description: 以 fresh Session 查詢自選期間的營運報表，驗證期間、分區與 server aggregate。
 */
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import { WeeklyOperationsReportError, mapWeeklyOperationsReportError } from './weekly_operations_report_errors';
import {
  WeeklyOperationsReportResponseSchema,
  WEEKLY_REPORT_SCHEMA_VERSION,
  CaseStatisticsResponseSchema,
  type CaseStatisticsData,
  type WeeklyOperationsReportData,
} from './weekly_operations_report_schemas';

export interface WeeklyOperationsReportQueryOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
}

function parseDate(value: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value ? null : parsed;
}

export function validateOperationsReportDateRange(startDate: string, endDate: string): void {
  const start = parseDate(startDate);
  const end = parseDate(endDate);
  if (!start || !end || start.getTime() > end.getTime()) {
    throw new WeeklyOperationsReportError('WEEKLY_REPORT_VALIDATION', '起日與迄日必須有效，且起日不得晚於迄日。');
  }
}


export const caseStatisticsQueryClient = {
  async query(year: number, quarter: number | null, month: number | null, options?: WeeklyOperationsReportQueryOptions): Promise<CaseStatisticsData> {
    const token = sessionClient.getToken();
    if (!token) throw new WeeklyOperationsReportError('WEEKLY_REPORT_UNAUTHENTICATED', '請先登入。', false, 401);
    const raw = await transport.get<unknown>('/api/v1/operations-reports/case-statistics', {
      signal: options?.signal, timeoutMs: options?.timeoutMs, baseUrl: options?.baseUrl, token,
      params: { year, quarter, month }, cache: 'no-store',
    });
    const decoded = CaseStatisticsResponseSchema.safeParse(raw);
    if (!decoded.success) throw new ApiDecodeError('案件統計回應結構異常。', decoded.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message, code: issue.code })), raw);
    const data = decoded.data.data;
    const startMonth = month ?? (quarter ? (quarter - 1) * 3 + 1 : 1);
    const endMonth = month ?? (quarter ? quarter * 3 : 12);
    const expectedStart = `${year}-${String(startMonth).padStart(2, '0')}-01`;
    const expectedEnd = `${year}-${String(endMonth).padStart(2, '0')}-${new Date(Date.UTC(year, endMonth, 0)).getUTCDate()}`;
    if (data.year !== year || data.quarter !== quarter || data.month !== month
      || data.start_date !== expectedStart || data.end_date !== expectedEnd) {
      throw new WeeklyOperationsReportError('WEEKLY_REPORT_PERIOD_MISMATCH', '案件統計期間與篩選不一致。');
    }
    const summary = data.summary;
    if (Object.values(summary.order_status_counts).reduce((sum, value) => sum + value, 0) + summary.other_status_count !== summary.application_count
      || summary.general_eligible_count + (summary.general_ineligible_count ?? 0) + summary.subsidized_eligible_count
        + (summary.subsidized_ineligible_count ?? 0) + summary.unclassified_qualification_count !== summary.application_count
      || summary.application_count > data.annual_application_count) {
      throw new WeeklyOperationsReportError('WEEKLY_REPORT_AGGREGATE_MISMATCH', '案件統計合計不一致。');
    }
    return data;
  },
};


function assertWeeklyView(view: WeeklyOperationsReportData, startDate: string, endDate: string): WeeklyOperationsReportData {
  if (view.period.start_date !== startDate || view.period.end_date !== endDate) {
    throw new WeeklyOperationsReportError('WEEKLY_REPORT_PERIOD_MISMATCH', '週報 period 與 request 不一致。');
  }
  if (view.summary.application_count !== view.case_rows.length) {
    throw new WeeklyOperationsReportError('WEEKLY_REPORT_AGGREGATE_MISMATCH', '案件受理 aggregate 不一致。');
  }
  const reviewCounts = view.case_rows.reduce((counts, row) => {
    counts[row.review_result] += 1;
    return counts;
  }, { general_eligible: 0, subsidized_eligible: 0, rejected_unpartitioned: 0, pending: 0 });
  if (
    view.summary.general_eligible_count !== reviewCounts.general_eligible
    || view.summary.subsidized_eligible_count !== reviewCounts.subsidized_eligible
    || view.summary.rejection_unpartitioned_count !== reviewCounts.rejected_unpartitioned
  ) {
    throw new WeeklyOperationsReportError('WEEKLY_REPORT_AGGREGATE_MISMATCH', '案件審核 aggregate 不一致。');
  }
  const partitionKinds = new Set(view.subsidy_partitions.map((partition) => partition.citizen_kind));
  if (partitionKinds.size !== 2 || !partitionKinds.has('general') || !partitionKinds.has('subsidized')) {
    throw new WeeklyOperationsReportError('WEEKLY_REPORT_PARTITION_MISMATCH', '週報缺少必要補助 partition。');
  }
  for (const partition of view.subsidy_partitions) {
    const rowTotal = partition.rows.reduce((sum, row) => sum + row.subsidy_amount_ntd, 0);
    if (partition.row_count !== partition.rows.length || partition.total_amount_ntd !== rowTotal) {
      throw new WeeklyOperationsReportError('WEEKLY_REPORT_AGGREGATE_MISMATCH', '補助 partition aggregate 不一致。');
    }
  }
  for (const row of view.service_rows) {
    const weekStart = parseDate(row.period_start_date);
    const weekEnd = parseDate(row.period_end_date);
    if (!weekStart || !weekEnd || weekStart.getUTCDay() !== 1 || weekEnd.getUTCDay() !== 0
      || weekEnd.getTime() - weekStart.getTime() !== 6 * 24 * 60 * 60 * 1000) {
      throw new WeeklyOperationsReportError('WEEKLY_REPORT_PERIOD_MISMATCH', '服務工時列不是星期一至星期日。');
    }
    if (row.weekly_hours !== null && row.service_hours_per_day !== null
      && Math.abs(row.weekly_hours - (row.weekly_work_days * row.service_hours_per_day)) > 0.000001) {
      throw new WeeklyOperationsReportError('WEEKLY_REPORT_AGGREGATE_MISMATCH', '服務工時 aggregate 不一致。');
    }
    if ((row.weekly_hours === null) !== (row.service_hours_per_day === null)) {
      throw new WeeklyOperationsReportError('WEEKLY_REPORT_AGGREGATE_MISMATCH', '服務工時缺值狀態不一致。');
    }
  }
  for (const metric of view.weekly_metrics) {
    const weekStart = parseDate(metric.week_start_date);
    const weekEnd = parseDate(metric.week_end_date);
    if (!weekStart || !weekEnd || weekStart.getUTCDay() !== 1 || weekEnd.getUTCDay() !== 0
      || weekEnd.getTime() - weekStart.getTime() !== 6 * 24 * 60 * 60 * 1000) {
      throw new WeeklyOperationsReportError('WEEKLY_REPORT_PERIOD_MISMATCH', '週指標不是星期一至星期日。');
    }
  }
  return view;
}

export const weeklyOperationsReportQueryClient = {
  async query(startDate: string, endDate: string, options?: WeeklyOperationsReportQueryOptions): Promise<WeeklyOperationsReportData> {
    validateOperationsReportDateRange(startDate, endDate);
    const token = sessionClient.getToken();
    if (!token) throw new WeeklyOperationsReportError('WEEKLY_REPORT_UNAUTHENTICATED', '請先登入。', false, 401);
    try {
      const raw = await transport.get<unknown>('/api/v1/operations-reports/weekly', {
        signal: options?.signal,
        timeoutMs: options?.timeoutMs,
        baseUrl: options?.baseUrl,
        token,
        params: { start_date: startDate, end_date: endDate, schema_version: WEEKLY_REPORT_SCHEMA_VERSION },
      });
      const decoded = WeeklyOperationsReportResponseSchema.safeParse(raw);
      if (!decoded.success) {
        throw new ApiDecodeError(
          '營運週報回應結構異常。',
          decoded.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message, code: issue.code })),
          raw,
        );
      }
      if (!decoded.data.success) {
        throw new WeeklyOperationsReportError('WEEKLY_REPORT_FAILURE', decoded.data.error ?? decoded.data.message);
      }
      return assertWeeklyView(decoded.data.data, startDate, endDate);
    } catch (error) {
      throw mapWeeklyOperationsReportError(error);
    }
  },
};
