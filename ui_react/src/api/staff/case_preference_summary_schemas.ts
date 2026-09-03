/**
 * File: case_preference_summary_schemas.ts
 * Description: 定義 Staff roster 接案偏好摘要的 strict GET 契約與逐母題降級讀模型。
 */
import { z } from 'zod';

export const StaffCasePreferenceOtherDetailStatusSchema = z.enum([
  'ready',
  'not_recorded',
  'source_not_ready',
]);

export const StaffCasePreferenceTopicSummarySchema = z.strictObject({
  values: z.array(z.string().min(1).max(255)),
  other_detail: z.string().min(1).max(500).nullable(),
  other_detail_status: StaffCasePreferenceOtherDetailStatusSchema,
}).superRefine((value, ctx) => {
  if (value.other_detail_status === 'ready' && value.other_detail === null) {
    ctx.addIssue({ code: 'custom', path: ['other_detail'], message: 'ready 必須提供 other_detail。' });
  }
  if (value.other_detail_status !== 'ready' && value.other_detail !== null) {
    ctx.addIssue({ code: 'custom', path: ['other_detail'], message: '非 ready 狀態不得提供 other_detail。' });
  }
});

export const StaffCasePreferenceSummarySchema = z.strictObject({
  staff_id: z.number().int().positive(),
  service_regions: StaffCasePreferenceTopicSummarySchema,
  service_periods: StaffCasePreferenceTopicSummarySchema,
  rest_schedule: StaffCasePreferenceTopicSummarySchema,
  baby_counts: StaffCasePreferenceTopicSummarySchema,
  holiday_availability: StaffCasePreferenceTopicSummarySchema,
  transportation: StaffCasePreferenceTopicSummarySchema,
});

export const StaffCasePreferenceSummaryResponseSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: StaffCasePreferenceSummarySchema.nullable(),
  error: z.string().nullable().optional(),
});

export const StaffCasePreferenceSummaryLooseResponseSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: z.unknown().nullable(),
  error: z.string().nullable().optional(),
});

export const StaffCasePreferenceSummaryLooseDataSchema = z.strictObject({
  staff_id: z.number().int().positive(),
  service_regions: z.unknown(),
  service_periods: z.unknown(),
  rest_schedule: z.unknown(),
  baby_counts: z.unknown(),
  holiday_availability: z.unknown(),
  transportation: z.unknown(),
});

export const STAFF_CASE_PREFERENCE_TOPIC_KEYS = [
  'service_regions',
  'service_periods',
  'rest_schedule',
  'baby_counts',
  'holiday_availability',
  'transportation',
] as const;

export type StaffCasePreferenceTopicKey = typeof STAFF_CASE_PREFERENCE_TOPIC_KEYS[number];
export type StaffCasePreferenceOtherDetailStatus = z.infer<typeof StaffCasePreferenceOtherDetailStatusSchema>;
export type StaffCasePreferenceTopicSummary = z.infer<typeof StaffCasePreferenceTopicSummarySchema>;
export type StaffCasePreferenceSummary = z.infer<typeof StaffCasePreferenceSummarySchema>;

export type StaffCasePreferenceTopicRead =
  | { availability: 'available'; data: StaffCasePreferenceTopicSummary }
  | { availability: 'unavailable'; reason: 'invalid_topic' };

export interface StaffCasePreferenceSummaryRead {
  staff_id: number;
  service_regions: StaffCasePreferenceTopicRead;
  service_periods: StaffCasePreferenceTopicRead;
  rest_schedule: StaffCasePreferenceTopicRead;
  baby_counts: StaffCasePreferenceTopicRead;
  holiday_availability: StaffCasePreferenceTopicRead;
  transportation: StaffCasePreferenceTopicRead;
}
