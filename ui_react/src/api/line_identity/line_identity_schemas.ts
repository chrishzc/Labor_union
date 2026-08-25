/**
 * File: line_identity_schemas.ts
 * Description: 定義 LINE 身分查詢、審核、對象更正、解除與人工維護操作的嚴格 Zod 公開契約。
 */
import { z } from 'zod';

export const LineBindingSubjectTypeSchema = z.enum([
  'customer',
  'staff',
  'admin',
]);

export const LineIdentityBindingStatusSchema = z.enum([
  'unbound',
  'pending_review',
  'bound',
  'revocation_pending',
  'revoked',
]);

export const LineIdentityRevocationStatusSchema = z.enum([
  'pending_menu_reset',
  'menu_reset_failed',
  'completed',
  'manual_completed',
]);

export const LineIdentityReviewTypeSchema = z.enum([
  'client_rebind',
  'staff_verification',
  'admin_binding',
]);

export const LineIdentityReviewStatusSchema = z.enum([
  'pending',
  'approved',
  'rejected',
  'cancelled',
  'expired',
]);

export const LineIdentityReviewDecisionSchema = z.enum([
  'approve',
  'reject',
]);

const NullableDateTimeSchema = z
  .string()
  .datetime({ offset: true, local: true })
  .nullable();

export const LineIdentityBindingViewSchema = z
  .object({
    line_user_id: z.string(),
    status: LineIdentityBindingStatusSchema,
    version: z.number().int(),
    subject_type: LineBindingSubjectTypeSchema,
    subject_reference: z.string(),
    subject_name: z.string(),
    updated_at: NullableDateTimeSchema.optional(),
    revocation_request_id: z.number().int().nullable().optional(),
    revocation_status: LineIdentityRevocationStatusSchema.nullable().optional(),
    revoked_at: NullableDateTimeSchema.optional(),
  })
  .strict();

export const LineIdentityBindingPageViewSchema = z
  .object({
    items: z.array(LineIdentityBindingViewSchema),
    total: z.number().int(),
    page: z.number().int(),
    page_size: z.number().int(),
  })
  .strict();

export const LineIdentityRevocationPreviewViewSchema = z
  .object({
    binding: LineIdentityBindingViewSchema,
    default_menu_publication_id: z.number().int().nullable().optional(),
    provider_menu_id: z.string().nullable().optional(),
    blockers: z.array(z.string()),
  })
  .strict();

export const LineIdentityReplacementPreviewViewSchema = z
  .object({
    binding: LineIdentityBindingViewSchema,
    target_subject_reference: z.string(),
    target_subject_name: z.string(),
    blockers: z.array(z.string()),
  })
  .strict();

export const LineIdentityRevocationApplyRequestSchema = z
  .object({
    expected_version: z.number().int().nonnegative(),
    reason: z.string().min(1).max(1000),
    idempotency_key: z.string().min(1).max(191),
    correlation_id: z.string().min(1).max(191),
  })
  .strict();

export const LineIdentityReplacementApplyRequestSchema = z
  .object({
    expected_version: z.number().int().nonnegative(),
    target_subject_reference: z.string().min(1).max(191),
    reason: z.string().min(1).max(1000),
    idempotency_key: z.string().min(1).max(191),
    correlation_id: z.string().min(1).max(191),
  })
  .strict();

export const LineIdentityRevocationActionRequestSchema = z
  .object({
    reason: z.string().min(1).max(1000),
  })
  .strict();

export const LineIdentityRevocationRequestViewSchema = z
  .object({
    request_id: z.number().int(),
    line_user_id: z.string(),
    subject_type: LineBindingSubjectTypeSchema,
    subject_reference: z.string(),
    status: LineIdentityRevocationStatusSchema,
    pending_binding_version: z.number().int(),
    publication_id: z.number().int(),
    provider_menu_id: z.string(),
    requested_by_actor_id: z.string(),
    reason: z.string(),
    attempt_count: z.number().int(),
    last_error_code: z.string().nullable().optional(),
    last_error_message: z.string().nullable().optional(),
  })
  .strict();

export const LineIdentityBindingListQuerySchema = z
  .object({
    status: LineIdentityBindingStatusSchema.optional(),
    subject_type: LineBindingSubjectTypeSchema.optional(),
    search: z.string().optional(),
    page: z.number().int().min(1).optional(),
    page_size: z.number().int().min(1).max(100).optional(),
  })
  .strict();

export const LineIdentityReviewViewSchema = z
  .object({
    request_id: z.number().int().positive(),
    review_type: LineIdentityReviewTypeSchema,
    status: LineIdentityReviewStatusSchema,
    version: z.number().int().nonnegative(),
    subject_type: LineBindingSubjectTypeSchema.nullable(),
    subject_reference: z.string().nullable(),
    assigned_admin_id: z.number().int().nullable(),
    due_at: NullableDateTimeSchema,
    line_user_id_masked: z.string(),
    display_name: z.string(),
    decision_reason: z.string().nullable(),
    reviewed_by_actor_id: z.string().nullable(),
    reviewed_at: NullableDateTimeSchema,
    created_at: NullableDateTimeSchema,
    outcome: z.enum(['created', 'existing']).nullable().optional(),
    receipt_identity: z.string().nullable().optional(),
  })
  .strict();

