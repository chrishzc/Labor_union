/**
 * File: matching_schedule_confirmation_client.ts
 * Description: 嚴格解碼日期表查詢、人工快照 Preview／Apply 與逐一確認回讀。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';

const FingerprintSchema = z.string().regex(/^[0-9a-f]{64}$/);
const IsoDateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const WeekSchema = z.strictObject({
  week_number: z.number().int().positive(),
  period_start: IsoDateSchema,
  period_end: IsoDateSchema,
  service_dates: z.array(IsoDateSchema).min(1),
  service_day_count: z.number().int().positive(),
});
const RecipientScheduleSchema = z.strictObject({
  audience_type: z.enum(['customer', 'caregiver']),
  segment_id: z.number().int().positive().nullable(),
  total_service_days: z.number().int().nonnegative(),
  total_weeks: z.number().int().nonnegative(),
  weeks: z.array(WeekSchema),
});
const SchedulePreviewSchema = z.strictObject({
  week_grouping_policy: z.literal('calendar_week_sunday_to_saturday_v1'),
  total_service_days: z.number().int().positive(),
  total_weeks: z.number().int().positive(),
  weeks: z.array(WeekSchema).min(1),
  recipient_schedules: z.array(RecipientScheduleSchema).min(2),
});
const RecipientSchema = z.strictObject({
  recipient_snapshot_id: z.number().int().positive(),
  audience_type: z.enum(['customer', 'caregiver']),
  segment_id: z.number().int().positive().nullable(),
  delivery_status: z.enum(['pending', 'queued', 'sent', 'failed', 'blocked']),
  confirmation_status: z.enum(['pending', 'confirmed', 'rejected', 'manually_confirmed', 'manually_revoked']),
  confirmation_source: z.enum(['line', 'admin']).nullable(),
  confirmation_reason: z.string().max(500).nullable(),
  confirmation_occurred_at_utc: z.string().nullable(),
});
const StateSchema = z.strictObject({
  case_no: z.string().min(1).max(50),
  plan_id: z.number().int().positive(),
  confirmed_service_date_version: z.number().int().positive(),
  snapshot_id: z.number().int().positive().nullable(),
  snapshot_status: z.enum(['not_sent', 'sent', 'sent_outdated', 'manual_ready']),
  schedule_preview: SchedulePreviewSchema,
  outdated_schedule_preview: SchedulePreviewSchema.nullable(),
  recipients: z.array(RecipientSchema),
  gate_passed: z.boolean(),
});
const ManualPreviewSchema = z.strictObject({
  case_no: z.string().min(1).max(50),
  plan_id: z.number().int().positive(),
  confirmed_service_date_version: z.number().int().positive(),
  schedule_preview: SchedulePreviewSchema,
  preview_fingerprint: FingerprintSchema,
});
const envelope = <T extends z.ZodTypeAny>(schema: T) => z.object({
  success: z.boolean(), message: z.string(), data: schema.nullable(), error: z.string().nullable().optional(),
}).passthrough();

export type MatchingScheduleState = z.infer<typeof StateSchema>;
export type MatchingScheduleManualPreview = z.infer<typeof ManualPreviewSchema>;

function requestOptions(idempotencyKey?: string): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
  const headers: Record<string, string> = {};
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  return { token, headers };
}

function decode<T>(schema: z.ZodType<T>, raw: unknown, operation: string): T {
  const parsed = envelope(schema).safeParse(raw);
  if (!parsed.success) throw new ApiDecodeError(`日期表${operation}回應結構異常。`, parsed.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message, code: issue.code })), raw);
  if (!parsed.data.success || parsed.data.data === null) throw new ApiHttpError(422, 'MATCHING_SCHEDULE_EMPTY_RESPONSE', parsed.data.error ?? parsed.data.message, false, raw);
  return parsed.data.data as T;
}

function planPath(caseNo: string, planId: number): string {
  return `/api/v1/orders/${encodeURIComponent(caseNo)}/matching-plans/${planId}/schedule-confirmation`;
}

function assertIdentity<T extends { case_no: string; plan_id: number }>(value: T, caseNo: string, planId: number): T {
  if (value.case_no !== caseNo || value.plan_id !== planId) throw new ApiDecodeError('日期表案件或方案 identity 不一致。');
  return value;
}

export const matchingScheduleConfirmationClient = {
  async query(caseNo: string, planId: number): Promise<MatchingScheduleState> {
    const raw = await transport.get<unknown>(planPath(caseNo, planId), requestOptions());
    return assertIdentity(decode(StateSchema, raw, '查詢'), caseNo, planId);
  },
  async previewManual(caseNo: string, planId: number): Promise<MatchingScheduleManualPreview> {
    const raw = await transport.post<unknown>(`${planPath(caseNo, planId)}/manual-preview`, undefined, requestOptions());
    return assertIdentity(decode(ManualPreviewSchema, raw, '人工 Preview'), caseNo, planId);
  },
  async applyManual(caseNo: string, planId: number, preview: MatchingScheduleManualPreview, reason: string): Promise<MatchingScheduleState> {
    const raw = await transport.post<unknown>(`${planPath(caseNo, planId)}/manual-apply`, {
      confirmed_service_date_version: preview.confirmed_service_date_version,
      preview_fingerprint: preview.preview_fingerprint,
      reason: reason.trim(),
    }, requestOptions(`manual-schedule-${caseNo}-${planId}-${crypto.randomUUID()}`));
    return assertIdentity(decode(StateSchema, raw, '人工 Apply'), caseNo, planId);
  },
  async confirmManual(recipientId: number, reason: string): Promise<MatchingScheduleState> {
    const raw = await transport.put<unknown>(`/api/v1/orders/schedule-confirmation/recipients/${recipientId}`, {
      value: 'manually_confirmed', reason: reason.trim(),
    }, requestOptions(`manual-schedule-recipient-${recipientId}-${crypto.randomUUID()}`));
    return decode(StateSchema, raw, '人工確認');
  },
};
