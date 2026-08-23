/**
 * File: schemas.ts
 * Description: 定義Historical Orders工作簿Preview的嚴格成功信封與aggregate DTO。
 */
import { z } from 'zod';

export const HistoricalOrderSha256Schema = z.string().regex(/^[0-9a-f]{64}$/, '預期 64 位小寫 Hex SHA-256');

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
    preview_fingerprint: HistoricalOrderSha256Schema,
  })
  .strict();

export type HistoricalOrderWorkbookPreview = z.infer<typeof HistoricalOrderWorkbookPreviewSchema>;

export const HistoricalOrderWorkbookReceiptSchema = z.object({
  source_content_digest: HistoricalOrderSha256Schema,
  source_row_count: z.number().int().min(0),
  adopted_count: z.number().int().min(0),
  unmatched_case_count: z.number().int().min(0),
  review_required_count: z.number().int().min(0),
  current_conflict_count: z.number().int().min(0),
  assignments_created: z.number().int().min(0),
  replayed_rows: z.number().int().min(0),
  replayed_workbook: z.boolean(),
}).strict();

export type HistoricalOrderWorkbookReceipt = z.infer<typeof HistoricalOrderWorkbookReceiptSchema>;

export const HistoricalOrderWorkbookPreviewEnvelopeSchema = z
  .object({ success: z.literal(true), message: z.string(), data: HistoricalOrderWorkbookPreviewSchema, error: z.null() })
  .strict();

export const HistoricalOrderWorkbookReceiptEnvelopeSchema = z
  .object({ success: z.literal(true), message: z.string(), data: HistoricalOrderWorkbookReceiptSchema, error: z.null() })
  .strict();
