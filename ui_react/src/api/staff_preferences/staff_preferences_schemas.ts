/**
 * File: staff_preferences_schemas.ts
 * Description: 對齊 Staff 偏好 definitions、profile、preview 與 receipt 的 strict Zod 契約。
 */
import { z } from 'zod';

export const StaffPreferenceValueKindSchema = z.enum([
  'integer_range',
  'integer_set',
]);

export const StaffPreferenceComparisonOperatorSchema = z.enum([
  'range_with_tolerance',
  'contains_integer',
]);

export const StaffPreferenceFingerprintSchema = z
  .string()
  .regex(/^[0-9a-f]{64}$/);

export const StaffPreferenceIntegerRangeSchema = z
  .strictObject({
    kind: z.literal('integer_range'),
    minimum: z.number().int().positive(),
    maximum: z.number().int().positive(),
  });

export const StaffPreferenceIntegerSetSchema = z
  .strictObject({
    kind: z.literal('integer_set'),
    values: z.array(z.number().int()).min(1),
  });

export const StaffPreferenceValueSchema = z.discriminatedUnion('kind', [
  StaffPreferenceIntegerRangeSchema,
  StaffPreferenceIntegerSetSchema,
]);

export const StaffPreferenceDefinitionSchema = z.strictObject({
  preference_key: z.string().min(1).max(64),
  display_name: z.string().min(1).max(100),
  value_kind: StaffPreferenceValueKindSchema,
  is_filterable: z.boolean(),
  order_fact_key: z.string().min(1).max(64).nullable(),
  comparison_operator: StaffPreferenceComparisonOperatorSchema.nullable(),
  active: z.boolean(),
  version: z.number().int().nonnegative(),
});

export const StaffPreferenceValueInputSchema = z.strictObject({
  preference_key: z.string().min(1).max(64),
  value: StaffPreferenceValueSchema,
});

export const StaffPreferenceValueViewSchema = z.strictObject({
  preference_key: z.string(),
  value: StaffPreferenceValueSchema,
});

export const StaffPreferenceProfileInputSchema = z.strictObject({
  values: z.array(StaffPreferenceValueInputSchema),
});

export const StaffPreferenceProfileSchema = z.strictObject({
  staff_id: z.number().int().positive(),
  version: z.number().int().nonnegative(),
  values: z.array(StaffPreferenceValueViewSchema),
});

export const StaffPreferenceProfilePreviewSchema = z.strictObject({
  staff_id: z.number().int().positive(),
  before: z.array(StaffPreferenceValueViewSchema),
  after: z.array(StaffPreferenceValueViewSchema),
  version: z.number().int().nonnegative(),
  preview_fingerprint: StaffPreferenceFingerprintSchema,
});

export const StaffPreferenceReasonSchema = z
  .string()
  .min(1)
  .max(500)
  .refine((value) => value.trim().length > 0);

export const StaffPreferenceProfileApplyPayloadSchema = z
  .strictObject({
    values: z.array(StaffPreferenceValueInputSchema),
    expected_version: z.number().int().nonnegative(),
    preview_fingerprint: StaffPreferenceFingerprintSchema,
    reason: StaffPreferenceReasonSchema,
  });

export const StaffPreferenceProfileApplyReceiptSchema = z.strictObject({
  staff_id: z.number().int().positive(),
  version: z.number().int().positive(),
  values: z.array(StaffPreferenceValueViewSchema),
  preview_fingerprint: StaffPreferenceFingerprintSchema,
  idempotency_key: z.string().min(1).max(191),
});

export const StaffPreferenceDefinitionsResponseSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: z.array(StaffPreferenceDefinitionSchema),
  error: z.string().nullable().optional(),
});

export const StaffPreferenceProfileResponseSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: StaffPreferenceProfileSchema,
  error: z.string().nullable().optional(),
});

export const StaffPreferenceProfilePreviewResponseSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: StaffPreferenceProfilePreviewSchema,
  error: z.string().nullable().optional(),
});

export const StaffPreferenceProfileApplyReceiptResponseSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: StaffPreferenceProfileApplyReceiptSchema,
  error: z.string().nullable().optional(),
});

export type StaffPreferenceValueKind = z.infer<typeof StaffPreferenceValueKindSchema>;
export type StaffPreferenceComparisonOperator = z.infer<
  typeof StaffPreferenceComparisonOperatorSchema
>;
export type StaffPreferenceValue = z.infer<typeof StaffPreferenceValueSchema>;
export type StaffPreferenceDefinition = z.infer<typeof StaffPreferenceDefinitionSchema>;
export type StaffPreferenceValueInput = z.infer<typeof StaffPreferenceValueInputSchema>;
export type StaffPreferenceValueView = z.infer<typeof StaffPreferenceValueViewSchema>;
export type StaffPreferenceProfileInput = z.infer<typeof StaffPreferenceProfileInputSchema>;
export type StaffPreferenceProfile = z.infer<typeof StaffPreferenceProfileSchema>;
export type StaffPreferenceProfilePreview = z.infer<
  typeof StaffPreferenceProfilePreviewSchema
>;
export type StaffPreferenceProfileApplyPayload = z.infer<
  typeof StaffPreferenceProfileApplyPayloadSchema
>;
export type StaffPreferenceProfileApplyReceipt = z.infer<
  typeof StaffPreferenceProfileApplyReceiptSchema
>;
