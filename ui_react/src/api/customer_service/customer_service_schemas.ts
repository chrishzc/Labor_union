/**
 * File: customer_service_schemas.ts
 * Description: 定義客服查詢、狀態更新、LINE 回覆與結案 Preview／Apply 的嚴格 Zod 契約。
 */
import { z } from 'zod';

// FastAPI/Pydantic datetime JSON may be local (naive) or include an offset.
const CustomerServiceDateTimeSchema = z.string().datetime({
  offset: true,
  local: true,
});

export const CustomerServiceCategorySchema = z.enum([
  'service_flow',
  'payment_subsidy',
  'service_progress',
  'profile_update',
  'contact_union',
  'other',
]);
export type CustomerServiceCategory = z.infer<
  typeof CustomerServiceCategorySchema
>;

export const CustomerServiceStatusSchema = z.enum([
  'waiting',
  'handling',
  'resolved',
]);
export type CustomerServiceStatus = z.infer<
  typeof CustomerServiceStatusSchema
>;

export const CustomerServiceTicketSchema = z
  .object({
    ticket_id: z.number().int(),
    line_user_id_masked: z.string(),
    category: CustomerServiceCategorySchema,
    status: CustomerServiceStatusSchema,
    version: z.number().int(),
    client_id: z.number().int().nullable().optional(),
    case_no: z.string().nullable().optional(),
    client_name: z.string().nullable().optional(),
    client_phone: z.string().nullable().optional(),
    assigned_admin_user_id: z.number().int().nullable().optional(),
    internal_note: z.string().nullable().optional(),
    created_at: CustomerServiceDateTimeSchema.nullable().optional(),
    updated_at: CustomerServiceDateTimeSchema.nullable().optional(),
  })
  .strict();
export type CustomerServiceTicket = z.infer<
  typeof CustomerServiceTicketSchema
>;

export const CustomerServiceEventSchema = z
  .object({
    id: z.number().int(),
    event_type: z.string(),
    message_text: z.string().nullable().optional(),
    actor_id: z.string(),
    created_at: CustomerServiceDateTimeSchema,
  })
  .strict();
export type CustomerServiceEvent = z.infer<
  typeof CustomerServiceEventSchema
>;

export const CustomerServiceDetailSchema = z
  .object({
    ticket: CustomerServiceTicketSchema,
    events: z.array(CustomerServiceEventSchema),
  })
  .strict();
export type CustomerServiceDetail = z.infer<
  typeof CustomerServiceDetailSchema
>;

export const CustomerServicePageSchema = z
  .object({
    items: z.array(CustomerServiceTicketSchema),
    total: z.number().int(),
    page: z.number().int(),
    page_size: z.number().int(),
  })
  .strict();
export type CustomerServicePage = z.infer<typeof CustomerServicePageSchema>;

export const CustomerServiceSummarySchema = z
  .object({
    waiting: z.number().int(),
    handling: z.number().int(),
    resolved_today: z.number().int(),
  })
  .strict();
export type CustomerServiceSummary = z.infer<
  typeof CustomerServiceSummarySchema
>;

export const CustomerServiceListParamsSchema = z
  .object({
    status: CustomerServiceStatusSchema.optional(),
    category: CustomerServiceCategorySchema.optional(),
    search: z.string().optional(),
    page: z.number().int().min(1).optional(),
    page_size: z.number().int().min(1).max(100).optional(),
  })
  .strict();
export type CustomerServiceListParams = z.infer<
  typeof CustomerServiceListParamsSchema
>;

export const CustomerServiceResolvePreviewRequestSchema = z
  .object({
    status: CustomerServiceStatusSchema,
    internal_note: z.string().max(4000).nullable(),
    expected_version: z.number().int().nonnegative(),
  })
  .strict();
export type CustomerServiceResolvePreviewRequest = z.infer<
  typeof CustomerServiceResolvePreviewRequestSchema
>;

export const CustomerServiceFingerprintSchema = z
  .string()
  .regex(/^[0-9a-f]{64}$/);

export const CustomerServiceResolvePreviewSchema = z
  .object({
    ticket_id: z.number().int(),
    before_status: CustomerServiceStatusSchema,
    after_status: CustomerServiceStatusSchema,
    current_version: z.number().int().nonnegative(),
    expected_version: z.number().int().nonnegative(),
    blockers: z.array(z.string()),
    preview_fingerprint: CustomerServiceFingerprintSchema,
    apply_ready: z.boolean(),
  })
  .strict();
