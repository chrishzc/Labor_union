/**
 * File: government_overpayment_recovery_schemas.ts
 * Description: 政府溢撥處置的 strict Query／Preview／Apply Zod 契約。
 */
import { z } from 'zod';

const FingerprintSchema = z.string().regex(/^[0-9a-f]{64}$/);
const IdentitySchema = z.string().trim().min(1).max(191);
const ReasonSchema = z.string().trim().min(1).max(500);
const EvidenceSchema = z.string().trim().min(1).max(500);
const IsoDateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);

export const GovernmentOverpaymentStatusSchema = z.enum([
  'pending_review',
  'offset_reserved',
  'offset_applied',
  'return_payable',
  'partially_returned',
  'returned',
]);

export const GovernmentOverpaymentDispositionSchema = z.enum(['offset', 'return']);

export const GovernmentOverpaymentOffsetTargetSchema = z.strictObject({
  claim_item_id: z.number().int().positive(),
  claim_batch_id: z.number().int().positive(),
  batch_version: z.number().int().nonnegative(),
  outstanding_amount_ntd: z.number().int().positive(),
  payer_identity: z.literal('hccg'),
});

export const GovernmentOverpaymentReturnRecipientSchema = z.strictObject({
  ready: z.boolean(),
  blockers: z.array(z.string()),
  agency_identity: IdentitySchema.nullable(),
  agency_name: IdentitySchema.nullable(),
  bank_code: IdentitySchema.nullable(),
  account_display: IdentitySchema.nullable(),
  account_fingerprint: FingerprintSchema.nullable(),
  effective_date: IsoDateSchema.nullable(),
}).superRefine((recipient, context) => {
  const details = [
    recipient.agency_identity,
    recipient.agency_name,
    recipient.bank_code,
    recipient.account_display,
    recipient.account_fingerprint,
    recipient.effective_date,
  ];
  if (recipient.ready && (recipient.blockers.length > 0 || details.some((value) => value === null))) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: '可用退款對象資料不完整。' });
  }
  if (!recipient.ready && details.some((value) => value !== null)) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: '不可用退款對象不得回傳帳戶資料。' });
  }
});

export const GovernmentOverpaymentReturnExcessRecoveryQuerySchema = z.strictObject({
  recovery_identity: IdentitySchema,
  source_bank_fact_reference: IdentitySchema,
  source_payout_reference: IdentitySchema,
  original_amount_ntd: z.number().int().positive(),
  remaining_amount_ntd: z.number().int().nonnegative(),
  status: z.enum(['open', 'partially_recovered', 'recovered']),
  recovery_version: z.number().int().nonnegative(),
}).superRefine((recovery, context) => {
  if (recovery.remaining_amount_ntd > recovery.original_amount_ntd) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: '超額回收剩餘金額不合法。' });
  }
  if (recovery.remaining_amount_ntd === 0 && recovery.status !== 'recovered') {
    context.addIssue({ code: z.ZodIssueCode.custom, message: '超額回收狀態與剩餘金額不一致。' });
  }
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
  return_recipient: GovernmentOverpaymentReturnRecipientSchema,
  blockers: z.array(z.string()),
  available_actions: z.array(GovernmentOverpaymentDispositionSchema),
  return_excess_recovery: GovernmentOverpaymentReturnExcessRecoveryQuerySchema.nullable().optional(),
}).superRefine((query, context) => {
  if (query.remaining_amount_ntd === 0 && !['offset_applied', 'returned'].includes(query.status)) {
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
  due_date: IsoDateSchema.nullable().optional(),
  evidence_reference: EvidenceSchema,
});

export const GovernmentOverpaymentDispositionApplyRequestSchema = GovernmentOverpaymentDispositionPreviewRequestSchema.extend({
  expected_overpayment_version: z.number().int().nonnegative(),
  preview_fingerprint: FingerprintSchema,
  reason: ReasonSchema,
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
  payable_identity: IdentitySchema.nullable(),
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
