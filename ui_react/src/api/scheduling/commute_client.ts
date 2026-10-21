import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';

const UsageSchema = z.strictObject({
  billing_month: z.string(), billing_timezone: z.literal('America/Los_Angeles'), configured: z.boolean(),
  free_limit: z.number().int().nonnegative(), local_requests: z.number().int().nonnegative(),
  estimated_billable: z.number().int().nonnegative(), uncertain_requests: z.number().int().nonnegative(),
  free_used: z.number().int().nonnegative(), free_remaining: z.number().int().nonnegative(),
  paid_requests: z.number().int().nonnegative(), estimated_cost_usd: z.string(),
  verified_count: z.number().int().nonnegative().nullable(), verified_through: z.string().nullable(), verified_at: z.string().nullable(),
});
const RouteSchema = z.strictObject({
  case_no: z.string(), staff_id: z.number().int().positive(), event_key: z.string(),
  status: z.enum(['ready', 'no_route', 'failed', 'unknown', 'already_requested']),
  distance_meters: z.number().int().nonnegative().nullable(), duration_seconds: z.number().nonnegative().nullable(),
  queried_at: z.string(), message: z.string(),
});
const HistorySchema = z.strictObject({
  case_no: z.string(),
  records: z.array(z.strictObject({
    record_id: z.string(), queried_at: z.string(), staff_id: z.number().int().positive(),
    staff_name: z.string().nullable(), status: z.enum(['succeeded', 'failed', 'unknown']), message: z.string(),
  })).max(50),
});
const envelope = <T extends z.ZodTypeAny>(data: T) => z.object({ success: z.literal(true), data });
export type CommuteUsage = z.infer<typeof UsageSchema>;
export type CommuteRoute = z.infer<typeof RouteSchema>;
export type CommuteHistory = z.infer<typeof HistorySchema>;
const options = () => ({ token: sessionClient.getToken(), cache: 'no-store' as const });
export const commuteClient = {
  async usage(): Promise<CommuteUsage> {
    return decodePayload(envelope(UsageSchema), await transport.get('/api/v1/scheduling/commute-usage', options())).data;
  },
  async history(caseNo: string, signal?: AbortSignal): Promise<CommuteHistory> {
    const data = decodePayload(envelope(HistorySchema), await transport.get(
      `/api/v1/orders/${encodeURIComponent(caseNo)}/commute-history`, { ...options(), signal })).data;
    if (data.case_no !== caseNo) throw new Error('通勤查詢紀錄與目前案件不一致。');
    return data;
  },
  async query(caseNo: string, staffId: number, eventKey: string, signal?: AbortSignal): Promise<CommuteRoute> {
    const data = decodePayload(envelope(RouteSchema), await transport.post(
      `/api/v1/orders/${encodeURIComponent(caseNo)}/caregivers/${staffId}/commute`,
      { event_key: eventKey }, { ...options(), timeoutMs: 25000, signal })).data;
    if (data.case_no !== caseNo || data.staff_id !== staffId || data.event_key !== eventKey) throw new Error('通勤查詢結果與目前人選不一致。');
    return data;
  },
  async reconcile(month: string, count: number, through: string): Promise<CommuteUsage> {
    return decodePayload(envelope(UsageSchema), await transport.post('/api/v1/scheduling/commute-usage/reconciliation',
      { month, count, through, event_key: crypto.randomUUID() }, options())).data;
  },
};
