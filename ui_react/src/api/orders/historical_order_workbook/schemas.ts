/**
 * File: schemas.ts
 * Description: 定義Historical Orders工作簿Preview的嚴格成功信封與aggregate DTO。
 */
import { z } from 'zod';

export const HistoricalOrderSha256Schema = z.string().regex(/^[0-9a-f]{64}$/, '預期 64 位小寫 Hex SHA-256');

export const HistoricalOrderStatusCountsSchema = z.object({
  cancelled_0: z.number().int().min(0),
  deposit_paid_1: z.number().int().min(0),
  discussion_2: z.number().int().min(0),
  invalid_or_blank: z.number().int().min(0),
}).strict();

const validateStatusCountConservation = (
  value: { source_row_count: number; status_counts: z.infer<typeof HistoricalOrderStatusCountsSchema> },
  context: z.RefinementCtx
) => {
  const total = Object.values(value.status_counts).reduce((sum, count) => sum + count, 0);
  if (total !== value.source_row_count) {
    context.addIssue({
      code: 'custom',
      path: ['status_counts'],
      message: 'historical_order_status_counts_not_conserved',
    });
  }
};

export const HistoricalOrderWorkbookPreviewSchema = z
  .object({
    source_content_digest: HistoricalOrderSha256Schema,
    sheet_identity: HistoricalOrderSha256Schema,
    source_row_count: z.number().int().min(0),
    adopted_count: z.number().int().min(0),
    unmatched_case_count: z.number().int().min(0),
    review_required_count: z.number().int().min(0),
    current_conflict_count: z.number().int().min(0),
    assignment_candidate_count: z.number().int().min(0),
    evidence_only_pairing_count: z.number().int().min(0),
    status_counts: HistoricalOrderStatusCountsSchema,
    preview_fingerprint: HistoricalOrderSha256Schema,
  })
  .strict()
  .superRefine(validateStatusCountConservation);

export type HistoricalOrderWorkbookPreview = z.infer<typeof HistoricalOrderWorkbookPreviewSchema>;

export const HistoricalOrderWorkbookReceiptSchema = z
  .object({
    source_content_digest: HistoricalOrderSha256Schema,
    source_row_count: z.number().int().min(0),
    adopted_count: z.number().int().min(0),
    unmatched_case_count: z.number().int().min(0),
    review_required_count: z.number().int().min(0),
    current_conflict_count: z.number().int().min(0),
    assignments_created: z.number().int().min(0),
    replayed_rows: z.number().int().min(0),
    replayed_workbook: z.boolean(),
    status_counts: HistoricalOrderStatusCountsSchema,
    review_references: z.array(z.string().trim().min(1).max(191)).max(100),
  })
  .strict()
  .superRefine(validateStatusCountConservation);

export type HistoricalOrderWorkbookReceipt = z.infer<typeof HistoricalOrderWorkbookReceiptSchema>;

export const HistoricalOrderWorkbookPreviewEnvelopeSchema = z
  .object({ success: z.literal(true), message: z.string(), data: HistoricalOrderWorkbookPreviewSchema, error: z.null() })
  .strict();

export const HistoricalOrderWorkbookReceiptEnvelopeSchema = z
  .object({ success: z.literal(true), message: z.string(), data: HistoricalOrderWorkbookReceiptSchema, error: z.null() })
  .strict();
