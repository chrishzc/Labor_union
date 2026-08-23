/**
 * File: schemas.ts
 * Description: 定義Staff Historical工作簿Preview的嚴格成功信封與aggregate DTO。
 */
import { z } from 'zod';

export const StaffHistoricalSha256Schema = z.string().regex(/^[0-9a-f]{64}$/, '預期 64 位小寫 Hex SHA-256');

export const StaffHistoricalWorkbookPreviewSchema = z
  .object({
    source_content_digest: StaffHistoricalSha256Schema,
    source_row_count: z.number().int().min(0),
    created_count: z.number().int().min(0),
    adopted_existing_count: z.number().int().min(0),
    blocked_identity_count: z.number().int().min(0),
    identity_conflict_count: z.number().int().min(0),
    review_required_count: z.number().int().min(0),
    preview_fingerprint: StaffHistoricalSha256Schema,
  })
  .strict();

export type StaffHistoricalWorkbookPreview = z.infer<typeof StaffHistoricalWorkbookPreviewSchema>;

export const StaffHistoricalWorkbookPreviewEnvelopeSchema = z
  .object({
    success: z.literal(true),
    message: z.string(),
    data: StaffHistoricalWorkbookPreviewSchema,
    error: z.null(),
  })
  .strict();

export const StaffHistoricalWorkbookReceiptSchema = StaffHistoricalWorkbookPreviewSchema.extend({
  exact_replay_count: z.number().int().min(0),
  replayed_workbook: z.boolean(),
}).strict();

export type StaffHistoricalWorkbookReceipt = z.infer<typeof StaffHistoricalWorkbookReceiptSchema>;

export const StaffHistoricalWorkbookReceiptEnvelopeSchema = z
  .object({
    success: z.literal(true),
    message: z.string(),
    data: StaffHistoricalWorkbookReceiptSchema,
    error: z.null(),
  })
  .strict();
