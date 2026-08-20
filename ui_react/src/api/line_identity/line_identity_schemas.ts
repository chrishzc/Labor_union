/**
 * File: line_identity_schemas.ts
 * Description: 定義 LINE 身分綁定查詢、解除預覽與解除申請的嚴格 Zod 公開契約。
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

export const LineIdentityRevocationApplyRequestSchema = z
  .object({
    expected_version: z.number().int().nonnegative(),
    reason: z.string().min(1).max(1000),
    idempotency_key: z.string().min(1).max(191),
    correlation_id: z.string().min(1).max(191),
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
export type LineIdentityRevocationApplyRequest = z.infer<
  typeof LineIdentityRevocationApplyRequestSchema
>;
export type LineIdentityRevocationRequestView = z.infer<
  typeof LineIdentityRevocationRequestViewSchema
>;
export type LineIdentityBindingListQuery = z.infer<
  typeof LineIdentityBindingListQuerySchema
>;
