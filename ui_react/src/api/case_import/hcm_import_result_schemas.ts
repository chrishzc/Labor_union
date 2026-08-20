/**
 * File: hcm_import_result_schemas.ts
 * Description: 嚴格解碼 HCM recent results、逐列結果與legacy membership unavailable狀態。
 */
import { z } from 'zod';

const Sha256Schema = z.string().regex(/^[0-9a-f]{64}$/);
const TimestampSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);

export const HcmImportRowOutcomeSchema = z.strictObject({
  source_row: z.number().int().positive(),
  case_no: z.string().min(1).max(50).nullable(),
  outcome: z.enum(['inserted', 'inserted_with_warning', 'exact_replay', 'review_required', 'failed']),
  problem_identity: z.string().min(1).max(191).nullable(),
  problem_fields: z.array(z.string()),
  issue_codes: z.array(z.string()),
  referral_occurrence_identities: z.array(z.string()),
});

export const HcmImportResultRecordSchema = z.strictObject({
  receipt_id: z.number().int().positive(),
  completed_at: TimestampSchema,
  source_content_digest: Sha256Schema,
  source_row_count: z.number().int().nonnegative(),
  inserted_count: z.number().int().nonnegative(),
  inserted_with_warning_count: z.number().int().nonnegative(),
  exact_replay_count: z.number().int().nonnegative(),
  review_required_count: z.number().int().nonnegative(),
  failed_count: z.number().int().nonnegative(),
  replayed_workbook: z.boolean(),
  row_outcomes_available: z.boolean(),
  legacy_summary_only: z.boolean(),
  row_outcomes: z.array(HcmImportRowOutcomeSchema),
});

export const HcmImportResultPageSchema = z.strictObject({
  items: z.array(HcmImportResultRecordSchema),
  next_cursor: z.number().int().positive().nullable(),
});

export const HcmImportResultEnvelopeSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: HcmImportResultPageSchema,
  error: z.string().nullable(),
});

export type HcmImportRowOutcome = z.infer<typeof HcmImportRowOutcomeSchema>;
export type HcmImportResultRecord = z.infer<typeof HcmImportResultRecordSchema>;
export type HcmImportResultPage = z.infer<typeof HcmImportResultPageSchema>;

