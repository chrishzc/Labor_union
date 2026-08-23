/**
 * File: line_delivery_query_schemas.ts
 * Description: 定義 LINE Delivery server-masked summary、list、detail 與 attempt strict views。
 */
import { z } from 'zod';

const DateTimeSchema = z.string().datetime({ offset: true });
const NullableDateTimeSchema = DateTimeSchema.nullable();

export const LineDeliveryStatusSchema = z.enum([
  'pending', 'processing', 'sent', 'retryable_failed', 'failed', 'cancelled',
]);
export const LineDeliverySourceTypeSchema = z.enum([
  'general_push', 'customer_service', 'contract', 'follow_schedule', 'identity',
  'identity_review', 'rich_menu', 'rich_menu_link', 'rich_menu_unlink', 'webhook',
  'group_invitation', 'runtime', 'matching', 'order', 'finance', 'assignment',
]);
export const LineDeliveryWorkerStatusSchema = z.enum([
  'healthy', 'degraded', 'stale', 'stopped', 'missing', 'unknown',
]);

export const LineDeliverySummarySchema = z.strictObject({
  total: z.number().int().nonnegative(),
  pending: z.number().int().nonnegative(),
  processing: z.number().int().nonnegative(),
  sent: z.number().int().nonnegative(),
  retryable_failed: z.number().int().nonnegative(),
  failed: z.number().int().nonnegative(),
  cancelled: z.number().int().nonnegative(),
  overdue: z.number().int().nonnegative(),
  sent_today: z.number().int().nonnegative(),
  next_run_at: NullableDateTimeSchema,
  worker_running: z.boolean(),
  worker_status: LineDeliveryWorkerStatusSchema,
});

export const LineDeliveryItemSchema = z.strictObject({
  id: z.number().int().positive(),
  task_id: z.number().int().positive(),
  task_type: z.string().min(1),
  source_type: LineDeliverySourceTypeSchema,
  status: LineDeliveryStatusSchema,
  scheduled_at: DateTimeSchema,
  completed_attempts: z.number().int().nonnegative(),
  max_attempts: z.number().int().positive(),
  next_retry_at: NullableDateTimeSchema,
  sent_at: NullableDateTimeSchema,
  failed_at: NullableDateTimeSchema,
  created_at: DateTimeSchema,
  updated_at: DateTimeSchema,
});

export const LineDeliveryAttemptSchema = z.strictObject({
  attempt_number: z.number().int().positive(),
  outcome: z.enum(['success', 'retryable_failure', 'terminal_failure']),
  retry_after_seconds: z.number().int().nonnegative().nullable(),
  started_at: DateTimeSchema,
  completed_at: DateTimeSchema,
});

export const LineDeliveryPageSchema = z.strictObject({
  items: z.array(LineDeliveryItemSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().min(1).max(100),
  total: z.number().int().nonnegative(),
  total_pages: z.number().int().nonnegative(),
});

export const LineDeliveryDetailSchema = z.strictObject({
  task: LineDeliveryItemSchema,
  attempts: z.array(LineDeliveryAttemptSchema),
});

function envelope<T extends z.ZodTypeAny>(data: T) {
  return z.strictObject({
    success: z.boolean(),
    message: z.string(),
    data,
    error: z.string().nullable().optional(),
  });
}

export const LineDeliverySummaryResponseSchema = envelope(LineDeliverySummarySchema);
export const LineDeliveryPageResponseSchema = envelope(LineDeliveryPageSchema);
export const LineDeliveryDetailResponseSchema = envelope(LineDeliveryDetailSchema);

export type LineDeliveryStatus = z.infer<typeof LineDeliveryStatusSchema>;
export type LineDeliverySourceType = z.infer<typeof LineDeliverySourceTypeSchema>;
export type LineDeliverySummary = z.infer<typeof LineDeliverySummarySchema>;
export type LineDeliveryItem = z.infer<typeof LineDeliveryItemSchema>;
export type LineDeliveryPage = z.infer<typeof LineDeliveryPageSchema>;
export type LineDeliveryDetail = z.infer<typeof LineDeliveryDetailSchema>;
