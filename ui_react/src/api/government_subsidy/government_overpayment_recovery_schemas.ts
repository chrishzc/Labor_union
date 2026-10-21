/**
 * File: government_overpayment_recovery_schemas.ts
 * Description: 政府溢撥處置的 strict Query／Preview／Apply Zod 契約。
 */
import { z } from 'zod';

const FingerprintSchema = z.string().regex(/^[0-9a-f]{64}$/);
const IdentitySchema = z.string().trim().min(1).max(191);
const ReasonSchema = z.string().trim().max(500);
const EvidenceSchema = z.string().trim().min(1).max(500);

export const GovernmentOverpaymentStatusSchema = z.enum([
  'pending_review',
  'offset_reserved',
  'offset_applied',
]);

export const GovernmentOverpaymentDispositionSchema = z.enum(['offset']);

export const GovernmentOverpaymentOffsetTargetSchema = z.strictObject({
  claim_item_id: z.number().int().positive(),
  claim_batch_id: z.number().int().positive(),
  batch_version: z.number().int().nonnegative(),
  outstanding_amount_ntd: z.number().int().positive(),
  payer_identity: z.literal('hccg'),
});

export const GovernmentOverpaymentQuerySchema = z.strictObject({
  overpayment_identity: IdentitySchema,
  payer_identity: z.literal('hccg'),
  remaining_amount_ntd: z.number().int().nonnegative(),
  status: GovernmentOverpaymentStatusSchema,
  overpayment_version: z.number().int().nonnegative(),
  source_bank_fact_reference: IdentitySchema,
  source_transaction_reference: IdentitySchema,
  offset_targets: z.array(GovernmentOverpaymentOffsetTargetSchema),
  blockers: z.array(z.string()),
  available_actions: z.array(GovernmentOverpaymentDispositionSchema),
}).superRefine((query, context) => {
  if (query.remaining_amount_ntd === 0 && !['offset_applied'].includes(query.status)) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: '溢撥剩餘金額與狀態不一致。' });
  }
  const ids = query.offset_targets.map((target) => target.claim_item_id);
  if (new Set(ids).size !== ids.length) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: '抵扣標的重複。' });
  }
});

export const GovernmentOverpaymentDispositionPreviewRequestSchema = z.strictObject({
  overpayment_identity: IdentitySchema,
  disposition: GovernmentOverpaymentDispositionSchema,
  targets: z.array(z.strictObject({
    claim_item_id: z.number().int().positive(),
    amount_ntd: z.number().int().positive(),
  })),
  evidence_reference: EvidenceSchema,
});

export const GovernmentOverpaymentDispositionApplyRequestSchema = GovernmentOverpaymentDispositionPreviewRequestSchema.extend({
  expected_overpayment_version: z.number().int().nonnegative(),
  preview_fingerprint: FingerprintSchema,
  reason: ReasonSchema.default(''),
}).strict();

export const GovernmentOverpaymentPreviewSchema = z.strictObject({
  overpayment_identity: IdentitySchema,
  overpayment_version: z.number().int().nonnegative(),
  remaining_before_ntd: z.number().int().nonnegative(),
  disposition_amount_ntd: z.number().int().positive(),
  remaining_after_ntd: z.number().int().nonnegative(),
  resulting_status: GovernmentOverpaymentStatusSchema,
  disposition_kind: GovernmentOverpaymentDispositionSchema,
  preview_fingerprint: FingerprintSchema,
});

export const GovernmentOverpaymentReceiptSchema = z.strictObject({
  overpayment_identity: IdentitySchema,
  remaining_after_ntd: z.number().int().nonnegative(),
  status: GovernmentOverpaymentStatusSchema,
  preview_fingerprint: FingerprintSchema,
});

function envelope<T extends z.ZodTypeAny>(data: T) {
  return z.strictObject({
    success: z.literal(true),
    message: z.string(),
    data,
    error: z.null(),
  });
}

export const GovernmentOverpaymentQueryResponseSchema = envelope(GovernmentOverpaymentQuerySchema);
export const GovernmentOverpaymentPreviewResponseSchema = envelope(GovernmentOverpaymentPreviewSchema);
export const GovernmentOverpaymentReceiptResponseSchema = envelope(GovernmentOverpaymentReceiptSchema);

export type GovernmentOverpaymentQuery = z.infer<typeof GovernmentOverpaymentQuerySchema>;
export type GovernmentOverpaymentDispositionPreviewRequest = z.infer<typeof GovernmentOverpaymentDispositionPreviewRequestSchema>;
export type GovernmentOverpaymentDispositionApplyRequest = z.infer<typeof GovernmentOverpaymentDispositionApplyRequestSchema>;
export type GovernmentOverpaymentPreview = z.infer<typeof GovernmentOverpaymentPreviewSchema>;
export type GovernmentOverpaymentReceipt = z.infer<typeof GovernmentOverpaymentReceiptSchema>;
export type GovernmentOverpaymentDisposition = z.infer<typeof GovernmentOverpaymentDispositionSchema>;
