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
