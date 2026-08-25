/**
 * File: line_runtime_target_schemas.ts
 * Description: 定義 LINE runtime alert target 查詢、候選與 mutation receipt 的 strict Zod 契約。
 */

import { z } from 'zod';

export const LineRuntimeTargetStateSchema = z.enum(['active', 'disabled']);
export const LineRuntimeMinimumStatusSchema = z.enum(['warning', 'critical']);

export const LineRuntimeTargetSchema = z.strictObject({
  target_id: z.number().int().positive(),
  target_kind: z.enum(['group', 'admin_user']),
  display_label: z.string(),
  state: LineRuntimeTargetStateSchema,
  minimum_status: LineRuntimeMinimumStatusSchema,
  current_version: z.string(),
  updated_at: z.string().datetime({ offset: true }),
});

export const LineRuntimeAdminCandidateSchema = z.strictObject({
  candidate_id: z.number().int().positive(),
  display_label: z.string(),
  line_linked: z.boolean(),
});

const CommandIdentityShape = {
  reason: z.string().trim().min(1).max(500),
  idempotency_key: z.string().trim().min(1).max(191),
  correlation_id: z.string().trim().min(1).max(191),
};

export const LineRuntimeAdminTargetRequestSchema = z.strictObject({
  admin_user_id: z.number().int().positive(),
  minimum_status: LineRuntimeMinimumStatusSchema,
  ...CommandIdentityShape,
});
export const LineRuntimeAdminTargetApplyRequestSchema = LineRuntimeAdminTargetRequestSchema.extend({
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
}).strict();

export const LineRuntimeGroupResetRequestSchema = z.strictObject({
  expected_version: z.string().trim().min(1).max(191),
  ...CommandIdentityShape,
});
export const LineRuntimeGroupResetApplyRequestSchema = LineRuntimeGroupResetRequestSchema.extend({
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
}).strict();

export const LineRuntimeTargetEnabledRequestSchema = z.strictObject({
  expected_version: z.string().trim().min(1).max(191),
  enabled: z.boolean(),
  ...CommandIdentityShape,
});
export const LineRuntimeTargetEnabledApplyRequestSchema = LineRuntimeTargetEnabledRequestSchema.extend({
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
}).strict();

export const LineRuntimeTargetPreviewSchema = z.strictObject({
  operation: z.enum(['group_reset', 'enable', 'disable', 'admin_target_add']),
  target_id: z.number().int().positive().nullable(),
  previous_state: z.enum(['absent', 'active', 'disabled']),
  resulting_state: LineRuntimeTargetStateSchema,
  current_version: z.string(),
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
  apply_ready: z.literal(true),
});

export const LineRuntimeTargetReceiptSchema = z.strictObject({
  receipt_id: z.string(),
  command_family: z.literal('line_alert_target'),
  operation: z.enum(['group_reset', 'enable', 'disable', 'admin_target_add']),
  target_id: z.number().int().positive(),
  previous_state: LineRuntimeTargetStateSchema,
  resulting_state: LineRuntimeTargetStateSchema,
  current_version: z.string(),
  replayed: z.boolean(),
  correlation_id: z.string(),
  committed_at: z.string().datetime({ offset: true }),
});

function envelope<T extends z.ZodTypeAny>(data: T) {
  return z.strictObject({ success: z.literal(true), message: z.string(), data, error: z.null() });
}

export const LineRuntimeTargetsResponseSchema = envelope(z.array(LineRuntimeTargetSchema));
export const LineRuntimeAdminCandidatesResponseSchema = envelope(z.array(LineRuntimeAdminCandidateSchema));
export const LineRuntimeTargetReceiptResponseSchema = envelope(LineRuntimeTargetReceiptSchema);
export const LineRuntimeTargetPreviewResponseSchema = envelope(LineRuntimeTargetPreviewSchema);

export type LineRuntimeTarget = z.infer<typeof LineRuntimeTargetSchema>;
export type LineRuntimeAdminCandidate = z.infer<typeof LineRuntimeAdminCandidateSchema>;
export type LineRuntimeAdminTargetRequest = z.infer<typeof LineRuntimeAdminTargetRequestSchema>;
export type LineRuntimeAdminTargetApplyRequest = z.infer<typeof LineRuntimeAdminTargetApplyRequestSchema>;
export type LineRuntimeGroupResetRequest = z.infer<typeof LineRuntimeGroupResetRequestSchema>;
export type LineRuntimeGroupResetApplyRequest = z.infer<typeof LineRuntimeGroupResetApplyRequestSchema>;
export type LineRuntimeTargetEnabledRequest = z.infer<typeof LineRuntimeTargetEnabledRequestSchema>;
export type LineRuntimeTargetEnabledApplyRequest = z.infer<typeof LineRuntimeTargetEnabledApplyRequestSchema>;
export type LineRuntimeTargetReceipt = z.infer<typeof LineRuntimeTargetReceiptSchema>;
export type LineRuntimeTargetPreview = z.infer<typeof LineRuntimeTargetPreviewSchema>;
