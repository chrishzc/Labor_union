/**
 * File: staff_case_preference_summary_schemas.ts
 * Description: 定義月嫂名冊接案偏好摘要與六項專用 Preview/Apply contract。
 */
import { z } from 'zod';

export const StaffCasePreferenceOtherDetailStatusSchema = z.enum([
  'ready',
  'not_recorded',
  'source_not_ready',
]);

export const StaffCasePreferenceTopicSchema = z
  .object({
    values: z.array(z.string()),
    other_detail: z.string().nullable(),
    other_detail_status: StaffCasePreferenceOtherDetailStatusSchema,
  })
  .strict()
  .superRefine((topic, ctx) => {
    if (topic.other_detail_status === 'ready') {
      if (topic.other_detail === null || topic.other_detail.trim().length === 0) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['other_detail'], message: 'ready 狀態必須提供非空 other_detail。' });
      }
      return;
    }
    if (topic.other_detail !== null) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['other_detail'], message: 'not_recorded / source_not_ready 狀態的 other_detail 必須為 null。' });
    }
  });

export const StaffCasePreferenceSummarySchema = z
  .object({
    staff_id: z.number().int().positive(),
    service_regions: StaffCasePreferenceTopicSchema,
    service_periods: StaffCasePreferenceTopicSchema,
    rest_schedule: StaffCasePreferenceTopicSchema,
    baby_counts: StaffCasePreferenceTopicSchema,
    holiday_availability: StaffCasePreferenceTopicSchema,
    transportation: StaffCasePreferenceTopicSchema,
  })
  .strict();

export const StaffCasePreferenceSummaryResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: StaffCasePreferenceSummarySchema,
    error: z.string().nullable().optional(),
  })
  .strict();

export const StaffCasePreferenceTopicInputSchema = z.object({
  values: z.array(z.string()),
  other_detail: z.string().nullable(),
}).strict();

export const StaffCasePreferenceSnapshotSchema = z.object({
  service_regions: StaffCasePreferenceTopicInputSchema,
  service_periods: StaffCasePreferenceTopicInputSchema,
  rest_schedule: StaffCasePreferenceTopicInputSchema,
  baby_counts: StaffCasePreferenceTopicInputSchema,
  holiday_availability: StaffCasePreferenceTopicInputSchema,
  transportation: StaffCasePreferenceTopicInputSchema,
}).strict();

export const StaffCasePreferencePreviewSchema = z.object({
  staff_id: z.number().int().positive(),
  before: StaffCasePreferenceSnapshotSchema,
  after: StaffCasePreferenceSnapshotSchema,
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
}).strict();

export const StaffCasePreferencePreviewResponseSchema = z.object({
  success: z.boolean(),
  message: z.string(),
  data: StaffCasePreferencePreviewSchema,
  error: z.string().nullable().optional(),
}).strict();

export const StaffCasePreferenceApplyPayloadSchema = z.object({
  snapshot: StaffCasePreferenceSnapshotSchema,
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
}).strict();

export const StaffCasePreferenceApplyReceiptSchema = z.object({
  staff_id: z.number().int().positive(),
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
  snapshot: StaffCasePreferenceSnapshotSchema,
}).strict();

export const StaffCasePreferenceApplyReceiptResponseSchema = z.object({
  success: z.boolean(),
  message: z.string(),
  data: StaffCasePreferenceApplyReceiptSchema,
  error: z.string().nullable().optional(),
}).strict();

export type StaffCasePreferenceOtherDetailStatus = z.infer<typeof StaffCasePreferenceOtherDetailStatusSchema>;
export type StaffCasePreferenceTopic = z.infer<typeof StaffCasePreferenceTopicSchema>;
export type StaffCasePreferenceSummary = z.infer<typeof StaffCasePreferenceSummarySchema>;
export type StaffCasePreferenceSummaryResponse = z.infer<typeof StaffCasePreferenceSummaryResponseSchema>;
export type StaffCasePreferenceTopicInput = z.infer<typeof StaffCasePreferenceTopicInputSchema>;
export type StaffCasePreferenceSnapshot = z.infer<typeof StaffCasePreferenceSnapshotSchema>;
export type StaffCasePreferencePreview = z.infer<typeof StaffCasePreferencePreviewSchema>;
export type StaffCasePreferenceApplyPayload = z.infer<typeof StaffCasePreferenceApplyPayloadSchema>;
export type StaffCasePreferenceApplyReceipt = z.infer<typeof StaffCasePreferenceApplyReceiptSchema>;
