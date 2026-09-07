/** Strict client contract for Staff's six canonical relation editor. */
import { z } from 'zod';

export const StaffCasePreferenceRelationKeySchema = z.enum([
  'service_regions', 'service_periods', 'cooking_skills',
  'holiday_availability', 'rest_schedule', 'baby_types',
]);
export const StaffCasePreferenceRelationValueSchema = z.strictObject({
  value: z.string().min(1).max(50),
  detail: z.string().max(100).nullable(),
});
export const StaffCasePreferenceRelationsSchema = z.strictObject({
  service_regions: z.array(StaffCasePreferenceRelationValueSchema),
  service_periods: z.array(StaffCasePreferenceRelationValueSchema),
  cooking_skills: z.array(StaffCasePreferenceRelationValueSchema),
  holiday_availability: z.array(StaffCasePreferenceRelationValueSchema),
  rest_schedule: z.array(StaffCasePreferenceRelationValueSchema),
  baby_types: z.array(StaffCasePreferenceRelationValueSchema),
});
export const StaffCasePreferenceManualSnapshotSchema = z.strictObject({
  staff_id: z.number().int().positive(),
  before: StaffCasePreferenceRelationsSchema,
  after: StaffCasePreferenceRelationsSchema,
  snapshot_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/).nullable(),
});
export const StaffCasePreferenceManualReceiptSchema = z.strictObject({
  staff_id: z.number().int().positive(),
  relations: StaffCasePreferenceRelationsSchema,
  snapshot_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
  idempotency_key: z.string().min(1).max(191),
  replayed: z.boolean(),
});
export const StaffCasePreferenceManualSnapshotResponseSchema = z.strictObject({
  success: z.boolean(), message: z.string(), data: StaffCasePreferenceManualSnapshotSchema, error: z.string().nullable().optional(),
});
export const StaffCasePreferenceManualReceiptResponseSchema = z.strictObject({
  success: z.boolean(), message: z.string(), data: StaffCasePreferenceManualReceiptSchema, error: z.string().nullable().optional(),
});
export type StaffCasePreferenceRelationKey = z.infer<typeof StaffCasePreferenceRelationKeySchema>;
export type StaffCasePreferenceRelationValue = z.infer<typeof StaffCasePreferenceRelationValueSchema>;
export type StaffCasePreferenceRelations = z.infer<typeof StaffCasePreferenceRelationsSchema>;
export type StaffCasePreferenceManualSnapshot = z.infer<typeof StaffCasePreferenceManualSnapshotSchema>;
export type StaffCasePreferenceManualReceipt = z.infer<typeof StaffCasePreferenceManualReceiptSchema>;
export type StaffCasePreferenceManualApplyPayload = StaffCasePreferenceRelations & {
  expected_snapshot_fingerprint: string;
  preview_fingerprint: string;
  reason: string;
};
