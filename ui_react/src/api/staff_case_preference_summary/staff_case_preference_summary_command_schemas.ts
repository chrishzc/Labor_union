/**
 * File: staff_case_preference_summary_command_schemas.ts
 * Description: 六項 Staff 接案偏好 Preview → Apply 的 strict HTTP contract。
 */
import { z } from 'zod';

export const StaffCasePreferenceTopicInputSchema = z.object({
  values: z.array(z.string()),
  other_detail: z.string().nullable(),
}).strict();

export const StaffCasePreferenceSnapshotInputSchema = z.object({
  service_regions: StaffCasePreferenceTopicInputSchema,
  service_periods: StaffCasePreferenceTopicInputSchema,
  rest_schedule: StaffCasePreferenceTopicInputSchema,
  baby_counts: StaffCasePreferenceTopicInputSchema,
  holiday_availability: StaffCasePreferenceTopicInputSchema,
  transportation: StaffCasePreferenceTopicInputSchema,
}).strict();

export const StaffCasePreferencePreviewRequestSchema = z.object({
  snapshot: StaffCasePreferenceSnapshotInputSchema,
}).strict();

export const StaffCasePreferenceApplyRequestSchema = z.object({
  snapshot: StaffCasePreferenceSnapshotInputSchema,
  expected_fingerprint: z.string().length(64),
  preview_fingerprint: z.string().length(64),
}).strict();

export const StaffCasePreferencePreviewSchema = z.object({
  staff_id: z.number().int().positive(),
  expected_fingerprint: z.string().length(64),
  preview_fingerprint: z.string().length(64),
  changed_topics: z.array(z.string()),
  snapshot: StaffCasePreferenceSnapshotInputSchema,
}).strict();

export const StaffCasePreferenceReceiptSchema = z.object({
  staff_id: z.number().int().positive(),
  outcome: z.enum(['applied', 'already_observed']),
  snapshot_fingerprint: z.string().length(64),
  changed_topics: z.array(z.string()),
}).strict();

export const StaffCasePreferencePreviewResponseSchema = z.object({
  success: z.boolean(),
  message: z.string(),
  data: StaffCasePreferencePreviewSchema,
  error: z.string().nullable().optional(),
}).strict();

export const StaffCasePreferenceReceiptResponseSchema = z.object({
  success: z.boolean(),
  message: z.string(),
  data: StaffCasePreferenceReceiptSchema,
  error: z.string().nullable().optional(),
}).strict();

export type StaffCasePreferenceTopicInput = z.infer<typeof StaffCasePreferenceTopicInputSchema>;
export type StaffCasePreferenceSnapshotInput = z.infer<typeof StaffCasePreferenceSnapshotInputSchema>;
export type StaffCasePreferencePreviewRequest = z.infer<typeof StaffCasePreferencePreviewRequestSchema>;
export type StaffCasePreferenceApplyRequest = z.infer<typeof StaffCasePreferenceApplyRequestSchema>;
export type StaffCasePreferencePreview = z.infer<typeof StaffCasePreferencePreviewSchema>;
export type StaffCasePreferenceReceipt = z.infer<typeof StaffCasePreferenceReceiptSchema>;
