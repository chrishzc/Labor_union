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
  type WeeklyOperationsReport,
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


function assertWeeklyView(view: WeeklyOperationsReport, startDate: string, endDate: string): WeeklyOperationsReport {
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
    if (row.period_start_date !== view.period.start_date || row.period_end_date !== view.period.end_date) {
      throw new WeeklyOperationsReportError('WEEKLY_REPORT_PERIOD_MISMATCH', '服務工時列的 period 不一致。');
    }
    if (Math.abs(row.weekly_hours - (row.weekly_work_days * row.service_hours_per_day)) > 0.000001) {
      throw new WeeklyOperationsReportError('WEEKLY_REPORT_AGGREGATE_MISMATCH', '服務工時 aggregate 不一致。');
    }
  }
  return view;
}

export const weeklyOperationsReportQueryClient = {
  async query(startDate: string, endDate: string, options?: WeeklyOperationsReportQueryOptions): Promise<WeeklyOperationsReport> {
    validateOperationsReportDateRange(startDate, endDate);
    const token = sessionClient.getToken();
    if (!token) throw new WeeklyOperationsReportError('WEEKLY_REPORT_UNAUTHENTICATED', '請先登入。', false, 401);
    try {
      const raw = await transport.get<unknown>('/api/v1/operations-reports/weekly', {
        signal: options?.signal,
        timeoutMs: options?.timeoutMs,
        baseUrl: options?.baseUrl,
        token,
        params: { start_date: startDate, end_date: endDate },
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
