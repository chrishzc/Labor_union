/**
 * File: schemas.ts
 * Description: 定義Client BeClass工作簿Preview／Apply的嚴格成功信封與aggregate DTO。
 */
import { z } from 'zod';

export const ClientBeClassSha256Schema = z
  .string()
  .regex(/^[0-9a-f]{64}$/, '預期 64 位小寫 Hex SHA-256');

export const ClientBeClassWorkbookPreviewSchema = z
  .object({
    source_content_digest: ClientBeClassSha256Schema,
    sheet_identity: ClientBeClassSha256Schema,
    source_row_count: z.number().int().min(0),
    create_count: z.number().int().min(0),
    review_required_count: z.number().int().min(0),
    existing_conflict_count: z.number().int().min(0),
    existing_source_count: z.number().int().min(0),
    preview_fingerprint: ClientBeClassSha256Schema,
  })
  .strict();

export type ClientBeClassWorkbookPreview = z.infer<
  typeof ClientBeClassWorkbookPreviewSchema
>;

export const ClientBeClassWorkbookPreviewEnvelopeSchema = z
  .object({
    success: z.literal(true),
    message: z.string(),
    data: ClientBeClassWorkbookPreviewSchema,
    error: z.null(),
  })
  .strict();

export const ClientBeClassWorkbookReceiptSchema = z.object({
  source_content_digest: ClientBeClassSha256Schema,
  source_row_count: z.number().int().min(0),
  created_count: z.number().int().min(0),
  exact_replay_count: z.number().int().min(0),
  review_required_count: z.number().int().min(0),
  existing_conflict_count: z.number().int().min(0),
  existing_source_count: z.number().int().min(0),
  replayed_workbook: z.boolean(),
}).strict();

export type ClientBeClassWorkbookReceipt = z.infer<typeof ClientBeClassWorkbookReceiptSchema>;

export const ClientBeClassWorkbookReceiptEnvelopeSchema = z
  .object({ success: z.literal(true), message: z.string(), data: ClientBeClassWorkbookReceiptSchema, error: z.null() })
  .strict();
