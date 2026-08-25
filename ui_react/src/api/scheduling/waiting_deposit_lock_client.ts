/**
 * File: waiting_deposit_lock_client.ts
 * Description: 查詢 active matching plan 並執行等待訂金檔期鎖 Preview／Apply。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';

const Fingerprint = z.string().regex(/^[0-9a-f]{64}$/);
const ActivePlanSchema = z.object({
  plan: z.object({ id: z.number().int().positive(), case_no: z.string().min(1), status: z.enum(['proposed', 'accepted']), version: z.number().int().nonnegative() }).passthrough(),
  segments: z.array(z.object({
    segment_id: z.number().int().positive(),
    segment_order: z.number().int().positive(),
    staff_id: z.number().int().positive(),
    assigned_start_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    assigned_end_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  }).passthrough()).min(1).max(4),
  availability_lock: z.object({ lock_id: z.number().int().positive(), status: z.string() }).passthrough().nullable(),
}).passthrough();
const PreviewSchema = z.strictObject({
  case_no: z.string().min(1), plan_id: z.number().int().positive(), service_day_count: z.number().int().nonnegative(),
  buffer_day_count: z.number().int().nonnegative(),
  occupancy: z.array(z.strictObject({ segment_id: z.number().int().positive(), staff_id: z.number().int().positive(), occupancy_date: z.string(), kind: z.enum(['service', 'buffer']) })),
  conflicts: z.array(z.strictObject({ staff_id: z.number().int().positive(), lock_date: z.string(), source_type: z.enum(['assignment', 'schedule', 'active_lock']), source_id: z.number().int().positive() })),
  apply_allowed: z.boolean(), preview_fingerprint: Fingerprint,
});
const ReceiptSchema = z.strictObject({
  result: z.enum(['created', 'existing']), lock_id: z.number().int().positive(), plan_id: z.number().int().positive(),
  case_no: z.string().min(1), lock_rows: z.array(z.strictObject({ segment_id: z.number().int().positive(), staff_id: z.number().int().positive(), lock_date: z.string() })),
});
const envelope = <T extends z.ZodTypeAny>(data: T) => z.object({ success: z.boolean(), message: z.string(), data: data.nullable(), error: z.string().nullable().optional() }).passthrough();

export type WaitingDepositPreview = z.infer<typeof PreviewSchema>;
export type WaitingDepositReceipt = z.infer<typeof ReceiptSchema>;
export interface ActiveWaitingDepositPlan {
  planId: number;
  status: string;
  activeLockId: number | null;
  communicationVersion?: number;
  segments?: ReadonlyArray<{
    segmentId: number;
    sequence: number;
    staffId: number;
    assignedStartDate: string;
    assignedEndDate: string;
  }>;
}

function options(idempotencyKey?: string): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
  const headers: Record<string, string> = { 'X-Correlation-ID': `waiting-lock-${crypto.randomUUID()}` };
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  return { token, headers };
}

function decode<T>(schema: z.ZodType<T>, raw: unknown, operation: string): T {
  const parsed = envelope(schema).safeParse(raw);
  if (!parsed.success) throw new ApiDecodeError(`預約鎖定 ${operation} 回應結構異常。`, parsed.error.issues.map((i) => ({ path: i.path.join('.'), message: i.message, code: i.code })), raw);
  if (!parsed.data.success || parsed.data.data === null) throw new ApiHttpError(422, 'WAITING_LOCK_EMPTY_RESPONSE', parsed.data.error ?? parsed.data.message, false, raw);
  return parsed.data.data as T;
}

export const waitingDepositLockClient = {
  async queryPlan(caseNo: string, signal?: AbortSignal): Promise<ActiveWaitingDepositPlan> {
    const raw = await transport.get<unknown>(
      `/api/v1/orders/${encodeURIComponent(caseNo)}/matching-plans/active`,
      { ...options(), signal },
    );
    const data = decode(ActivePlanSchema, raw, '方案查詢');
    if (data.plan.case_no !== caseNo) throw new ApiDecodeError('預約鎖定方案案件 identity 不一致。');
    return {
      planId: data.plan.id,
      status: data.plan.status,
      activeLockId: data.availability_lock?.lock_id ?? null,
      communicationVersion: data.plan.version,
      segments: data.segments.map((segment) => ({
        segmentId: segment.segment_id,
        sequence: segment.segment_order,
        staffId: segment.staff_id,
        assignedStartDate: segment.assigned_start_date,
        assignedEndDate: segment.assigned_end_date,
      })),
    };
  },
  async preview(caseNo: string, planId: number): Promise<WaitingDepositPreview> {
    const raw = await transport.post<unknown>(`/api/v1/orders/${encodeURIComponent(caseNo)}/matching-plans/${planId}/waiting-deposit-lock/acquire/preview`, undefined, options());
    return decode(PreviewSchema, raw, 'Preview');
  },
  async apply(caseNo: string, planId: number, fingerprint: string): Promise<WaitingDepositReceipt> {
    const raw = await transport.post<unknown>(`/api/v1/orders/${encodeURIComponent(caseNo)}/matching-plans/${planId}/waiting-deposit-lock/acquire/apply`, { preview_fingerprint: fingerprint }, options(`waiting-lock-${caseNo}-${planId}-${crypto.randomUUID()}`));
    return decode(ReceiptSchema, raw, 'Apply');
  },
};
