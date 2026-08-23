/**
 * File: order_actual_start_client.ts
 * Description: 提供實際開工日 Preview／Apply 的 closed Zod 契約、動態授權及冪等標頭。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';
import { decodeMutationError } from './order_mutation_errors';

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;

function isCanonicalIsoDate(value: string): boolean {
  if (!ISO_DATE_PATTERN.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  const candidate = new Date(Date.UTC(year, month - 1, day));
  return (
    candidate.getUTCFullYear() === year &&
    candidate.getUTCMonth() === month - 1 &&
    candidate.getUTCDate() === day
  );
}

const IsoDateSchema = z.string().refine(isCanonicalIsoDate, {
  message: '預期有效的 ISO 日期 YYYY-MM-DD',
});
const IsoDateTimeSchema = z.string().refine(
  (value) => /^\d{4}-\d{2}-\d{2}T/.test(value) && !Number.isNaN(Date.parse(value)),
  { message: '預期有效的 ISO 日期時間' },
);
const FingerprintSchema = z.string().regex(SHA256_PATTERN);
const NonnegativeIntegerSchema = z.number().int().nonnegative();
const PositiveIntegerSchema = z.number().int().positive();
const MoneySchema = z.strictObject({ amount: z.number().int() });
const LifecycleStatusSchema = z.enum([
  '待補件',
  '洽談中',
  '訂單成立',
  '服務中',
  '訂單完成',
  '訂單取消',
]);

const ActualStartAssignmentSchema = z.strictObject({
  source_assignment_id: PositiveIntegerSchema,
  staff_id: PositiveIntegerSchema,
  sequence: PositiveIntegerSchema,
  assigned_start_date: IsoDateSchema,
  assigned_end_date: IsoDateSchema,
  service_dates: z.array(IsoDateSchema).min(1),
  actual_hours: PositiveIntegerSchema,
});

const ActualStartCandidateSchema = z.strictObject({
  case_no: z.string().min(1),
  kind: z.enum(['first_confirmation', 'correction']),
  expected_order_version: NonnegativeIntegerSchema,
  expected_scheduling_version: NonnegativeIntegerSchema,
  source_generation_number: NonnegativeIntegerSchema,
  original_actual_start_date: IsoDateSchema.nullable(),
  original_scheduling_root_date: IsoDateSchema,
  new_actual_start_date: IsoDateSchema,
  shift_days: z.number().int(),
  assignments: z.array(ActualStartAssignmentSchema).min(1),
  official_service_dates: z.array(IsoDateSchema).min(1),
  actual_end_date: IsoDateSchema,
  fingerprint: FingerprintSchema,
});

const SchedulingAssignmentSchema = z.strictObject({
  candidate_key: z.string().min(1),
  source_assignment_id: PositiveIntegerSchema.nullable(),
  staff_id: PositiveIntegerSchema,
  sequence: PositiveIntegerSchema,
  assigned_start_date: IsoDateSchema,
  assigned_end_date: IsoDateSchema,
  service_dates: z.array(IsoDateSchema).min(1),
  actual_hours: PositiveIntegerSchema,
  lineage_source_assignment_ids: z.array(PositiveIntegerSchema),
  double_pay_dates: z.array(IsoDateSchema),
});

const SchedulingGenerationSchema = z.strictObject({
  case_no: z.string().min(1),
  generation_number: PositiveIntegerSchema,
  expected_aggregate_version: NonnegativeIntegerSchema,
  resulting_aggregate_version: NonnegativeIntegerSchema,
  cancelled_assignment_ids: z.array(PositiveIntegerSchema),
  assignments: z.array(SchedulingAssignmentSchema).min(1),
  buffers: z.array(z.strictObject({
    candidate_key: z.string().min(1),
    staff_id: PositiveIntegerSchema,
    dates: z.array(IsoDateSchema),
    active: z.boolean(),
  })),
});

const PaymentStageSchema = z.enum(['deposit', 'first', 'second']);
const ClientFinanceImpactSchema = z.strictObject({
  case_no: z.string().min(1),
  expected_account_version: NonnegativeIntegerSchema,
  resulting_account_version: NonnegativeIntegerSchema,
  stage_plans: z.array(z.strictObject({
    payment_stage: PaymentStageSchema,
    service_dates: z.array(IsoDateSchema),
    amount: MoneySchema,
    due_date: IsoDateSchema.nullable(),
  })),
  actions: z.array(z.strictObject({
    action: z.enum([
      'create_stage',
      'replace_open',
      'cancel_open',
      'create_adjustment',
      'create_refund',
      'unchanged',
    ]),
    payment_stage: PaymentStageSchema,
    obligation_identity: z.string().min(1),
    before_amount: MoneySchema,
    after_amount: MoneySchema,
    obligation_amount: MoneySchema,
    before_due_date: IsoDateSchema.nullable(),
    after_due_date: IsoDateSchema.nullable(),
    source_obligation_identity: z.string().min(1).nullable(),
  })),
  settlement: z.strictObject({
    deposit_settled: z.boolean(),
    all_formal_obligations_settled: z.boolean(),
    fingerprint: FingerprintSchema,
  }),
  blockers: z.array(z.string()),
  fingerprint: FingerprintSchema,
});

const PayrollAssignmentSchema = z.strictObject({
  assignment_identity: z.string().min(1),
  staff_id: PositiveIntegerSchema,
  official_service_day_count: PositiveIntegerSchema,
  actual_hours: PositiveIntegerSchema,
  double_pay_hours: NonnegativeIntegerSchema,
  hourly_rate: MoneySchema,
  service_salary: MoneySchema,
  floor_fee_allocated: MoneySchema,
  effective_adjustments: MoneySchema,
  total_payable: MoneySchema,
});

const PayrollImpactSchema = z.strictObject({
  case_no: z.string().min(1),
  expected_payroll_version: NonnegativeIntegerSchema,
  resulting_payroll_version: NonnegativeIntegerSchema,
  payroll: z.strictObject({
    assignments: z.array(PayrollAssignmentSchema),
    earned_floor_fee: MoneySchema,
    total_payable: MoneySchema,
    fingerprint: FingerprintSchema,
  }),
  carried_rate_snapshots: z.array(z.strictObject({
    assignment_identity: z.string().min(1),
    policy_version: z.string().min(1),
    policy_kind: z.enum(['citizen', 'subsidized_citizen', 'non_citizen']),
    hourly_rate: MoneySchema,
  })),
  actions: z.array(z.strictObject({
    action: z.enum([
      'establish',
      'close_unpaid',
      'append_frozen_difference',
      'keep_frozen',
    ]),
    obligation_identity: z.string().min(1),
    source_obligation_identity: z.string().min(1).nullable(),
    source_assignment_id: PositiveIntegerSchema.nullable(),
    candidate_assignment_key: z.string().min(1).nullable(),
    staff_id: PositiveIntegerSchema,
    obligation_kind: z.enum(['service_pay', 'adjustment', 'reversal']),
    direction: z.enum(['payable_to_staff', 'receivable_from_staff']),
    amount: MoneySchema,
    due_date: IsoDateSchema.nullable(),
  })),
  blockers: z.array(z.string()),
  fingerprint: FingerprintSchema,
});

const LifecycleImpactSchema = z.strictObject({
  case_no: z.string().min(1),
  before_status: LifecycleStatusSchema,
  after_status: LifecycleStatusSchema,
  actual_end_date: IsoDateSchema,
  completion_instant: IsoDateTimeSchema,
  business_date: IsoDateSchema,
  service_completion_reached: z.boolean(),
  service_data_lock_was_present: z.boolean(),
  service_data_lock_should_exist: z.boolean(),
  alert_codes: z.array(z.string()),
  fingerprint: FingerprintSchema,
});

export const ActualStartPreviewPayloadSchema = z.strictObject({
  new_actual_start_date: IsoDateSchema,
});

export const ActualStartApplyPayloadSchema = z.strictObject({
  new_actual_start_date: IsoDateSchema,
  expected_order_version: NonnegativeIntegerSchema,
  expected_scheduling_version: NonnegativeIntegerSchema,
  expected_client_finance_version: NonnegativeIntegerSchema,
  expected_payroll_version: NonnegativeIntegerSchema,
  preview_fingerprint: FingerprintSchema,
  reason: z.string().refine(
    (value) => value.trim().length >= 1 && value.length <= 500,
    { message: '原因必須為 1 至 500 字元且不可為純空白' },
  ),
});

export const ActualStartPreviewSchema = z.strictObject({
  before_actual_start_date: IsoDateSchema.nullable(),
  after_actual_start_date: IsoDateSchema,
  actual_end_date: IsoDateSchema,
  order_version: NonnegativeIntegerSchema,
  scheduling_version: NonnegativeIntegerSchema,
  scheduling_generation: NonnegativeIntegerSchema,
  client_finance_version: NonnegativeIntegerSchema,
  payroll_version: NonnegativeIntegerSchema,
  actual_start: ActualStartCandidateSchema,
  scheduling: SchedulingGenerationSchema,
  client_finance_impact: ClientFinanceImpactSchema,
  payroll_impact: PayrollImpactSchema,
  lifecycle_impact: LifecycleImpactSchema,
  preview_fingerprint: FingerprintSchema,
});

export const ActualStartReceiptSchema = z.strictObject({
  case_no: z.string().min(1),
  order_version: NonnegativeIntegerSchema,
  scheduling_version: NonnegativeIntegerSchema,
  scheduling_generation: NonnegativeIntegerSchema,
  client_finance_version: NonnegativeIntegerSchema,
  payroll_version: NonnegativeIntegerSchema,
  lifecycle_status: LifecycleStatusSchema,
  service_data_lock_formed: z.boolean(),
  cancelled_assignment_ids: z.array(PositiveIntegerSchema),
  created_assignment_keys: z.array(z.string().min(1)),
  official_service_day_count: NonnegativeIntegerSchema,
  official_service_hours: NonnegativeIntegerSchema,
  preview_fingerprint: FingerprintSchema,
});

const envelope = <T extends z.ZodTypeAny>(schema: T) => z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: schema.nullable(),
  error: z.string().nullable(),
});

export type ActualStartPreviewPayload = z.infer<typeof ActualStartPreviewPayloadSchema>;
export type ActualStartApplyPayload = z.infer<typeof ActualStartApplyPayloadSchema>;
export type ActualStartPreview = z.infer<typeof ActualStartPreviewSchema>;
export type ActualStartReceipt = z.infer<typeof ActualStartReceiptSchema>;

export interface ActualStartRequestOptions {
  correlationId?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  headers?: Record<string, string>;
}

export interface ActualStartApplyOptions extends ActualStartRequestOptions {
  idempotencyKey: string;
}

function requireHeaderValue(value: unknown, label: string): string {
  if (typeof value !== 'string') throw new Error(`${label} 必須為字串。`);
  const canonical = value.trim();
  if (canonical.length < 1 || canonical.length > 191) {
    throw new Error(`${label} 長度必須介於 1 至 191 字元。`);
  }
  return canonical;
}

function requireCaseNo(caseNo: string): string {
  const canonical = caseNo.trim();
  if (canonical.length < 1 || canonical.length > 50) {
    throw new Error('案件編號長度必須介於 1 至 50 字元。');
  }
  return canonical;
}

function requestOptions(
  options: ActualStartRequestOptions | undefined,
  headers: Record<string, string>,
): RequestOptions {
  const token = sessionClient.getToken();
  return {
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
    headers: { ...options?.headers, ...headers },
    ...(token ? { token } : {}),
  };
}

function decode<T extends z.ZodTypeAny>(schema: T, raw: unknown): z.output<T> {
  const response = decodePayload(envelope(schema), raw);
  if (!response.success) {
    throw new ApiHttpError(
      400,
      'ACTUAL_START_FAILED',
      response.error ?? response.message,
      false,
      raw,
    );
  }
  if (response.data === null) {
    throw new ApiDecodeError('實際開工日成功信封缺少 data 本體', [], raw);
  }
  return response.data;
}

export const orderActualStartClient = {
  async preview(
    caseNo: string,
    payload: ActualStartPreviewPayload,
    options?: ActualStartRequestOptions,
  ): Promise<ActualStartPreview> {
    const canonicalCaseNo = requireCaseNo(caseNo);
    const body = ActualStartPreviewPayloadSchema.parse(payload);
    const endpoint = `/api/v1/orders/${encodeURIComponent(canonicalCaseNo)}/actual-start/preview`;
    const correlationId = requireHeaderValue(
      options?.correlationId ?? `orders-actual-start-preview-${canonicalCaseNo}-${Date.now()}`,
      'X-Correlation-ID',
    );
    try {
      return decode(
        ActualStartPreviewSchema,
        await transport.post(endpoint, body, requestOptions(options, {
          'X-Correlation-ID': correlationId,
        })),
      );
    } catch (error) {
      throw decodeMutationError(error, { caseNo: canonicalCaseNo, endpoint });
    }
  },

  async apply(
    caseNo: string,
    payload: ActualStartApplyPayload,
    options: ActualStartApplyOptions,
  ): Promise<ActualStartReceipt> {
    const canonicalCaseNo = requireCaseNo(caseNo);
    const body = ActualStartApplyPayloadSchema.parse(payload);
    const endpoint = `/api/v1/orders/${encodeURIComponent(canonicalCaseNo)}/actual-start/apply`;
    const correlationId = requireHeaderValue(
      options?.correlationId ?? `orders-actual-start-apply-${canonicalCaseNo}-${Date.now()}`,
      'X-Correlation-ID',
    );
    const idempotencyKey = requireHeaderValue(options?.idempotencyKey, 'Idempotency-Key');
    try {
      return decode(
        ActualStartReceiptSchema,
        await transport.post(endpoint, body, requestOptions(options, {
          'X-Correlation-ID': correlationId,
          'Idempotency-Key': idempotencyKey,
        })),
      );
    } catch (error) {
      throw decodeMutationError(error, { caseNo: canonicalCaseNo, endpoint });
    }
  },
};
