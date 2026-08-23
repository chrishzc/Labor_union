/**
 * File: staff_leave_inbox_client.ts
 * Description: 以 strict typed contract 查詢與審核 Scheduling 請假待辦。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';

const IsoDateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const LeaveInboxStatusSchema = z.enum(['pending', 'accepted_for_processing', 'rejected', 'cancelled', 'resolved']);
const LeaveInboxItemSchema = z.strictObject({
  id: z.number().int().positive(),
  staff_id: z.number().int().positive(),
  staff_name: z.string().min(1),
  leave_start_date: IsoDateSchema,
  leave_end_date: IsoDateSchema,
  request_reason: z.string(),
  request_status: LeaveInboxStatusSchema,
  aggregate_version: z.number().int().positive(),
});
const ReviewReceiptSchema = z.strictObject({
  request_id: z.number().int().positive(),
  status: LeaveInboxStatusSchema,
  version: z.number().int().positive(),
  actor: z.string().min(1),
});
const envelope = <T extends z.ZodTypeAny>(data: T) => z.object({
  success: z.boolean(), message: z.string(), data: data.nullable(), error: z.string().nullable().optional(),
}).passthrough();

export type LeaveInboxStatus = z.infer<typeof LeaveInboxStatusSchema>;
export type LeaveInboxItem = z.infer<typeof LeaveInboxItemSchema>;
export type LeaveInboxReviewReceipt = z.infer<typeof ReviewReceiptSchema>;
export type LeaveInboxReviewAction = 'accept' | 'reject' | 'cancel';

function options(idempotencyKey?: string): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
  const headers: Record<string, string> = { 'X-Correlation-ID': `scheduling-leave-inbox-${crypto.randomUUID()}` };
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  return { token, headers };
}

function decode<T>(schema: z.ZodType<T>, raw: unknown, operation: string): T {
  const parsed = envelope(schema).safeParse(raw);
  if (!parsed.success) {
    throw new ApiDecodeError(`請假待辦 ${operation} 回應結構異常。`, parsed.error.issues.map((issue) => ({
      path: issue.path.join('.') || '(root)', message: issue.message, code: issue.code,
    })), raw);
  }
  if (!parsed.data.success || parsed.data.data === null) {
    throw new ApiHttpError(422, 'LEAVE_INBOX_EMPTY_RESPONSE', parsed.data.error ?? parsed.data.message, false, raw);
  }
  return parsed.data.data as T;
}

export const staffLeaveInboxClient = {
  async list(status: LeaveInboxStatus = 'pending', limit = 50): Promise<readonly LeaveInboxItem[]> {
    const raw = await transport.get<unknown>('/api/v1/scheduling/staff-leave-requests', {
      ...options(), params: { status, limit },
    });
    return decode(z.array(LeaveInboxItemSchema).readonly(), raw, '查詢');
  },
  async review(item: LeaveInboxItem, action: LeaveInboxReviewAction, reason: string): Promise<LeaveInboxReviewReceipt> {
    const key = `leave-inbox-${item.id}-${item.aggregate_version}-${action}-${crypto.randomUUID()}`;
    const raw = await transport.post<unknown>(
      `/api/v1/scheduling/staff-leave-requests/${item.id}/review`,
      { expected_version: item.aggregate_version, action, reason: reason.trim() },
      options(key),
    );
    return decode(ReviewReceiptSchema, raw, '審核');
  },
};
