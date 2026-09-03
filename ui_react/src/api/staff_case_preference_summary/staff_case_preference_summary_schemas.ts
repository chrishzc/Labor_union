/**
 * File: staff_case_preference_summary_schemas.ts
 * Description: 定義月嫂名冊接案偏好摘要的嚴格唯讀 HTTP contract。
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
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['other_detail'],
          message: 'ready 狀態必須提供非空 other_detail。',
        });
      }
      return;
    }
    if (topic.other_detail !== null) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['other_detail'],
        message: 'not_recorded / source_not_ready 狀態的 other_detail 必須為 null。',
      });
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

export type StaffCasePreferenceOtherDetailStatus = z.infer<typeof StaffCasePreferenceOtherDetailStatusSchema>;
export type StaffCasePreferenceTopic = z.infer<typeof StaffCasePreferenceTopicSchema>;
export type StaffCasePreferenceSummary = z.infer<typeof StaffCasePreferenceSummarySchema>;
export type StaffCasePreferenceSummaryResponse = z.infer<typeof StaffCasePreferenceSummaryResponseSchema>;
