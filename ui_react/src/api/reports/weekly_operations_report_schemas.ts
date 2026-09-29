/**
 * File: weekly_operations_report_schemas.ts
 * Description: 定義營運週報三分頁、期間、彙總與資料品質問題的 strict canonical view。
 */
import { z } from 'zod';
import { SubsidyReportRowSchema } from './subsidy_report_query_schemas';

export const WEEKLY_REPORT_SCHEMA_VERSION = 'operations-report.v4' as const;

const DateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const NonNegativeNullableIntegerSchema = z.number().int().nonnegative().nullable();

export const WeeklyOperationsReportPeriodSchema = z.strictObject({
  start_date: DateSchema,
  end_date: DateSchema,
  timezone: z.literal('Asia/Taipei'),
  period_label: z.string().min(1),
});

export const WeeklyOperationsReportSummarySchema = z.strictObject({
  application_count: z.number().int().nonnegative(),
  general_eligible_count: z.number().int().nonnegative(),
  general_ineligible_count: NonNegativeNullableIntegerSchema,
  subsidized_eligible_count: z.number().int().nonnegative(),
  subsidized_ineligible_count: NonNegativeNullableIntegerSchema,
  rejection_unpartitioned_count: z.number().int().nonnegative(),
  order_established_count: z.number().int().nonnegative(),
  negotiating_count: z.number().int().nonnegative(),
  cancelled_count: z.number().int().nonnegative(),
  incomplete_count: z.number().int().nonnegative(),
});

export const WeeklyReportCaseTotalsSchema = z.strictObject({
  ...WeeklyOperationsReportSummarySchema.shape,
  year: z.number().int().positive(),
  month: z.number().int().min(1).max(12).nullable(),
  start_date: DateSchema,
  end_date: DateSchema,
  promotion_count: NonNegativeNullableIntegerSchema,
  inquiry_count: NonNegativeNullableIntegerSchema,
  review_rejected_count: z.number().int().nonnegative(),
  order_status_counts: z.record(z.string().min(1), z.number().int().nonnegative()),
});

export const WeeklyOperationsCaseRowSchema = z.strictObject({
  case_no: z.string().min(1),
  applicant_name: z.string().min(1),
  application_date: DateSchema.nullable(),
  identity_status: z.string().nullable(),
  review_result: z.enum(['general_eligible', 'subsidized_eligible', 'rejected_unpartitioned', 'pending']),
  order_status: z.string().nullable(),
  service_days: z.number().int().nonnegative().nullable(),
  service_hours_per_day: z.number().nonnegative().nullable(),
  planned_start_date: DateSchema.nullable(),
  planned_end_date: DateSchema.nullable(),
  district: z.string().nullable(),
  data_quality_codes: z.array(z.string()),
  week_start_date: DateSchema.nullable(),
  week_end_date: DateSchema.nullable(),
  week_label: z.string(),
});

export const WeeklyOperationsServiceRowSchema = z.strictObject({
  assignment_id: z.number().int().positive(),
  case_no: z.string().min(1),
  client_name: z.string().min(1),
  staff_name: z.string().min(1),
  service_start_date: DateSchema.nullable(),
  service_end_date: DateSchema.nullable(),
  period_start_date: DateSchema,
  period_end_date: DateSchema,
  service_hours_per_day: z.number().positive().nullable(),
  weekly_work_days: z.number().int().nonnegative(),
  weekly_hours: z.number().positive().nullable(),
  order_status: z.string().min(1),
  completed: z.boolean(),
  data_quality_codes: z.array(z.string()),
});

export const WeeklyOperationsDataQualityIssueSchema = z.strictObject({
  code: z.string().min(1),
  field: z.string().min(1),
  row_count: z.number().int().nonnegative(),
  message: z.string().min(1),
});

export const WeeklyOperationsSubsidyRowSchema = z.strictObject({
  ...SubsidyReportRowSchema.shape,
  application_roc_year: z.number().int().positive().nullable(),
  claim_period_label: z.string(),
  reconciliation_status: z.string(),
  notes: z.string(),
});

export const WeeklyOperationsSubsidyPartitionSchema = z.strictObject({
  citizen_kind: z.enum(['general', 'subsidized']),
  row_count: z.number().int().nonnegative(),
  total_amount_ntd: z.number().int().nonnegative(),
  rows: z.array(WeeklyOperationsSubsidyRowSchema),
});

export const WeeklyReportMetricSchema = z.strictObject({
  week_start_date: DateSchema,
  week_end_date: DateSchema,
  promotion_count: NonNegativeNullableIntegerSchema,
  inquiry_count: NonNegativeNullableIntegerSchema,
  updated_at: z.string().datetime({ offset: true }).nullable(),
});

export const WeeklyOperationsReportSchema = z.strictObject({
  schema_version: z.literal(WEEKLY_REPORT_SCHEMA_VERSION),
  period: WeeklyOperationsReportPeriodSchema,
  generated_at: z.string().datetime({ offset: true }),
  source_revision: z.string().min(1),
  summary: WeeklyOperationsReportSummarySchema,
  case_rows: z.array(WeeklyOperationsCaseRowSchema),
  subsidy_partitions: z.array(WeeklyOperationsSubsidyPartitionSchema).length(2),
  service_rows: z.array(WeeklyOperationsServiceRowSchema),
  weekly_metrics: z.array(WeeklyReportMetricSchema),
  annual_totals: z.array(WeeklyReportCaseTotalsSchema),
  monthly_subtotals: z.array(WeeklyReportCaseTotalsSchema),
  data_quality_issues: z.array(WeeklyOperationsDataQualityIssueSchema),
});

// 舊後端會忽略新的 schema_version query 並回 v3；兩版各自嚴格驗證，
// 不把缺少 v4 統計欄位的異常回應當成合法舊版。
export const WeeklyOperationsReportV3Schema = WeeklyOperationsReportSchema.omit({
  annual_totals: true,
  monthly_subtotals: true,
}).extend({ schema_version: z.literal('operations-report.v3') });

export const WeeklyOperationsReportResponseSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: z.discriminatedUnion('schema_version', [
    WeeklyOperationsReportV3Schema,
    WeeklyOperationsReportSchema,
  ]),
  error: z.string().nullable().optional(),
});

export type WeeklyOperationsReport = z.infer<typeof WeeklyOperationsReportSchema>;
export type WeeklyOperationsReportData = z.infer<typeof WeeklyOperationsReportResponseSchema>['data'];
