/**
 * File: schemas.ts
 * Description: 定義Client BeClass工作簿Preview／Apply的嚴格成功信封與aggregate DTO。
 */
import { z } from 'zod';

export const ClientBeClassSha256Schema = z
  .string()
  .regex(/^[0-9a-f]{64}$/, '預期 64 位小寫 Hex SHA-256');

const ClientBeClassPairingSchema = z.strictObject({
  source_row: z.number().int().min(2),
  case_no: z.string().min(1).max(50),
});
export type ClientBeClassPairing = z.infer<typeof ClientBeClassPairingSchema>;

const ClientBeClassManualRowSchema = z.strictObject({
  source_row: z.number().int().min(2),
  query_no: z.string(),
  name: z.string(),
  masked_phone: z.string(),
  city: z.string().nullable(),
  submitted_at: z.string().nullable(),
  case_nos: z.array(z.string()).min(1),
});

const ClientBeClassCandidateSchema = z.strictObject({
  case_no: z.string(),
  client_id: z.number().int().positive(),
  name: z.string(),
  masked_phone: z.string(),
  city: z.string().nullable(),
  created_at: z.string().nullable(),
  start_date: z.string().nullable(),
});

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
    row_issues: z.array(z.strictObject({
      source_row: z.number().int().min(1),
      query_no: z.string().max(100).nullable(),
      fields: z.array(z.string()),
      issue_codes: z.array(z.string()),
    })).optional(),
    manual_rows: z.array(ClientBeClassManualRowSchema).optional(),
    candidates: z.array(ClientBeClassCandidateSchema).optional(),
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
  manual_bindings: z.array(ClientBeClassPairingSchema.extend({ query_no: z.string() })).optional(),
  row_issues: z.array(z.strictObject({
    source_row: z.number().int().positive(),
    query_no: z.string().max(100).nullable(),
    fields: z.array(z.string()),
    issue_codes: z.array(z.string()),
  })).nullable().optional(),
}).strict();

export type ClientBeClassWorkbookReceipt = z.infer<typeof ClientBeClassWorkbookReceiptSchema>;

export const ClientBeClassWorkbookReceiptEnvelopeSchema = z
  .object({ success: z.literal(true), message: z.string(), data: ClientBeClassWorkbookReceiptSchema, error: z.null() })
  .strict();
