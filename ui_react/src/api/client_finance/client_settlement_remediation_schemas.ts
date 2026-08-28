/**
 * File: client_settlement_remediation_schemas.ts
 * Description: 客戶應收、退款與補助退還 Query／Preview／Apply strict 契約。
 */
import { z } from 'zod';

const identity = z.string().trim().min(1).max(191);
const fingerprint = z.string().regex(/^[0-9a-f]{64}$/);
const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const money = z.strictObject({ amount: z.number().int().nonnegative() });
const stage = z.enum(['deposit', 'first', 'second', 'adjustment']);

const receivableObligation = z.strictObject({
  obligation_identity: identity,
  payment_stage: stage,
  amount_due_ntd: z.number().int().positive(),
  due_date: date,
});
const payableObligation = z.strictObject({
  obligation_identity: identity,
  obligation_type: z.enum(['adjustment', 'refund', 'subsidy_return']),
  amount_due_ntd: z.number().int().positive(),
  due_date: date,
});
const incomingBankFact = z.strictObject({
  finance_import_row_id: z.number().int().positive(), amount_ntd: z.number().int().positive(), transaction_date: date,
});
const outgoingBankFact = incomingBankFact.extend({ eligible_obligation_identities: z.array(identity).min(1) }).strict();

export const ClientSettlementQuerySchema = z.strictObject({
  case_no: identity,
  account_version: z.number().int().nonnegative(),
  as_of: date,
  receivable_obligations: z.array(receivableObligation),
  refund_obligations: z.array(payableObligation),
  subsidy_return_obligations: z.array(payableObligation),
  incoming_bank_facts: z.array(incomingBankFact),
  refund_bank_facts: z.array(outgoingBankFact),
  subsidy_return_bank_facts: z.array(outgoingBankFact),
});

const receiptAllocation = z.strictObject({ bank_fact_identity: identity, obligation_identity: identity, amount: money });
export const ClientReceiptPreviewSchema = z.strictObject({
  account_version: z.number().int().nonnegative(),
  candidate: z.strictObject({
    status: z.enum(['exact', 'overage', 'review_required']), payment_stage: stage,
    bank_total: money, obligation_total: money, overage_amount: money,
    allocations: z.array(receiptAllocation), blockers: z.array(identity), settlement_identity: fingerprint,
  }),
  preview_fingerprint: fingerprint,
});

const correctionEntry = z.strictObject({
  identity, entry_type: z.enum(['refund', 'subsidy_return']), amount: money, occurred_on: date,
  reversal_of_entry_identity: identity.nullable(), finance_import_row_identity: identity,
});
const correctionAllocation = z.strictObject({ entry_identity: identity, obligation_identity: identity, amount: money });
export const ClientPayablePreviewSchema = z.strictObject({
  account_version: z.number().int().nonnegative(),
  candidate: z.strictObject({
    correction_type: z.literal('refund'), case_no: identity, amount: money,
    entries: z.array(correctionEntry), allocations: z.array(correctionAllocation),
    affected_obligations: z.array(identity), reversal_entry_type: z.null(), recovery_amount: money,
    fingerprint,
  }),
  preview_fingerprint: fingerprint,
});

export const ClientReceiptReceiptSchema = z.strictObject({
  case_no: identity, account_version: z.number().int().nonnegative(),
  status: z.enum(['exact', 'overage', 'review_required']), settlement_identity: fingerprint,
  ledger_entry_count: z.number().int().nonnegative(), allocation_count: z.number().int().nonnegative(), blockers: z.array(identity),
});
export const ClientPayableReceiptSchema = z.strictObject({
  case_no: identity, correction_type: z.literal('refund'), account_version: z.number().int().nonnegative(),
  correction_identity: fingerprint, ledger_entry_count: z.number().int().nonnegative(),
  allocation_count: z.number().int().nonnegative(), affected_obligations: z.array(identity),
});

function envelope<T extends z.ZodTypeAny>(schema: T) {
  return z.strictObject({ success: z.literal(true), message: z.string(), data: schema, error: z.string().nullable().optional() });
}
export const ClientSettlementQueryResponseSchema = envelope(ClientSettlementQuerySchema);
export const ClientReceiptPreviewResponseSchema = envelope(ClientReceiptPreviewSchema);
export const ClientPayablePreviewResponseSchema = envelope(ClientPayablePreviewSchema);
export const ClientReceiptReceiptResponseSchema = envelope(ClientReceiptReceiptSchema);
export const ClientPayableReceiptResponseSchema = envelope(ClientPayableReceiptSchema);

export type ClientSettlementQuery = z.infer<typeof ClientSettlementQuerySchema>;
export type ClientReceiptPreview = z.infer<typeof ClientReceiptPreviewSchema>;
export type ClientPayablePreview = z.infer<typeof ClientPayablePreviewSchema>;
export type ClientReceiptReceipt = z.infer<typeof ClientReceiptReceiptSchema>;
export type ClientPayableReceipt = z.infer<typeof ClientPayableReceiptSchema>;
export type ClientPaymentStage = z.infer<typeof stage>;
