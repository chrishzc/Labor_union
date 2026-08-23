/**
 * File: hcm_workbook_schemas.ts
 * Description: 定義 HCM Current Workbook Preview 的嚴格成功信封與 aggregate DTO。
 */
import { z } from 'zod';

export const HcmSha256Schema = z
  .string()
  .regex(/^[0-9a-f]{64}$/, '預期 64 位小寫 Hex SHA-256');

export const HcmWorkbookPreviewSchema = z
  .object({
    source_content_digest: HcmSha256Schema,
    source_row_count: z.number().int().min(0),
    ready_count: z.number().int().min(0),
    ready_with_warning_count: z.number().int().min(0),
    review_required_count: z.number().int().min(0),
    preview_fingerprint: HcmSha256Schema,
  })
  .strict();

export type HcmWorkbookPreview = z.infer<typeof HcmWorkbookPreviewSchema>;

export const HcmWorkbookPreviewEnvelopeSchema = z
  .object({
    success: z.literal(true),
    message: z.string(),
    data: HcmWorkbookPreviewSchema,
    error: z.null(),
  })
  .strict();

export type HcmWorkbookPreviewEnvelope = z.infer<
  typeof HcmWorkbookPreviewEnvelopeSchema
>;

export const HcmWorkbookRowOutcomeSchema = z
  .object({
    source_row: z.number().int().min(1),
    case_no: z.string().max(50).nullable(),
    outcome: z.enum([
      'inserted',
      'inserted_with_warning',
      'exact_replay',
      'review_required',
      'failed',
    ]),
    problem_identity: z.string().max(191).nullable(),
    problem_fields: z.array(z.string()),
    issue_codes: z.array(z.string()),
    referral_occurrence_identities: z.array(z.string()),
  })
  .strict();

export type HcmWorkbookRowOutcome = z.infer<typeof HcmWorkbookRowOutcomeSchema>;

export const HcmWorkbookReceiptSchema = z
  .object({
    source_content_digest: HcmSha256Schema,
    source_row_count: z.number().int().min(0),
    inserted_count: z.number().int().min(0),
    inserted_with_warning_count: z.number().int().min(0),
    exact_replay_count: z.number().int().min(0),
    review_required_count: z.number().int().min(0),
    failed_count: z.number().int().min(0),
    replayed_workbook: z.boolean(),
    row_outcomes_available: z.boolean(),
    legacy_summary_only: z.boolean(),
    row_outcomes: z.array(HcmWorkbookRowOutcomeSchema),
  })
  .strict();

export type HcmWorkbookReceipt = z.infer<typeof HcmWorkbookReceiptSchema>;

export const HcmWorkbookReceiptEnvelopeSchema = z
  .object({
    success: z.literal(true),
    message: z.string(),
    data: HcmWorkbookReceiptSchema,
    error: z.null(),
  })
  .strict();

export type HcmWorkbookReceiptEnvelope = z.infer<
  typeof HcmWorkbookReceiptEnvelopeSchema
>;