export const LineIdentityReviewPageViewSchema = z
  .object({
    items: z.array(LineIdentityReviewViewSchema),
    next_cursor: z.string().nullable(),
  })
  .strict();

export const LineIdentityReviewApplyViewSchema = LineIdentityReviewViewSchema
  .extend({
    outcome: z.enum(['created', 'existing']),
    receipt_identity: z.string().min(1),
  })
  .strict();

export const LineIdentityReviewSummaryViewSchema = z
  .object({
    pending_total: z.number().int().nonnegative(),
    staff_pending: z.number().int().nonnegative(),
    rebind_pending: z.number().int().nonnegative(),
    processed_today: z.number().int().nonnegative(),
    stale_pending: z.number().int().nonnegative(),
    stale_hours: z.number().int().positive(),
  })
  .strict();

export const LineIdentityReviewListQuerySchema = z
  .object({
    review_status: LineIdentityReviewStatusSchema.optional(),
    review_type: LineIdentityReviewTypeSchema.optional(),
    page_size: z.number().int().min(1).max(100).optional(),
    cursor: z.string().min(1).max(191).optional(),
  })
  .strict();

export const LineIdentityReviewPreviewRequestSchema = z
  .object({
    expected_version: z.number().int().nonnegative(),
    reason: z.string().min(1).max(1000),
  })
  .strict();

export const LineIdentityReviewPreviewViewSchema = z
  .object({
    request_id: z.number().int().positive(),
    decision: LineIdentityReviewDecisionSchema,
    before_status: LineIdentityReviewStatusSchema,
    after_status: LineIdentityReviewStatusSchema,
    expected_version: z.number().int().nonnegative(),
    resulting_version: z.number().int().nonnegative(),
    subject_type: LineBindingSubjectTypeSchema.nullable(),
    subject_reference: z.string().nullable(),
    line_user_id_masked: z.string(),
    preview_fingerprint: z.string().min(1),
  })
  .strict();

export const LineIdentityReviewApplyRequestSchema = z
  .object({
    expected_version: z.number().int().nonnegative(),
    idempotency_key: z.string().min(1).max(191),
    reason: z.string().min(1).max(1000),
    preview_fingerprint: z.string().min(1),
  })
  .strict();

export function createLineIdentityEnvelopeSchema<T extends z.ZodTypeAny>(
  dataSchema: T
) {
  return z
    .object({
      success: z.boolean(),
      message: z.string(),
      data: dataSchema.nullable(),
      error: z.string().nullable(),
    })
    .strict();
}

export type LineBindingSubjectType = z.infer<
  typeof LineBindingSubjectTypeSchema
>;
export type LineIdentityBindingStatus = z.infer<
  typeof LineIdentityBindingStatusSchema
>;
export type LineIdentityRevocationStatus = z.infer<
  typeof LineIdentityRevocationStatusSchema
>;
export type LineIdentityBindingView = z.infer<
  typeof LineIdentityBindingViewSchema
>;
export type LineIdentityBindingPageView = z.infer<
  typeof LineIdentityBindingPageViewSchema
>;
export type LineIdentityRevocationPreviewView = z.infer<
  typeof LineIdentityRevocationPreviewViewSchema
>;
export type LineIdentityReplacementPreviewView = z.infer<
  typeof LineIdentityReplacementPreviewViewSchema
>;
export type LineIdentityRevocationApplyRequest = z.infer<
  typeof LineIdentityRevocationApplyRequestSchema
>;
export type LineIdentityReplacementApplyRequest = z.infer<
  typeof LineIdentityReplacementApplyRequestSchema
>;
export type LineIdentityRevocationActionRequest = z.infer<
  typeof LineIdentityRevocationActionRequestSchema
>;
export type LineIdentityRevocationRequestView = z.infer<
  typeof LineIdentityRevocationRequestViewSchema
>;
export type LineIdentityBindingListQuery = z.infer<
  typeof LineIdentityBindingListQuerySchema
>;
export type LineIdentityReviewType = z.infer<
  typeof LineIdentityReviewTypeSchema
>;
export type LineIdentityReviewStatus = z.infer<
  typeof LineIdentityReviewStatusSchema
>;
export type LineIdentityReviewDecision = z.infer<
  typeof LineIdentityReviewDecisionSchema
>;
export type LineIdentityReviewView = z.infer<
  typeof LineIdentityReviewViewSchema
>;
export type LineIdentityReviewPageView = z.infer<
  typeof LineIdentityReviewPageViewSchema
>;
export type LineIdentityReviewApplyView = z.infer<
  typeof LineIdentityReviewApplyViewSchema
>;
export type LineIdentityReviewSummaryView = z.infer<
  typeof LineIdentityReviewSummaryViewSchema
>;
export type LineIdentityReviewListQuery = z.infer<
  typeof LineIdentityReviewListQuerySchema
>;
export type LineIdentityReviewPreviewRequest = z.infer<
  typeof LineIdentityReviewPreviewRequestSchema
>;
export type LineIdentityReviewPreviewView = z.infer<
  typeof LineIdentityReviewPreviewViewSchema
>;
export type LineIdentityReviewApplyRequest = z.infer<
  typeof LineIdentityReviewApplyRequestSchema
>;
