/**
 * File: order_cancellation_client.ts
 * Description: 提供 Orders Cancellation 嚴格 typed Query／Preview／Apply client。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';

const DateOnlySchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
export const ServiceDaySchema = z.strictObject({
  service_date: DateOnlySchema,
  staff_id: z.number().int().positive(),
  reason: z.string().min(1).max(500).nullable(),
});
const MoneySchema = z.strictObject({ amount: z.number().int().nonnegative() });
const SchedulingAssignmentSchema = z.strictObject({
  candidate_key: z.string().min(1),
  source_assignment_id: z.number().int().positive().nullable(),
  staff_id: z.number().int().positive(),
  sequence: z.number().int().positive(),
  assigned_start_date: DateOnlySchema,
  assigned_end_date: DateOnlySchema,
  service_dates: z.array(DateOnlySchema),
  actual_hours: z.number().int().nonnegative(),
  lineage_source_assignment_ids: z.array(z.number().int().positive()),
  double_pay_dates: z.array(DateOnlySchema),
});
const SchedulingBufferSchema = z.strictObject({
  candidate_key: z.string().min(1),
  staff_id: z.number().int().positive(),
  dates: z.array(DateOnlySchema),
  active: z.boolean(),
});
const SchedulingImpactSchema = z.strictObject({
  case_no: z.string().min(1),
  generation_number: z.number().int().nonnegative(),
  expected_aggregate_version: z.number().int().nonnegative(),
  resulting_aggregate_version: z.number().int().nonnegative(),
  cancelled_assignment_ids: z.array(z.number().int().positive()),
  assignments: z.array(SchedulingAssignmentSchema),
  buffers: z.array(SchedulingBufferSchema),
});
const ClientStagePlanSchema = z.strictObject({
  payment_stage: z.string().min(1),
  service_dates: z.array(DateOnlySchema),
  amount: MoneySchema,
  due_date: DateOnlySchema.nullable(),
});
export const ClientFinanceDirectionSchema = z.enum([
  'refund_due',
  'additional_charge_due',
  'no_finance_change',
]);
const ClientObligationActionSchema = z.strictObject({
  action: z.string().min(1),
  payment_stage: z.string().min(1),
  obligation_identity: z.string().min(1),
  before_amount: MoneySchema,
  after_amount: MoneySchema,
  obligation_amount: MoneySchema,
  before_due_date: DateOnlySchema.nullable(),
  after_due_date: DateOnlySchema.nullable(),
  source_obligation_identity: z.string().min(1).nullable(),
  direction: ClientFinanceDirectionSchema,
  direction_amount_ntd: z.number().int().nonnegative(),
}).superRefine((value, context) => {
  if (value.direction === 'no_finance_change' && value.direction_amount_ntd !== 0) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['direction_amount_ntd'],
      message: 'no_finance_change direction amount must be zero',
    });
  } else if (value.direction !== 'no_finance_change' && value.direction_amount_ntd <= 0) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['direction_amount_ntd'],
      message: 'financial direction amount must be positive',
    });
  }
});
const ClientSettlementSchema = z.strictObject({
  deposit_settled: z.boolean(),
  all_formal_obligations_settled: z.boolean(),
  fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});
const ClientFinanceImpactSchema = z.strictObject({
  case_no: z.string().min(1),
  expected_account_version: z.number().int().nonnegative(),
  resulting_account_version: z.number().int().nonnegative(),
  stage_plans: z.array(ClientStagePlanSchema),
  actions: z.array(ClientObligationActionSchema),
  settlement: ClientSettlementSchema,
  blockers: z.array(z.string()),
  fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});
const PayrollAssignmentSchema = z.strictObject({
  assignment_identity: z.string().min(1),
  staff_id: z.number().int().positive(),
  official_service_day_count: z.number().int().nonnegative(),
  actual_hours: z.number().int().nonnegative(),
  double_pay_hours: z.number().int().nonnegative(),
  hourly_rate: MoneySchema,
  service_salary: MoneySchema,
  floor_fee_allocated: MoneySchema,
  effective_adjustments: MoneySchema,
  total_payable: MoneySchema,
});
const PayrollCandidateSchema = z.strictObject({
  assignments: z.array(PayrollAssignmentSchema),
  earned_floor_fee: MoneySchema,
  total_payable: MoneySchema,
  fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});
const PayrollRateSnapshotSchema = z.strictObject({
  assignment_identity: z.string().min(1),
  policy_version: z.string().min(1),
  policy_kind: z.string().min(1),
  hourly_rate: MoneySchema,
});
const PayrollActionSchema = z.strictObject({
  action: z.string().min(1),
  obligation_identity: z.string().min(1),
  source_obligation_identity: z.string().min(1).nullable(),
  source_assignment_id: z.number().int().positive().nullable(),
  candidate_assignment_key: z.string().min(1).nullable(),
  staff_id: z.number().int().positive(),
  obligation_kind: z.string().min(1),
  direction: z.string().min(1),
  amount: MoneySchema,
  due_date: DateOnlySchema.nullable(),
});
const PayrollSpecialPayEventSchema = z.strictObject({
  assignment_identity: z.string().min(1),
  assignment_sequence: z.number().int().positive(),
  service_dates: z.array(DateOnlySchema),
});
const PayrollImpactSchema = z.strictObject({
  case_no: z.string().min(1),
  expected_payroll_version: z.number().int().nonnegative(),
  resulting_payroll_version: z.number().int().nonnegative(),
  payroll: PayrollCandidateSchema,
  carried_rate_snapshots: z.array(PayrollRateSnapshotSchema),
  actions: z.array(PayrollActionSchema),
  special_pay_events: z.array(PayrollSpecialPayEventSchema),
  blockers: z.array(z.string()),
  fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});
const LifecycleImpactSchema = z.strictObject({
  case_no: z.string().min(1),
  before_status: z.string().min(1),
  after_status: z.string().min(1),
  actual_end_date: DateOnlySchema.nullable(),
  cancellation_effective: z.boolean(),
  fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});
const CaregiverOptionSchema = z.strictObject({
  staff_id: z.number().int().positive(),
  display_name: z.string().min(1),
});

export const OrderCancellationQuerySchema = z.strictObject({
  case_no: z.string().min(1),
  lifecycle_status: z.string().min(1),
  actual_start_date: DateOnlySchema.nullable(),
  contracted_service_days: z.number().int().positive(),
  service_hours_per_day: z.number().int().positive(),
  service_started: z.boolean(),
  service_data_locked: z.boolean(),
  order_version: z.number().int().nonnegative(),
  scheduling_version: z.number().int().nonnegative(),
  scheduling_generation: z.number().int().nonnegative(),
  client_finance_version: z.number().int().nonnegative(),
  payroll_version: z.number().int().nonnegative(),
  confirmed_service_days: z.array(ServiceDaySchema),
  caregiver_options: z.array(CaregiverOptionSchema),
});

export const OrderCancellationPreviewSchema = z.strictObject({
  cancellation_date: DateOnlySchema,
  actual_end_date: DateOnlySchema.nullable(),
  confirmed_service_days: z.array(ServiceDaySchema),
  official_service_day_count: z.number().int().nonnegative(),
  official_service_hours: z.number().int().nonnegative(),
  order_version: z.number().int().nonnegative(),
  scheduling_version: z.number().int().nonnegative(),
  scheduling_generation: z.number().int().nonnegative(),
  client_finance_version: z.number().int().nonnegative(),
  payroll_version: z.number().int().nonnegative(),
  scheduling: SchedulingImpactSchema,
  client_finance_impact: ClientFinanceImpactSchema,
  payroll_impact: PayrollImpactSchema,
  lifecycle_impact: LifecycleImpactSchema,
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});

export const OrderCancellationReceiptSchema = z.strictObject({
  case_no: z.string().min(1),
  order_version: z.number().int().nonnegative(),
  scheduling_version: z.number().int().nonnegative(),
  scheduling_generation: z.number().int().nonnegative(),
  client_finance_version: z.number().int().nonnegative(),
  payroll_version: z.number().int().nonnegative(),
  lifecycle_status: z.string().min(1),
  actual_end_date: DateOnlySchema.nullable(),
  official_service_day_count: z.number().int().nonnegative(),
  official_service_hours: z.number().int().nonnegative(),
  cancelled_assignment_ids: z.array(z.number().int().positive()),
  created_assignment_keys: z.array(z.string().min(1)),
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});

export const OrderCancellationApplyPayloadSchema = z.strictObject({
  confirmed_service_days: z.array(ServiceDaySchema),
  expected_order_version: z.number().int().nonnegative(),
  expected_scheduling_version: z.number().int().nonnegative(),
  expected_client_finance_version: z.number().int().nonnegative(),
  expected_payroll_version: z.number().int().nonnegative(),
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
  reason: z.string().trim().min(1).max(500),
});

const envelope = <T extends z.ZodTypeAny>(schema: T) => z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: schema,
  error: z.string().nullable(),
});

export type OrderCancellationQuery = z.infer<typeof OrderCancellationQuerySchema>;
export type OrderCancellationPreview = z.infer<typeof OrderCancellationPreviewSchema>;
export type OrderCancellationReceipt = z.infer<typeof OrderCancellationReceiptSchema>;
export type OrderCancellationApplyPayload = z.infer<typeof OrderCancellationApplyPayloadSchema>;
export type ServiceDay = z.infer<typeof ServiceDaySchema>;

interface ApplyOptions {
  idempotencyKey: string;
  signal?: AbortSignal;
}

function options(signal?: AbortSignal, headers?: Record<string, string>): RequestOptions {
  return { signal, token: sessionClient.getToken(), headers };
}

function decode<T extends z.ZodTypeAny>(schema: T, raw: unknown): z.output<T> {
  const result = decodePayload(envelope(schema), raw);
  if (!result.success) throw new ApiHttpError(400, 'ORDER_CANCELLATION_FAILED', result.error ?? result.message, false, raw);
  return result.data;
}

export const orderCancellationClient = {
  async query(caseNo: string, signal?: AbortSignal): Promise<OrderCancellationQuery> {
    const raw = await transport.get(`/api/v1/orders/${encodeURIComponent(caseNo)}/cancellation`, options(signal));
    const result = decode(OrderCancellationQuerySchema, raw);
    if (result.case_no !== caseNo) throw new Error('訂單取消案件識別不一致。');
    return result;
  },
  async preview(caseNo: string, confirmedServiceDays: ServiceDay[], signal?: AbortSignal): Promise<OrderCancellationPreview> {
    const raw = await transport.post(
      `/api/v1/orders/${encodeURIComponent(caseNo)}/cancellation/preview`,
      { confirmed_service_days: confirmedServiceDays },
      options(signal, { 'X-Correlation-ID': `orders-cancellation-preview-${caseNo}-${Date.now()}` }),
    );
    return decode(OrderCancellationPreviewSchema, raw);
  },
  async receipt(caseNo: string, idempotencyKey: string, signal?: AbortSignal): Promise<OrderCancellationReceipt> {
    const key = idempotencyKey.trim();
    if (!key || key.length > 191) {
      throw new Error('Idempotency-Key 必須為 1 至 191 字元。');
    }
    const raw = await transport.get(
      `/api/v1/orders/${encodeURIComponent(caseNo)}/cancellation/receipt`,
      options(signal, { 'Idempotency-Key': key }),
    );
    const result = decode(OrderCancellationReceiptSchema, raw);
    if (result.case_no !== caseNo) throw new Error('訂單取消收據案件識別不一致。');
    return result;
  },
  async apply(
    caseNo: string,
    payload: OrderCancellationApplyPayload,
    source: ApplyOptions,
  ): Promise<OrderCancellationReceipt> {
    const idempotencyKey = source.idempotencyKey.trim();
    if (!idempotencyKey || idempotencyKey.length > 191) {
      throw new Error('Idempotency-Key 必須為 1 至 191 字元。');
    }
    const raw = await transport.post(
      `/api/v1/orders/${encodeURIComponent(caseNo)}/cancellation/apply`,
      OrderCancellationApplyPayloadSchema.parse(payload),
      options(source.signal, {
        'Idempotency-Key': idempotencyKey,
        'X-Correlation-ID': `orders-cancellation-apply-${caseNo}-${Date.now()}`,
      }),
    );
    const result = decode(OrderCancellationReceiptSchema, raw);
    if (result.case_no !== caseNo) throw new Error('訂單取消收據案件識別不一致。');
    return result;
  },
};
