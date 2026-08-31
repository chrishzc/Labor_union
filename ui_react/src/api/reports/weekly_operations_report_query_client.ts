/**
 * File: weekly_operations_report_query_client.ts
 * Description: 以 fresh Session 查詢週一週界的營運週報，驗證期間、遮罩、分區與 server aggregate。
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

export function validateWeeklyReportWeekStart(weekStart: string): Date {
  const parsed = parseDate(weekStart);
  if (!parsed || parsed.getUTCDay() !== 1) {
    throw new WeeklyOperationsReportError('WEEKLY_REPORT_VALIDATION', '週起日必須是有效的星期一。');
  }
  return parsed;
}

export function weeklyReportWeekEnd(weekStart: string): string {
  const start = validateWeeklyReportWeekStart(weekStart);
  start.setUTCDate(start.getUTCDate() + 6);
  return start.toISOString().slice(0, 10);
}

const ISO_WEEK_PATTERN = /^(\d{4})-W(\d{2})$/;
const WEEK_MILLISECONDS = 7 * 24 * 60 * 60 * 1000;

function firstIsoMonday(year: number): Date {
  const januaryFourth = new Date(Date.UTC(year, 0, 4));
  januaryFourth.setUTCDate(januaryFourth.getUTCDate() - ((januaryFourth.getUTCDay() + 6) % 7));
  return januaryFourth;
}

export function weeklyReportIsoWeek(weekStart: string): string {
  const monday = validateWeeklyReportWeekStart(weekStart);
  const thursday = new Date(monday);
  thursday.setUTCDate(thursday.getUTCDate() + 3);
  const isoYear = thursday.getUTCFullYear();
  const week = Math.floor((monday.getTime() - firstIsoMonday(isoYear).getTime()) / WEEK_MILLISECONDS) + 1;
  return `${isoYear}-W${String(week).padStart(2, '0')}`;
}

export function weeklyReportWeekStart(isoWeek: string): string {
  const match = ISO_WEEK_PATTERN.exec(isoWeek);
  if (!match) {
    throw new WeeklyOperationsReportError('WEEKLY_REPORT_VALIDATION', '週別必須是有效的 ISO 週。');
  }
  const isoYear = Number(match[1]);
  const week = Number(match[2]);
  if (week < 1 || week > 53) {
    throw new WeeklyOperationsReportError('WEEKLY_REPORT_VALIDATION', '週別必須是有效的 ISO 週。');
  }
  const monday = firstIsoMonday(isoYear);
  monday.setUTCDate(monday.getUTCDate() + ((week - 1) * 7));
  const weekStart = monday.toISOString().slice(0, 10);
  if (weeklyReportIsoWeek(weekStart) !== isoWeek) {
    throw new WeeklyOperationsReportError('WEEKLY_REPORT_VALIDATION', '週別必須是有效的 ISO 週。');
  }
  return weekStart;
}

function isMasked(value: string): boolean {
  return value === '—' || value.includes('*');
}

function assertWeeklyView(view: WeeklyOperationsReport, weekStart: string): WeeklyOperationsReport {
  if (view.period.week_start !== weekStart || view.period.week_end !== weeklyReportWeekEnd(weekStart)) {
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
  if (view.case_rows.some((row) => !isMasked(row.applicant_name_masked))) {
    throw new WeeklyOperationsReportError('WEEKLY_REPORT_PII_NOT_MASKED', '案件受理資料包含未遮罩姓名。');
  }
  for (const row of view.service_rows) {
    if (!isMasked(row.client_name_masked) || !isMasked(row.staff_name_masked)) {
      throw new WeeklyOperationsReportError('WEEKLY_REPORT_PII_NOT_MASKED', '服務工時資料包含未遮罩姓名。');
    }
    if (row.week_start !== view.period.week_start || row.week_end !== view.period.week_end) {
      throw new WeeklyOperationsReportError('WEEKLY_REPORT_PERIOD_MISMATCH', '服務工時列的 period 不一致。');
    }
    if (Math.abs(row.weekly_hours - (row.weekly_work_days * row.service_hours_per_day)) > 0.000001) {
      throw new WeeklyOperationsReportError('WEEKLY_REPORT_AGGREGATE_MISMATCH', '服務工時 aggregate 不一致。');
    }
  }
  return view;
}

export const weeklyOperationsReportQueryClient = {
  async query(weekStart: string, options?: WeeklyOperationsReportQueryOptions): Promise<WeeklyOperationsReport> {
    validateWeeklyReportWeekStart(weekStart);
    const token = sessionClient.getToken();
    if (!token) throw new WeeklyOperationsReportError('WEEKLY_REPORT_UNAUTHENTICATED', '請先登入。', false, 401);
    try {
      const raw = await transport.get<unknown>('/api/v1/operations-reports/weekly', {
        signal: options?.signal,
        timeoutMs: options?.timeoutMs,
        baseUrl: options?.baseUrl,
        token,
        params: { week_start: weekStart },
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
      return assertWeeklyView(decoded.data.data, weekStart);
    } catch (error) {
      throw mapWeeklyOperationsReportError(error);
    }
  },
};
