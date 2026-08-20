/**
 * File: order_query_schemas.ts
 * Description: 嚴格解碼八個核准的 Orders 唯讀查詢回應。
 */
import { z } from 'zod';

const DateOnlySchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const TimeOnlySchema = z.string().regex(/^\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?$/);
const Sha256Schema = z.string().regex(/^[0-9a-f]{64}$/);

export const OrderSummaryItemSchema = z.strictObject({
  case_no: z.string().min(1),
  client_name: z.string(),
  order_status: z.string(),
  staff_name: z.string().nullable(),
  identity_status: z.string().nullable(),
  start_date: DateOnlySchema.nullable(),
  end_date: DateOnlySchema.nullable(),
  actual_start_date: DateOnlySchema.nullable(),
  actual_end_date: DateOnlySchema.nullable(),
  service_days: z.number().int().positive().nullable(),
  total_employer_self_pay_payable: z.number().int().nonnegative().nullable(),
});
export type OrderSummaryItem = z.infer<typeof OrderSummaryItemSchema>;

export const OrderSummaryPageSchema = z.strictObject({
  items: z.array(OrderSummaryItemSchema),
  next_cursor: z.string().nullable(),
  etag: Sha256Schema,
});
type DecodedOrderSummaryPage = z.infer<typeof OrderSummaryPageSchema>;
export type OrderSummaryPage = DecodedOrderSummaryPage & {
  /** Compatibility-only read used by the not-yet-migrated OrderTracker. */
  readonly total_count?: never;
};

export const OrderDetailSchema = z.strictObject({
  case_no: z.string().min(1),
  client_id: z.number().int().positive(),
  staff_id: z.number().int().positive().nullable(),
  client_name: z.string(),
  staff_name: z.string().nullable(),
  order_status: z.string(),
  identity_status: z.string().nullable(),
  cancel_reason: z.string().nullable(),
  line_group_id: z.string().nullable(),
  contract_identity: z.string().nullable(),
  actual_start_date: DateOnlySchema.nullable(),
  actual_end_date: DateOnlySchema.nullable(),
  deposit_date: DateOnlySchema.nullable(),
  start_date: DateOnlySchema.nullable(),
  end_date: DateOnlySchema.nullable(),
  service_days: z.number().int().nonnegative(),
  service_hours_per_day: z.number().int().nonnegative(),
  deposit_service_days: z.number().int().nonnegative().nullable(),
  floor_fee: z.number().int().nonnegative(),
  custom_rest_dates: z.string().nullable(),
});
export type OrderDetail = z.infer<typeof OrderDetailSchema>;

export const OrderCalendarDetailSchema = z.strictObject({
  case_no: z.string().min(1),
  service_mode: z.enum(['週休1日', '週休2日', '連續服務']),
});
export type OrderCalendarDetail = z.infer<typeof OrderCalendarDetailSchema>;

export const ServiceTimeTermsSchema = z.strictObject({
  start_time: TimeOnlySchema.nullable(),
  end_time: TimeOnlySchema.nullable(),
  end_day_offset: z.number().int().min(0).max(1).nullable(),
});
export type ServiceTimeTerms = z.infer<typeof ServiceTimeTermsSchema>;

export const OrderTermsDetailSchema = z.strictObject({
  planned_start_date: DateOnlySchema,
  service_days: z.number().int().positive(),
  service_hours_per_day: z.number().int().positive(),
  requires_cooking: z.boolean().nullable(),
  floor_fee_ntd: z.number().int().nonnegative(),
  service_time: ServiceTimeTermsSchema,
});
export type OrderTermsDetail = z.infer<typeof OrderTermsDetailSchema>;

export const OrderTermsSchema = z.strictObject({
  case_no: z.string().min(1),
  order_version: z.number().int().nonnegative(),
  scheduling_version: z.number().int().nonnegative(),
  scheduling_generation: z.number().int().nonnegative(),
  client_finance_version: z.number().int().nonnegative(),
  payroll_version: z.number().int().nonnegative(),
  service_data_locked: z.boolean(),
  terms: OrderTermsDetailSchema,
});
export type OrderTerms = z.infer<typeof OrderTermsSchema>;

export const FormManagementContextSchema = z.strictObject({
  case_no: z.string().min(1),
  service_time: z.string().nullable(),
  service_type: z.string().nullable(),
  delivery_type: z.string().nullable(),
  residence_type: z.string().nullable(),
  city: z.string().nullable(),
  identity_status: z.string().nullable(),
});
export type FormManagementContext = z.infer<typeof FormManagementContextSchema>;

export const ActualStartSchema = z.strictObject({
  case_no: z.string().min(1),
  current_actual_start_date: DateOnlySchema.nullable(),
  planned_start_date: DateOnlySchema,
  service_data_locked: z.boolean(),
  order_version: z.number().int().nonnegative(),
  scheduling_version: z.number().int().nonnegative(),
  scheduling_generation: z.number().int().nonnegative(),
  client_finance_version: z.number().int().nonnegative(),
  payroll_version: z.number().int().nonnegative(),
});
export type ActualStart = z.infer<typeof ActualStartSchema>;

export const ContractCompletionSchema = z.strictObject({
  case_no: z.string().min(1),
  order_version: z.number().int().nonnegative(),
  client_finance_version: z.number().int().nonnegative(),
  contract_identity: z.string().nullable(),
  contract_completed: z.boolean(),
  lifecycle_status: z.string(),
  deposit_settled: z.boolean(),
  service_time_terms_complete: z.boolean(),
  completion_available: z.boolean(),
  domain_blockers: z.array(z.string()),
});
export type ContractCompletion = z.infer<typeof ContractCompletionSchema>;

export const AssignmentSegmentSchema = z.strictObject({
  assignment_id: z.number().int().positive().nullable(),
  candidate_key: z.string().nullable(),
  staff_id: z.number().int().positive(),
  sequence: z.number().int().positive(),
  assigned_start_date: DateOnlySchema,
  assigned_end_date: DateOnlySchema,
  official_service_dates: z.array(DateOnlySchema),
  actual_hours: z.number().int().nonnegative().nullable(),
  lineage_source_assignment_ids: z.array(z.number().int()),
});
export type AssignmentSegment = z.infer<typeof AssignmentSegmentSchema>;

export const AssignmentPlanSchema = z.strictObject({
  case_no: z.string().min(1),
  order_version: z.number().int().nonnegative(),
  scheduling_version: z.number().int().nonnegative(),
  scheduling_generation: z.number().int().nonnegative(),
  client_finance_version: z.number().int().nonnegative(),
  payroll_version: z.number().int().nonnegative(),
  contracted_service_days: z.number().int().positive(),
  service_hours_per_day: z.number().int().positive(),
  service_started: z.boolean(),
  assignments: z.array(AssignmentSegmentSchema),
});
export type AssignmentPlan = z.infer<typeof AssignmentPlanSchema>;

/** Compatibility-only denied payloads for OrderTracker; no decoder or client method exists. */

export function createOrderQueryEnvelopeSchema<T extends z.ZodTypeAny>(dataSchema: T) {
  return z.strictObject({
    success: z.boolean(),
    message: z.string(),
    data: dataSchema,
    error: z.string().nullable(),
  });
}