export type CustomerServiceResolvePreview = z.infer<
  typeof CustomerServiceResolvePreviewSchema
>;

export const CustomerServiceResolveApplyRequestSchema = z
  .object({
    status: CustomerServiceStatusSchema,
    internal_note: z.string().max(4000).nullable(),
    expected_version: z.number().int().nonnegative(),
    preview_fingerprint: CustomerServiceFingerprintSchema,
  })
  .strict();
export type CustomerServiceResolveApplyRequest = z.infer<
  typeof CustomerServiceResolveApplyRequestSchema
>;

export const CustomerServiceUpdateApplySchema = z
  .object({
    ticket_id: z.number().int(),
    resulting_status: CustomerServiceStatusSchema,
    resulting_version: z.number().int().positive(),
    preview_fingerprint: CustomerServiceFingerprintSchema,
    replayed: z.boolean(),
    readback: CustomerServiceDetailSchema,
  })
  .strict();
export type CustomerServiceUpdateApply = z.infer<
  typeof CustomerServiceUpdateApplySchema
>;

export const CustomerServiceReplyPreviewRequestSchema = z
  .object({
    reply_text: z.string().trim().min(1).max(2000),
    resolve: z.boolean(),
    internal_note: z.string().max(4000).nullable(),
    expected_version: z.number().int().nonnegative(),
  })
  .strict();
export type CustomerServiceReplyPreviewRequest = z.infer<
  typeof CustomerServiceReplyPreviewRequestSchema
>;

export const CustomerServiceReplyApplyRequestSchema = CustomerServiceReplyPreviewRequestSchema
  .extend({
    idempotency_key: z.string().min(1).max(191),
    preview_fingerprint: CustomerServiceFingerprintSchema,
  })
  .strict();
export type CustomerServiceReplyApplyRequest = z.infer<
  typeof CustomerServiceReplyApplyRequestSchema
>;

export const CustomerServiceReplyPreviewSchema = z
  .object({
    ticket_id: z.number().int(),
    before_status: CustomerServiceStatusSchema,
    after_status: CustomerServiceStatusSchema,
    current_version: z.number().int().nonnegative(),
    expected_version: z.number().int().nonnegative(),
    reply_character_count: z.number().int().min(1).max(2000),
    will_enqueue_delivery: z.literal(true),
    preview_fingerprint: CustomerServiceFingerprintSchema,
    apply_ready: z.literal(true),
  })
  .strict();
export type CustomerServiceReplyPreview = z.infer<
  typeof CustomerServiceReplyPreviewSchema
>;

export const CustomerServiceReplyApplySchema = z
  .object({
    ticket_id: z.number().int(),
    resulting_status: CustomerServiceStatusSchema,
    resulting_version: z.number().int().positive(),
    preview_fingerprint: CustomerServiceFingerprintSchema,
    delivery_enqueued: z.literal(true),
    delivery_delivered: z.literal(false),
    replayed: z.boolean(),
    readback: CustomerServiceDetailSchema,
  })
  .strict();
export type CustomerServiceReplyApply = z.infer<
  typeof CustomerServiceReplyApplySchema
>;

export const CustomerServiceSummaryResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: CustomerServiceSummarySchema,
    error: z.string().nullable(),
  })
  .strict();
export type CustomerServiceSummaryResponse = z.infer<
  typeof CustomerServiceSummaryResponseSchema
>;

export const CustomerServicePageResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: CustomerServicePageSchema,
    error: z.string().nullable(),
  })
  .strict();
export type CustomerServicePageResponse = z.infer<
  typeof CustomerServicePageResponseSchema
>;

export const CustomerServiceDetailResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: CustomerServiceDetailSchema,
    error: z.string().nullable(),
  })
  .strict();
export type CustomerServiceDetailResponse = z.infer<
  typeof CustomerServiceDetailResponseSchema
>;

export const CustomerServiceResolvePreviewResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: CustomerServiceResolvePreviewSchema,
    error: z.string().nullable(),
  })
  .strict();
export type CustomerServiceResolvePreviewResponse = z.infer<
  typeof CustomerServiceResolvePreviewResponseSchema
>;

export const CustomerServiceUpdateApplyResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: CustomerServiceUpdateApplySchema,
    error: z.string().nullable(),
  })
  .strict();

export const CustomerServiceReplyPreviewResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: CustomerServiceReplyPreviewSchema,
    error: z.string().nullable(),
  })
  .strict();

export const CustomerServiceReplyApplyResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: CustomerServiceReplyApplySchema,
    error: z.string().nullable(),
  })
  .strict();
