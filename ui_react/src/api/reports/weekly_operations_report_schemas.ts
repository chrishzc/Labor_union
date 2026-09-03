/**
 * File: weekly_operations_report_schemas.ts
 * Description: 定義營運週報三分頁、期間、彙總與資料品質問題的 strict server-redacted view。
 */
import { z } from 'zod';
import { SubsidyReportPartitionSchema } from './subsidy_report_query_schemas';

const DateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const NonNegativeNullableIntegerSchema = z.number().int().nonnegative().nullable();

export const WeeklyOperationsReportPeriodSchema = z.strictObject({
  start_date: DateSchema,
  end_date: DateSchema,
  timezone: z.literal('Asia/Taipei'),
  period_label: z.string().min(1),
});

export const WeeklyOperationsReportSummarySchema = z.strictObject({
  promotion_count: NonNegativeNullableIntegerSchema,
  inquiry_count: NonNegativeNullableIntegerSchema,
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

export const WeeklyOperationsCaseRowSchema = z.strictObject({
  case_no: z.string().min(1),
  applicant_name_masked: z.string().min(1),
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
});

export const WeeklyOperationsServiceRowSchema = z.strictObject({
  assignment_id: z.number().int().positive(),
  case_no: z.string().min(1),
  client_name_masked: z.string().min(1),
  staff_name_masked: z.string().min(1),
  service_start_date: DateSchema,
  service_end_date: DateSchema,
  period_start_date: DateSchema,
  period_end_date: DateSchema,
  service_hours_per_day: z.number().nonnegative(),
  weekly_work_days: z.number().int().nonnegative(),
  weekly_hours: z.number().nonnegative(),
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

export const WeeklyOperationsReportSchema = z.strictObject({
  schema_version: z.literal('operations-report.v2'),
  period: WeeklyOperationsReportPeriodSchema,
  generated_at: z.string().datetime({ offset: true }),
  source_revision: z.string().min(1),
  summary: WeeklyOperationsReportSummarySchema,
  case_rows: z.array(WeeklyOperationsCaseRowSchema),
  subsidy_partitions: z.array(SubsidyReportPartitionSchema).length(2),
  service_rows: z.array(WeeklyOperationsServiceRowSchema),
  data_quality_issues: z.array(WeeklyOperationsDataQualityIssueSchema),
});

export const WeeklyOperationsReportResponseSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: WeeklyOperationsReportSchema,
  error: z.string().nullable().optional(),
});

export type WeeklyOperationsReport = z.infer<typeof WeeklyOperationsReportSchema>;
