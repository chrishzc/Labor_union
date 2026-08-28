/**
 * File: schemas.ts
 * Description: 定義歷史訂單 review 更正的 strict Query／Preview／Apply DTO。
 */
import { z } from 'zod';
import { createBaseResponseSchema } from '../../shared/runtime_decoder';

export const HistoricalReviewIdentitySchema = z.string().trim().min(1).max(191);
export const HistoricalReviewSha256Schema = z.string().regex(/^[0-9a-f]{64}$/, '預期 64 位小寫 Hex SHA-256');

export const HistoricalReviewIssueSchema = z.strictObject({
  issue_code: z.string().trim().min(1),
  field_path: z.string().trim().min(1),
  field_label: z.string().trim().min(1),
  masked_source_value: z.string(),
  masked_current_value: z.string(),
  rule: z.string().trim().min(1),
  allowed_values: z.array(z.string()),
  process_blocker: z.string().trim().min(1),
});
export type HistoricalReviewIssue = z.infer<typeof HistoricalReviewIssueSchema>;

export const HistoricalReviewWorkbookContractSchema = z.strictObject({
  contract_key: z.string().trim().min(1).max(191),
  contract_version: z.number().int().positive(),
  required_columns: z.array(z.string().trim().min(1)).min(1),
  single_row_only: z.literal(true),
  file_extension: z.literal('xlsx'),
});
export type HistoricalReviewWorkbookContract = z.infer<typeof HistoricalReviewWorkbookContractSchema>;

export const HistoricalReviewContextSchema = z.strictObject({
  review_identity: HistoricalReviewIdentitySchema,
  masked_case_identity: z.string().trim().min(1),
  issues: z.array(HistoricalReviewIssueSchema),
  review_version: z.number().int().nonnegative(),
  remediation_version: z.number().int().nonnegative(),
  workbook_contract: HistoricalReviewWorkbookContractSchema,
  reason_required: z.literal(true),
  evidence_required: z.literal(true),
  completion_condition: z.string().trim().min(1),
  prior_alert_active: z.boolean(),
});
export type HistoricalReviewContext = z.infer<typeof HistoricalReviewContextSchema>;

export const HistoricalReviewDispositionSchema = z.enum([
  'corrected_source_adopted',
  'superseded_by_replacement_review',
]);
export type HistoricalReviewDisposition = z.infer<typeof HistoricalReviewDispositionSchema>;

export const HistoricalReviewPreviewSchema = z.strictObject({
  prior_review_identity: HistoricalReviewIdentitySchema,
  source_content_digest: HistoricalReviewSha256Schema,
  outcome: HistoricalReviewDispositionSchema,
  remaining_issues: z.array(HistoricalReviewIssueSchema),
  preview_fingerprint: HistoricalReviewSha256Schema,
  review_version: z.number().int().nonnegative(),
  remediation_version: z.number().int().nonnegative(),
});
export type HistoricalReviewPreview = z.infer<typeof HistoricalReviewPreviewSchema>;

export const HistoricalReviewReceiptSchema = z.strictObject({
  remediation_receipt_identity: HistoricalReviewIdentitySchema,
  disposition: HistoricalReviewDispositionSchema,
  source_content_digest: HistoricalReviewSha256Schema,
  preview_fingerprint: HistoricalReviewSha256Schema,
  resulting_remediation_version: z.number().int().positive(),
});
export type HistoricalReviewReceipt = z.infer<typeof HistoricalReviewReceiptSchema>;

export const HistoricalReviewSuccessorSchema = z.strictObject({
  review_identity: HistoricalReviewIdentitySchema,
  masked_case_identity: z.string().trim().min(1),
  issues: z.array(HistoricalReviewIssueSchema),
});
export type HistoricalReviewSuccessor = z.infer<typeof HistoricalReviewSuccessorSchema>;

export const HistoricalReviewReadbackSchema = z.strictObject({
  prior_review_identity: HistoricalReviewIdentitySchema,
  prior_alert_active: z.boolean(),
  remaining_issues: z.array(HistoricalReviewIssueSchema),
  review_version: z.number().int().nonnegative(),
  remediation_version: z.number().int().nonnegative(),
});
export type HistoricalReviewReadback = z.infer<typeof HistoricalReviewReadbackSchema>;

export const HistoricalReviewApplySchema = z.strictObject({
  prior_review_identity: HistoricalReviewIdentitySchema,
  disposition: HistoricalReviewDispositionSchema,
  receipt: HistoricalReviewReceiptSchema,
  prior_alert_active: z.boolean(),
  successor: HistoricalReviewSuccessorSchema.nullable(),
  replayed: z.boolean(),
  readback: HistoricalReviewReadbackSchema,
});
export type HistoricalReviewApply = z.infer<typeof HistoricalReviewApplySchema>;

export const HistoricalReviewContextEnvelopeSchema = createBaseResponseSchema(HistoricalReviewContextSchema);
export const HistoricalReviewPreviewEnvelopeSchema = createBaseResponseSchema(HistoricalReviewPreviewSchema);
export const HistoricalReviewApplyEnvelopeSchema = createBaseResponseSchema(HistoricalReviewApplySchema);
