/**
 * File: staff_lifecycle_schemas.ts
 * Description: 對齊 Staff lifecycle Pydantic DTO 的 strict Zod 契約。
 */
import { z } from 'zod';

const FINGERPRINT_PATTERN = /^[0-9a-f]{64}$/;
const OFFSET_DATETIME_PATTERN =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

function isAwareIsoDateTime(value: string): boolean {
  return OFFSET_DATETIME_PATTERN.test(value) && !Number.isNaN(Date.parse(value));
}

export const StaffLifecycleAwareDateTimeSchema = z.string().refine(isAwareIsoDateTime, {
  message: 'effective_at 必須是帶時區的 ISO datetime。',
});

export const StaffLifecycleFingerprintSchema = z.string().regex(FINGERPRINT_PATTERN, {
  message: '預期 64 位元小寫 Hex SHA-256 指紋。',
});

export const StaffLifecycleStateSchema = z.enum(['active', 'retired']);
export const StaffLifecycleActionSchema = z.enum(['retirement', 'reactivation']);

export const StaffLifecycleTransitionInputSchema = z
  .strictObject({
    effective_at: StaffLifecycleAwareDateTimeSchema,
    reason_code: z.string().min(1).max(64),
  });

export const StaffLifecycleApplyPayloadSchema = z
  .strictObject({
    effective_at: StaffLifecycleAwareDateTimeSchema,
    reason_code: z.string().min(1).max(64),
    expected_version: z.number().int().nonnegative(),
    preview_fingerprint: StaffLifecycleFingerprintSchema,
  });

export const StaffLifecycleViewSchema = z
  .strictObject({
    staff_id: z.number().int().positive(),
    state: StaffLifecycleStateSchema,
    version: z.number().int().nonnegative(),
    effective_at: StaffLifecycleAwareDateTimeSchema.nullable().optional(),
    reason_code: z.string().nullable().optional(),
  });

export const StaffLifecyclePreviewSchema = z
  .strictObject({
    staff_id: z.number().int().positive(),
    state: StaffLifecycleStateSchema,
    version: z.number().int().nonnegative(),
    effective_at: StaffLifecycleAwareDateTimeSchema.nullable().optional(),
    reason_code: z.string().nullable().optional(),
    after_state: StaffLifecycleStateSchema,
    preview_fingerprint: StaffLifecycleFingerprintSchema,
  });

export const StaffLifecycleApplyReceiptSchema = z
  .strictObject({
    staff_id: z.number().int().positive(),
    state: StaffLifecycleStateSchema,
    resulting_version: z.number().int().nonnegative(),
    preview_fingerprint: StaffLifecycleFingerprintSchema,
    idempotency_key: z.string().min(1).max(191),
  });

export const StaffLifecycleQueryResponseSchema = z
  .strictObject({
    success: z.boolean(),
    message: z.string(),
    data: StaffLifecycleViewSchema.nullable(),
    error: z.string().nullable().optional(),
  });

export const StaffLifecyclePreviewResponseSchema = z
  .strictObject({
    success: z.boolean(),
    message: z.string(),
    data: StaffLifecyclePreviewSchema.nullable(),
    error: z.string().nullable().optional(),
  });

export const StaffLifecycleReceiptResponseSchema = z
  .strictObject({
    success: z.boolean(),
    message: z.string(),
    data: StaffLifecycleApplyReceiptSchema.nullable(),
    error: z.string().nullable().optional(),
  });

export type StaffLifecycleAction = z.infer<typeof StaffLifecycleActionSchema>;
export type StaffLifecycleState = z.infer<typeof StaffLifecycleStateSchema>;
export type StaffLifecycleTransitionInput = z.infer<typeof StaffLifecycleTransitionInputSchema>;
export type StaffLifecycleApplyPayload = z.infer<typeof StaffLifecycleApplyPayloadSchema>;
export type StaffLifecycleView = z.infer<typeof StaffLifecycleViewSchema>;
export type StaffLifecyclePreview = z.infer<typeof StaffLifecyclePreviewSchema>;
export type StaffLifecycleApplyReceipt = z.infer<typeof StaffLifecycleApplyReceiptSchema>;

export const StaffLifecycleTransitionSchema = StaffLifecycleTransitionInputSchema;
export const StaffLifecycleApplyInputSchema = StaffLifecycleApplyPayloadSchema;
export const StaffLifecyclePreviewViewSchema = StaffLifecyclePreviewSchema;
export const StaffLifecycleApplyReceiptViewSchema = StaffLifecycleApplyReceiptSchema;
