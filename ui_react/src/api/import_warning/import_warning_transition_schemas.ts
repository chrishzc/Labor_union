/**
 * File: import_warning_transition_schemas.ts
 * Description: 定義匯入警示 transition Preview、Apply receipt 與 receipt lookup 的 strict Zod 契約。
 */

import { z } from 'zod';

export const ImportWarningTrackingStatusSchema = z.enum([
  'open',
  'awaiting_external_confirmation',
  'response_recorded',
  'reimport_requested',
  'closed',
  'auto_resolved',
]);

export const WarningTransitionRequestSchema = z.strictObject({
  expected_version: z.number().int().positive(),
  target_status: z.enum([
    'awaiting_external_confirmation',
    'response_recorded',
    'reimport_requested',
    'closed',
  ]),
  reason_code: z.string().trim().min(1).max(100),
  note: z.string().trim().max(500).nullable().optional(),
  evidence_reference: z.string().trim().max(191).nullable().optional(),
});

export const WarningTransitionPreviewSchema = z.strictObject({
  occurrence_identity: z.string().trim().min(1).max(191),
  expected_version: z.number().int().positive(),
  resulting_status: ImportWarningTrackingStatusSchema,
  resulting_version: z.number().int().min(2),
});

export const WarningTransitionReceiptSchema = z.strictObject({
  occurrence_identity: z.string().trim().min(1).max(191),
  before_status: ImportWarningTrackingStatusSchema,
  after_status: ImportWarningTrackingStatusSchema,
  resulting_version: z.number().int().min(2),
  receipt_identity: z.string().regex(/^[0-9a-f]{64}$/),
  correlation_id: z.string().trim().min(1).max(191),
  replayed: z.boolean(),
});

function responseSchema<T extends z.ZodTypeAny>(data: T) {
  return z.strictObject({
    success: z.literal(true),
    message: z.string(),
    data,
    error: z.string().nullable().optional(),
  });
}

export const WarningTransitionPreviewResponseSchema = responseSchema(WarningTransitionPreviewSchema);
export const WarningTransitionReceiptResponseSchema = responseSchema(WarningTransitionReceiptSchema);

export type ImportWarningTrackingStatus = z.infer<typeof ImportWarningTrackingStatusSchema>;
export type WarningTransitionRequest = z.infer<typeof WarningTransitionRequestSchema>;
export type WarningTransitionPreview = z.infer<typeof WarningTransitionPreviewSchema>;
export type WarningTransitionReceipt = z.infer<typeof WarningTransitionReceiptSchema>;
export type WarningTransitionPreviewResponse = z.infer<typeof WarningTransitionPreviewResponseSchema>;
export type WarningTransitionReceiptResponse = z.infer<typeof WarningTransitionReceiptResponseSchema>;

