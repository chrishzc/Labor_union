/**
 * File: client_over_refund_recovery_schemas.ts
 * Description: Client Finance recovery owner API 的 closed Zod request/response contracts。
 */
import { z } from 'zod';

const identity = z.string().trim().min(1).max(191);
const evidence = z.string().trim().min(1).max(500);
const fingerprint = z.string().regex(/^[0-9a-f]{64}$/);
const nonNegative = z.number().int().nonnegative();
const positive = z.number().int().positive();

export const ClientOverRefundRecoveryQuerySchema = z.strictObject({
  case_no: identity,
  recovery_identity: identity,
  remaining_amount_ntd: z.number().int().nonnegative(),
  status: z.enum(['open', 'partially_recovered', 'recovered', 'adjusted']),
  recovery_version: nonNegative,
  account_version: nonNegative,
  source_row_reference: identity,
  current_matchings: z.array(z.strictObject({
    matching_identity: identity,
    matching_version: positive,
    incoming_row_reference: identity,
  })).max(100),
}).superRefine((value, context) => {
  const terminal = value.status === 'recovered' || value.status === 'adjusted';
  if (terminal !== (value.remaining_amount_ntd === 0)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['status'], message: 'status 與 remaining 不符合 owner 完成條件' });
  }
  const ids = value.current_matchings.map((item) => item.matching_identity);
  if (new Set(ids).size !== ids.length) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['current_matchings'], message: 'matching identity 不得重複' });
  }
});

const recoveryBase = z.strictObject({ recovery_identity: identity, finance_import_row_id: positive });
export const ClientOverRefundRecoveryMatchingPreviewRequestSchema = recoveryBase.extend({ evidence_reference: evidence });
export const ClientOverRefundRecoveryMatchedPreviewRequestSchema = recoveryBase.extend({ matching_identity: identity, matching_version: positive, evidence_reference: evidence });
export const ClientOverRefundRecoveryAdjustmentPreviewRequestSchema = z.strictObject({ recovery_identity: identity, adjustment_amount_ntd: positive, evidence_reference: evidence });

export const ClientOverRefundRecoveryMatchingPreviewSchema = z.strictObject({
  recovery_identity: identity,
  finance_import_row_identity: identity,
  recovery_version: nonNegative,
  account_version: nonNegative,
  preview_fingerprint: fingerprint,
});
export const ClientOverRefundRecoveryPreviewSchema = z.strictObject({
  recovery_identity: identity,
  account_version: nonNegative,
  recovery_version: nonNegative,
  amount_received_ntd: positive,
  remaining_before_ntd: positive,
  remaining_after_ntd: nonNegative,
  resulting_status: z.enum(['open', 'partially_recovered', 'recovered', 'adjusted']),
  preview_fingerprint: fingerprint,
}).superRefine((value, context) => {
  if (value.remaining_after_ntd >= value.remaining_before_ntd) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['remaining_after_ntd'], message: 'owner preview 必須降低 remaining' });
  }
  const terminal = value.resulting_status === 'recovered' || value.resulting_status === 'adjusted';
  if (terminal !== (value.remaining_after_ntd === 0)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['resulting_status'], message: 'preview status 與 remaining 不符合完成條件' });
  }
});
export const ClientOverRefundRecoveryAdjustmentPreviewSchema = z.strictObject({
  recovery_identity: identity,
  account_version: nonNegative,
  recovery_version: nonNegative,
  adjustment_amount_ntd: positive,
  remaining_before_ntd: positive,
  remaining_after_ntd: nonNegative,
  resulting_status: z.enum(['open', 'partially_recovered', 'recovered', 'adjusted']),
  preview_fingerprint: fingerprint,
}).superRefine((value, context) => {
  if (value.adjustment_amount_ntd !== value.remaining_before_ntd - value.remaining_after_ntd) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['adjustment_amount_ntd'], message: 'adjustment 與 remaining 變化不一致' });
  }
  const terminal = value.resulting_status === 'recovered' || value.resulting_status === 'adjusted';
  if (terminal !== (value.remaining_after_ntd === 0)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['resulting_status'], message: 'preview status 與 remaining 不符合完成條件' });
  }
});

export const ClientOverRefundRecoveryReceiptSchema = z.strictObject({
  recovery_identity: identity,
  account_version: nonNegative,
  recovery_version: nonNegative,
  remaining_after_ntd: nonNegative,
  resulting_status: z.enum(['open', 'partially_recovered', 'recovered', 'adjusted']),
  evidence_reference: evidence.nullable().optional(),
}).superRefine((value, context) => {
  const terminal = value.resulting_status === 'recovered' || value.resulting_status === 'adjusted';
  if (terminal !== (value.remaining_after_ntd === 0)) context.addIssue({ code: z.ZodIssueCode.custom, path: ['resulting_status'], message: 'receipt status 與 remaining 不符合完成條件' });
});
export const ClientOverRefundRecoveryMatchingReceiptSchema = z.strictObject({
  matching_identity: identity,
  matching_version: positive,
  recovery_identity: identity,
  finance_import_row_identity: identity,
  recovery_version: nonNegative,
  account_version: nonNegative,
  evidence_reference: evidence.nullable().optional(),
});

export const ClientOverRefundRecoveryResponseSchema = <T extends z.ZodTypeAny>(data: T) => z.strictObject({ success: z.literal(true), message: z.string(), data, error: z.string().nullable().optional() });

export type ClientOverRefundRecoveryQuery = z.infer<typeof ClientOverRefundRecoveryQuerySchema>;
export type ClientOverRefundRecoveryMatchingPreviewRequest = z.infer<typeof ClientOverRefundRecoveryMatchingPreviewRequestSchema>;
export type ClientOverRefundRecoveryMatchedPreviewRequest = z.infer<typeof ClientOverRefundRecoveryMatchedPreviewRequestSchema>;
export type ClientOverRefundRecoveryAdjustmentPreviewRequest = z.infer<typeof ClientOverRefundRecoveryAdjustmentPreviewRequestSchema>;
export type ClientOverRefundRecoveryMatchingPreview = z.infer<typeof ClientOverRefundRecoveryMatchingPreviewSchema>;
export type ClientOverRefundRecoveryPreview = z.infer<typeof ClientOverRefundRecoveryPreviewSchema>;
export type ClientOverRefundRecoveryAdjustmentPreview = z.infer<typeof ClientOverRefundRecoveryAdjustmentPreviewSchema>;
export type ClientOverRefundRecoveryReceipt = z.infer<typeof ClientOverRefundRecoveryReceiptSchema>;
export type ClientOverRefundRecoveryMatchingReceipt = z.infer<typeof ClientOverRefundRecoveryMatchingReceiptSchema>;
