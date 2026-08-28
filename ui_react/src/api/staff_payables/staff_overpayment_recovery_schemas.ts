/**
 * File: staff_overpayment_recovery_schemas.ts
 * Description: Staff overpayment recovery 的封閉 Query／Preview／Receipt Zod 契約。
 */
import { z } from 'zod';

const identity = z.string().trim().min(1).max(191);
const positive = z.number().int().positive();
const nonnegative = z.number().int().nonnegative();
const fingerprint = z.string().regex(/^[0-9a-f]{64}$/);

const matching = z.strictObject({
  matching_identity: identity,
  matching_version: positive,
  finance_import_row_identity: identity,
});

export const StaffOverpaymentRecoveryQuerySchema = z.strictObject({
  staff_id: positive,
  recovery_identity: identity,
  remaining_amount_ntd: nonnegative,
  status: z.enum(['open', 'partially_recovered', 'recovered', 'adjusted']),
  recovery_version: nonnegative,
  staff_payables_version: nonnegative,
  source_bank_fact_references: z.array(identity),
  source_payout_event_references: z.array(identity),
  source_obligation_references: z.array(identity),
  matchings: z.array(matching),
}).superRefine((value, context) => {
  const active = value.status === 'open' || value.status === 'partially_recovered';
  if (active !== (value.remaining_amount_ntd > 0)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['remaining_amount_ntd'], message: 'remaining 與 status 不一致。' });
  }
  const matchingIdentities = value.matchings.map((item) => item.matching_identity);
  if (new Set(matchingIdentities).size !== matchingIdentities.length) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['matchings'], message: 'current matching 不可重複。' });
  }
});

const evidence = identity;
const recoveryIdentity = identity;

export const StaffOverpaymentRecoveryMatchingPreviewSchema = z.strictObject({
  recovery_identity: recoveryIdentity,
  staff_id: positive,
  finance_import_row_identity: identity,
  recovery_version: nonnegative,
  staff_payables_version: nonnegative,
  preview_fingerprint: fingerprint,
});

export const StaffOverpaymentRecoveryMatchingReceiptSchema = z.strictObject({
  matching_identity: identity,
  matching_version: positive,
  recovery_identity: recoveryIdentity,
  staff_id: positive,
  finance_import_row_identity: identity,
  recovery_version: nonnegative,
  staff_payables_version: nonnegative,
  evidence_reference: evidence.nullable().optional(),
});

export const StaffOverpaymentRecoveryCollectionPreviewSchema = z.strictObject({
  recovery_identity: recoveryIdentity,
  recovery_version: nonnegative,
  staff_payables_version: nonnegative,
  received_amount_ntd: positive,
  remaining_before_ntd: positive,
  remaining_after_ntd: nonnegative,
  resulting_status: z.enum(['open', 'partially_recovered', 'recovered']),
  preview_fingerprint: fingerprint,
}).superRefine((value, context) => {
  if (value.remaining_after_ntd !== Math.max(0, value.remaining_before_ntd - value.received_amount_ntd)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['remaining_after_ntd'], message: '收款後 remaining 不符合 owner 計算。' });
  }
  if ((value.resulting_status === 'recovered') !== (value.remaining_after_ntd === 0)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['resulting_status'], message: '收款狀態與 remaining 不一致。' });
  }
});

export const StaffOverpaymentRecoveryAdjustmentPreviewSchema = z.strictObject({
  recovery_identity: recoveryIdentity,
  recovery_version: nonnegative,
  staff_payables_version: nonnegative,
  adjustment_amount_ntd: positive,
  remaining_before_ntd: positive,
  remaining_after_ntd: z.literal(0),
  resulting_status: z.literal('adjusted'),
  preview_fingerprint: fingerprint,
}).superRefine((value, context) => {
  if (value.adjustment_amount_ntd !== value.remaining_before_ntd) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['adjustment_amount_ntd'], message: 'Staff adjustment 必須等於 fresh remaining。' });
  }
});

export const StaffOverpaymentRecoveryReceiptSchema = z.strictObject({
  recovery_identity: recoveryIdentity,
  recovery_version: nonnegative,
  staff_payables_version: nonnegative,
  remaining_after_ntd: nonnegative,
  resulting_status: z.enum(['open', 'partially_recovered', 'recovered', 'adjusted']),
  preview_fingerprint: fingerprint,
  evidence_reference: evidence.nullable().optional(),
}).superRefine((value, context) => {
  const active = value.resulting_status === 'open' || value.resulting_status === 'partially_recovered';
  if (active !== (value.remaining_after_ntd > 0)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['remaining_after_ntd'], message: 'receipt remaining 與 status 不一致。' });
  }
});

export type StaffOverpaymentRecoveryQuery = z.infer<typeof StaffOverpaymentRecoveryQuerySchema>;
export type StaffOverpaymentRecoveryMatchingPreview = z.infer<typeof StaffOverpaymentRecoveryMatchingPreviewSchema>;
export type StaffOverpaymentRecoveryMatchingReceipt = z.infer<typeof StaffOverpaymentRecoveryMatchingReceiptSchema>;
export type StaffOverpaymentRecoveryCollectionPreview = z.infer<typeof StaffOverpaymentRecoveryCollectionPreviewSchema>;
export type StaffOverpaymentRecoveryAdjustmentPreview = z.infer<typeof StaffOverpaymentRecoveryAdjustmentPreviewSchema>;
export type StaffOverpaymentRecoveryReceipt = z.infer<typeof StaffOverpaymentRecoveryReceiptSchema>;

export type StaffOverpaymentRecoveryPreview =
  | StaffOverpaymentRecoveryMatchingPreview
  | StaffOverpaymentRecoveryCollectionPreview
  | StaffOverpaymentRecoveryAdjustmentPreview;

export function staffOverpaymentRecoveryEnvelope<T extends z.ZodTypeAny>(data: T) {
  return z.strictObject({ success: z.literal(true), message: z.string(), data, error: z.null().optional() });
}
