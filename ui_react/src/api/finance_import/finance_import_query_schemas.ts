/**
 * File: finance_import_query_schemas.ts
 * Description: 定義Finance Import batches、manifest、review與reprocess唯讀Zod契約。
 */
import { z } from 'zod';
const FingerprintSchema = z.string().regex(/^[0-9a-f]{64}$/);
export const FinanceImportBatchSummarySchema = z.strictObject({ batch_id: z.number().int().positive(), batch_identity: z.string().nullable(), format_id: z.string(), source_file: z.string().nullable(), row_count: z.number().int().nonnegative(), status: z.string(), batch_version: z.number().int().nonnegative().nullable(), architecture_ready: z.boolean(), created_at: z.string() });
export const FinanceImportManifestSchema = z.strictObject({ batch_id: z.number().int().positive(), batch_identity: z.string(), format_id: z.string(), source_file: z.string().nullable(), sheet_name: z.string(), header_row: z.number().int().positive(), source_row_count: z.number().int().nonnegative(), status: z.string(), batch_version: z.number().int().nonnegative(), source_content_digest: FingerprintSchema, classifier_version: z.string(), fingerprint_version: z.string(), canonical_row_count: z.number().int().nonnegative(), occurrence_count: z.number().int().nonnegative(), review_count: z.number().int().nonnegative(), dispatch_event_count: z.number().int().nonnegative(), reconciliation_receipt_count: z.number().int().nonnegative(), created_at: z.string(), completed_at: z.string().nullable() });
export const FinanceImportReviewPageSchema = z.strictObject({ batch_identity: z.string(), source_reviews: z.array(z.strictObject({ review_id: z.number().int().positive(), review_identity: z.string(), source_sheet: z.string(), source_row: z.number().int().positive(), issue_codes: z.array(z.string()), created_at: z.string() })), next_after_source_review_id: z.number().int().positive().nullable(), items: z.array(z.strictObject({ row_id: z.number().int().positive(), row_identity: z.string(), transaction_date: z.string().nullable(), direction: z.string(), amount_ntd: z.number().int().positive(), classification_type: z.string(), bank_type: z.enum(['receivable', 'payable', 'government_subsidy', 'subsidy_return', 'review', 'legacy']).optional(), disposition: z.string(), reconciliation_status: z.string(), source_sheet: z.string(), source_row: z.number().int().positive(), occurrence_count: z.number().int().positive(), available_actions: z.array(z.string()), created_at: z.string() })), next_after_row_id: z.number().int().positive().nullable() });
export const FinanceImportRunPageSchema = z.strictObject({ items: z.array(z.strictObject({ run_id: z.number().int().positive(), batch_identity: z.string(), classifier_version: z.string(), plan_fingerprint: FingerprintSchema, selected_count: z.number().int().nonnegative(), changed_count: z.number().int().nonnegative(), dispatch_count: z.number().int().nonnegative(), reconciled_count: z.number().int().nonnegative(), pending_count: z.number().int().nonnegative(), status: z.string(), created_at: z.string(), completed_at: z.string() })), next_before_run_id: z.number().int().positive().nullable() });
export const FinanceImportBatchListResponseSchema = z.strictObject({ success: z.boolean(), message: z.string(), data: z.array(FinanceImportBatchSummarySchema), error: z.string().nullable().optional() });
export function financeEnvelope<T extends z.ZodTypeAny>(schema: T) { return z.strictObject({ success: z.boolean(), message: z.string(), data: schema, error: z.string().nullable().optional() }); }
export type FinanceImportBatchSummary = z.infer<typeof FinanceImportBatchSummarySchema>;
export type FinanceImportManifest = z.infer<typeof FinanceImportManifestSchema>;
export type FinanceImportReviewPage = z.infer<typeof FinanceImportReviewPageSchema>;
export type FinanceImportRunPage = z.infer<typeof FinanceImportRunPageSchema>;

const bankSchema = z.enum(['sinopac', 'taishin']);
const optionalCount = z.number().int().nonnegative().nullable();
export const FinanceClientReceiptReviewSchema = z.strictObject({
  reason: z.string(),
  candidates: z.array(z.strictObject({ obligation_identity: z.string(), obligation_type: z.string(), due_date: z.iso.date().nullable() })),
});
export const FinanceBankTransactionPageSchema = z.strictObject({
  items: z.array(z.strictObject({
    row_id: z.number().int().positive(), row_identity: z.string(), transaction_date: z.string().nullable(),
    bank: bankSchema, direction: z.enum(['incoming', 'outgoing', 'unknown']), amount_ntd: z.number().int().positive(),
    classification_type: z.string(), status: z.enum(['pending', 'posted']), disposition: z.string(),
    review_reason: z.string().nullable(), available_actions: z.array(z.string()),
    dispatch_reason: z.string().nullish(),
    recorded_client_receipt_review: FinanceClientReceiptReviewSchema.nullish(),
    recorded_pending_reason: z.string().nullish(),
    reference: z.string(), counterparty_name: z.string().nullable(), cases: z.array(z.string()),
    reconciliation_target: z.strictObject({
      case_no: z.string(), obligation_identities: z.array(z.string()), staff_id: z.number().int().positive().nullable(),
      requires_selection: z.boolean().optional(),
    }).nullish(),
    reconciliation_unavailable_reason: z.string().nullish(),
    staff_subsidy_batch_identity: z.string().nullish(),
  })),
  pending_count: optionalCount,
  next_before_row_id: z.number().int().positive().nullable(),
});
export const FinanceImportHistoryPageSchema = z.strictObject({
  items: z.array(z.strictObject({
    identity: z.string(), started_at: z.string(), bank: bankSchema.nullable(),
    source_file: z.string().nullable(), status: z.enum(['saved', 'posting', 'posted', 'blocked', 'posting_failed', 'failed', 'legacy']),
    new_count: optionalCount, duplicate_count: optionalCount, reconciled_count: optionalCount,
    pending_count: optionalCount, source_warning_count: optionalCount, error_code: z.string().nullable(),
  })),
  next_before: z.string().nullable(),
});
export type FinanceBankTransactionPage = z.infer<typeof FinanceBankTransactionPageSchema>;
export type FinanceBankTransaction = FinanceBankTransactionPage['items'][number];
export type FinanceImportHistoryPage = z.infer<typeof FinanceImportHistoryPageSchema>;
