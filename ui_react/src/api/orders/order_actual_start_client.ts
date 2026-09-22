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
const LifecycleStatusSchema = z.enum([
  '待補件',
  '洽談中',
  '訂單成立',
  '服務中',
  '訂單完成',
  '訂單取消',
  '歷史訂單－未服務',
  '歷史訂單－服務中',
  '歷史訂單－服務完成',
  '歷史訂單－帳務完成',
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

const ActualStartDateOnlyApplyPayloadSchema = z.strictObject({
  operation: z.literal('date_only'),
  new_actual_start_date: IsoDateSchema,
  expected_order_version: NonnegativeIntegerSchema,
  preview_fingerprint: FingerprintSchema,
});

const ActualStartRescheduleApplyPayloadSchema = z.strictObject({
  operation: z.literal('reschedule'),
  new_actual_start_date: IsoDateSchema,
  expected_order_version: NonnegativeIntegerSchema,
  expected_scheduling_version: NonnegativeIntegerSchema,
  preview_fingerprint: FingerprintSchema,
  reason: z.string().refine(
    (value) => value.trim().length >= 1 && value.length <= 500,
    { message: '原因必須為 1 至 500 字元且不可為純空白' },
  ),
});

export const ActualStartApplyPayloadSchema = z.discriminatedUnion('operation', [
  ActualStartDateOnlyApplyPayloadSchema,
  ActualStartRescheduleApplyPayloadSchema,
]);

const ActualStartDateOnlyPreviewSchema = z.strictObject({
  operation: z.literal('date_only'),
  case_no: z.string().min(1),
  before_actual_start_date: IsoDateSchema.nullable(),
  after_actual_start_date: IsoDateSchema,
  order_version: NonnegativeIntegerSchema,
  scheduling_version: NonnegativeIntegerSchema.nullable(),
  scheduling_generation: NonnegativeIntegerSchema.nullable(),
  client_finance_version: NonnegativeIntegerSchema.nullable(),
  payroll_version: NonnegativeIntegerSchema.nullable(),
  preview_fingerprint: FingerprintSchema,
});

const ActualStartReschedulePreviewSchema = z.strictObject({
  operation: z.literal('reschedule'),
  before_actual_start_date: IsoDateSchema.nullable(),
  after_actual_start_date: IsoDateSchema,
  actual_end_date: IsoDateSchema,
  order_version: NonnegativeIntegerSchema,
  scheduling_version: NonnegativeIntegerSchema,
  scheduling_generation: NonnegativeIntegerSchema,
  actual_start: ActualStartCandidateSchema,
  scheduling: SchedulingGenerationSchema,
  lifecycle_impact: LifecycleImpactSchema,
  preview_fingerprint: FingerprintSchema,
});

export const ActualStartPreviewSchema = z.discriminatedUnion('operation', [
  ActualStartDateOnlyPreviewSchema,
  ActualStartReschedulePreviewSchema,
]);

const ActualStartDateOnlyResultSchema = z.strictObject({
  operation: z.literal('date_only'),
  case_no: z.string().min(1),
  actual_start_date: IsoDateSchema,
  order_version: NonnegativeIntegerSchema,
  scheduling_version: NonnegativeIntegerSchema.nullable(),
  scheduling_generation: NonnegativeIntegerSchema.nullable(),
  client_finance_version: NonnegativeIntegerSchema.nullable(),
  payroll_version: NonnegativeIntegerSchema.nullable(),
  preview_fingerprint: FingerprintSchema,
  changed: z.boolean(),
});

const ActualStartRescheduleReceiptSchema = z.strictObject({
  operation: z.literal('reschedule'),
  case_no: z.string().min(1),
  order_version: NonnegativeIntegerSchema,
  scheduling_version: NonnegativeIntegerSchema,
  scheduling_generation: NonnegativeIntegerSchema,
  lifecycle_status: LifecycleStatusSchema,
  service_data_lock_formed: z.boolean(),
  cancelled_assignment_ids: z.array(PositiveIntegerSchema),
  created_assignment_keys: z.array(z.string().min(1)),
  official_service_day_count: NonnegativeIntegerSchema,
  official_service_hours: NonnegativeIntegerSchema,
  preview_fingerprint: FingerprintSchema,
});

export const ActualStartReceiptSchema = z.discriminatedUnion('operation', [
  ActualStartDateOnlyResultSchema,
  ActualStartRescheduleReceiptSchema,
]);

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
