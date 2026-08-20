/**
 * File: order_mutation_schemas.ts
 * Description: 嚴格對齊後端 Phase 2B Orders 安全變更端點之 Zod 解碼器，禁止寬鬆型別與預設值。
 */
import { z } from 'zod';

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const HEX_SHA256_PATTERN = /^[0-9a-f]{64}$/;

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

export const IsoDateSchema = z.string().refine(isCanonicalIsoDate, {
  message: '預期有效的 ISO 日期 YYYY-MM-DD',
});

export const FingerprintSchema = z.string().regex(HEX_SHA256_PATTERN, {
  message: '預期 64 位元小寫 Hex SHA-256 指紋',
});

export const ReasonSchema = z
  .string()
  .refine(
    (val) => {
      const trimmed = val.trim();
      return trimmed.length >= 1 && trimmed.length <= 500 && val.length <= 500;
    },
    {
      message: '原因必須為 1 至 500 字元且不可為純空白字串',
    }
  );

export function createOrderMutationEnvelopeSchema<T extends z.ZodTypeAny>(dataSchema: T) {
  return z
    .object({
      success: z.boolean(),
      message: z.string(),
      data: dataSchema.nullable(),
      error: z.string().nullable(),
    })
    .strict();
}

// ============================================================================
// 1. Confirmed Service Dates Schemas (api/schemas/service_date_confirmation.py)
// ============================================================================

export const ServiceWeekSchema = z
  .object({
    week_number: z.number().int().gt(0),
    period_start: IsoDateSchema,
    period_end: IsoDateSchema,
    service_dates: z.array(IsoDateSchema),
    service_day_count: z.number().int().gt(0),
  })
  .strict();

export type ServiceWeek = z.infer<typeof ServiceWeekSchema>;

export const ServiceDateConfirmationQueryViewSchema = z
  .object({
    case_no: z.string().min(1),
    order_version: z.number().int().min(0),
    scheduling_version: z.number().int().min(0),
    contracted_service_days: z.number().int().gt(0),
    suggested_dates: z.array(IsoDateSchema),
    selectable_dates: z.array(IsoDateSchema),
    current_version: z.number().int().min(1).nullable(),
    current_dates: z.array(IsoDateSchema),
  })
  .strict();

export type ServiceDateConfirmationQueryView = z.infer<
  typeof ServiceDateConfirmationQueryViewSchema
>;

export const ServiceDateConfirmationPreviewViewSchema = z
  .object({
    case_no: z.string().min(1),
    order_version: z.number().int().min(0),
    scheduling_version: z.number().int().min(0),
    current_version: z.number().int().min(1).nullable(),
    service_dates: z.array(IsoDateSchema),
    weeks: z.array(ServiceWeekSchema),
    preview_fingerprint: FingerprintSchema,
  })
  .strict();

export type ServiceDateConfirmationPreviewView = z.infer<
  typeof ServiceDateConfirmationPreviewViewSchema
>;

export const ServiceDateConfirmationReceiptViewSchema = z
  .object({
    case_no: z.string().min(1),
    confirmed_version: z.number().int().gt(0),
    order_version: z.number().int().min(0),
    scheduling_version: z.number().int().min(0),
    service_dates: z.array(IsoDateSchema),
    preview_fingerprint: FingerprintSchema,
  })
  .strict();

export type ServiceDateConfirmationReceiptView = z.infer<
  typeof ServiceDateConfirmationReceiptViewSchema
>;

export const ServiceDatePreviewPayloadSchema = z
  .object({
    service_dates: z.array(IsoDateSchema).min(1),
  })
  .strict();

export type ServiceDatePreviewPayload = z.infer<
  typeof ServiceDatePreviewPayloadSchema
>;

export const ServiceDateApplyPayloadSchema = z
  .object({
    service_dates: z.array(IsoDateSchema).min(1),
    expected_order_version: z.number().int().min(0),
    expected_scheduling_version: z.number().int().min(0),
    preview_fingerprint: FingerprintSchema,
    reason: ReasonSchema,
  })
  .strict();

export type ServiceDateApplyPayload = z.infer<
  typeof ServiceDateApplyPayloadSchema
>;

// ============================================================================
// 2. Controlled Order Reopen Schemas (api/schemas/order_reopen.py)
// ============================================================================

export const OrderReopenPreviewViewSchema = z
  .object({
    case_no: z.string().min(1),
    order_version: z.number().int().min(0),
    client_finance_version: z.number().int().min(0),
    payroll_version: z.number().int().min(0),
    cancellation_event_id: z.number().int().gt(0),
    before_status: z.literal('訂單取消'),
    after_status: z.enum(['洽談中', '訂單成立', '服務中']),
    requires_fresh_scheduling_preview: z.literal(true),
    restored_assignment_ids: z.array(z.number().int()).length(0),
    restored_schedule_ids: z.array(z.number().int()).length(0),
    restored_lock_ids: z.array(z.number().int()).length(0),
    preview_fingerprint: FingerprintSchema,
  })
  .strict();

export type OrderReopenPreviewView = z.infer<
  typeof OrderReopenPreviewViewSchema
>;

export const OrderReopenReceiptViewSchema = z
  .object({
    case_no: z.string().min(1),
    order_version: z.number().int().min(0),
    lifecycle_status: z.enum(['洽談中', '訂單成立', '服務中']),
    cancellation_event_id: z.number().int().gt(0),
    requires_fresh_scheduling_preview: z.literal(true),
    preview_fingerprint: FingerprintSchema,
  })
  .strict();

export type OrderReopenReceiptView = z.infer<
  typeof OrderReopenReceiptViewSchema
>;

export const OrderReopenApplyPayloadSchema = z
  .object({
    expected_order_version: z.number().int().min(0),
    expected_client_finance_version: z.number().int().min(0),
    expected_payroll_version: z.number().int().min(0),
    preview_fingerprint: FingerprintSchema,
    reason: ReasonSchema,
  })
  .strict();

export type OrderReopenApplyPayload = z.infer<
  typeof OrderReopenApplyPayloadSchema
>;
