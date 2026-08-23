/**
 * File: staff_availability_schemas.ts
 * Description: 對齊 Staff Availability Pydantic DTO 的 strict Zod 契約。
 */
import { z } from 'zod';

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const FINGERPRINT_PATTERN = /^[0-9a-f]{64}$/;

function isIsoDate(value: string): boolean {
  if (!ISO_DATE_PATTERN.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
}

export const StaffAvailabilityDateSchema = z.string().refine(isIsoDate, {
  message: '預期有效的 ISO 日期 YYYY-MM-DD。',
});

export const StaffAvailabilityFingerprintSchema = z.string().regex(FINGERPRINT_PATTERN, {
  message: '預期 64 位元小寫 Hex SHA-256 指紋。',
});

export const StaffAvailabilityActionSchema = z.enum([
  'create_long_leave',
  'create_pause',
  'end_pause',
  'cancel',
]);

export const StaffUnavailabilityKindSchema = z.enum(['long_leave', 'paused_service']);
export const StaffAvailabilityBlockStatusSchema = z.enum(['effective', 'cancelled']);

export const StaffAvailabilityIntentSchema = z
  .strictObject({
    action: StaffAvailabilityActionSchema,
    reason: z.string().min(1).max(500),
    start_date: StaffAvailabilityDateSchema.nullable().optional(),
    end_date: StaffAvailabilityDateSchema.nullable().optional(),
    block_id: z.number().int().positive().nullable().optional(),
    resume_date: StaffAvailabilityDateSchema.nullable().optional(),
  });

export const StaffAvailabilityApplyPayloadSchema = z
  .strictObject({
    action: StaffAvailabilityActionSchema,
    reason: z.string().min(1).max(500),
    start_date: StaffAvailabilityDateSchema.nullable().optional(),
    end_date: StaffAvailabilityDateSchema.nullable().optional(),
    block_id: z.number().int().positive().nullable().optional(),
    resume_date: StaffAvailabilityDateSchema.nullable().optional(),
    expected_version: z.number().int().nonnegative(),
    preview_fingerprint: StaffAvailabilityFingerprintSchema,
  });

export const StaffUnavailabilityBlockSchema = z
  .strictObject({
    block_id: z.number().int().positive(),
    staff_id: z.number().int().positive(),
    kind: StaffUnavailabilityKindSchema,
    start_date: StaffAvailabilityDateSchema,
    end_date: StaffAvailabilityDateSchema.nullable(),
    status: StaffAvailabilityBlockStatusSchema,
    reason: z.string(),
  });

export const StaffAvailabilityPreviewSchema = z
  .strictObject({
    staff_id: z.number().int().positive(),
    action: StaffAvailabilityActionSchema,
    source_version: z.number().int().nonnegative(),
    target_block: StaffUnavailabilityBlockSchema.nullable(),
    candidate_kind: StaffUnavailabilityKindSchema.nullable(),
    candidate_start_date: StaffAvailabilityDateSchema.nullable(),
    candidate_end_date: StaffAvailabilityDateSchema.nullable(),
    blockers: z.array(z.string()),
    can_apply: z.boolean(),
    preview_fingerprint: StaffAvailabilityFingerprintSchema,
  });

export const StaffAvailabilityReceiptSchema = z
  .strictObject({
    staff_id: z.number().int().positive(),
    action: StaffAvailabilityActionSchema,
    block: StaffUnavailabilityBlockSchema,
    aggregate_version: z.number().int().positive(),
    preview_fingerprint: StaffAvailabilityFingerprintSchema,
    idempotency_key: z.string().min(1).max(191),
  });

export const StaffAvailabilityQueryResponseSchema = z
  .strictObject({
    success: z.boolean(),
    message: z.string(),
    data: z.array(StaffUnavailabilityBlockSchema).nullable(),
    error: z.string().nullable().optional(),
  });

export const StaffAvailabilityPreviewResponseSchema = z
  .strictObject({
    success: z.boolean(),
    message: z.string(),
    data: StaffAvailabilityPreviewSchema.nullable(),
    error: z.string().nullable().optional(),
  });

export const StaffAvailabilityReceiptResponseSchema = z
  .strictObject({
    success: z.boolean(),
    message: z.string(),
    data: StaffAvailabilityReceiptSchema.nullable(),
    error: z.string().nullable().optional(),
  });

export type StaffAvailabilityAction = z.infer<typeof StaffAvailabilityActionSchema>;
export type StaffUnavailabilityKind = z.infer<typeof StaffUnavailabilityKindSchema>;
export type StaffAvailabilityBlockStatus = z.infer<typeof StaffAvailabilityBlockStatusSchema>;
export type StaffAvailabilityIntent = z.infer<typeof StaffAvailabilityIntentSchema>;
export type StaffAvailabilityApplyPayload = z.infer<typeof StaffAvailabilityApplyPayloadSchema>;
export type StaffUnavailabilityBlock = z.infer<typeof StaffUnavailabilityBlockSchema>;
export type StaffAvailabilityPreview = z.infer<typeof StaffAvailabilityPreviewSchema>;
export type StaffAvailabilityReceipt = z.infer<typeof StaffAvailabilityReceiptSchema>;

export type StaffAvailabilityQueryResponse = z.infer<typeof StaffAvailabilityQueryResponseSchema>;
export type StaffAvailabilityPreviewResponse = z.infer<typeof StaffAvailabilityPreviewResponseSchema>;
export type StaffAvailabilityReceiptResponse = z.infer<typeof StaffAvailabilityReceiptResponseSchema>;

export const StaffAvailabilityIntentBodySchema = StaffAvailabilityIntentSchema;
export const StaffAvailabilityApplyBodySchema = StaffAvailabilityApplyPayloadSchema;
export const StaffUnavailabilityBlockViewSchema = StaffUnavailabilityBlockSchema;
export const StaffAvailabilityPreviewViewSchema = StaffAvailabilityPreviewSchema;
export const StaffAvailabilityReceiptViewSchema = StaffAvailabilityReceiptSchema;
