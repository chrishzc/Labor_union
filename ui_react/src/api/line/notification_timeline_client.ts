/**
 * File: notification_timeline_client.ts
 * Description: 嚴格解碼案件範圍的canonical LINE 通知唯讀歷程。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';

export const LineNotificationTimelineRecordSchema = z.strictObject({
  source_event_id: z.number().int().positive(),
  event_code: z.string().min(1),
  occurred_at_utc: z.string().min(1).optional(),
  historical_silent: z.boolean().optional(),
  rule_id: z.string().nullable().optional(),
  decision_status: z.string().nullable().optional(),
  reason_code: z.string().nullable().optional(),
  recipient_type: z.string().nullable().optional(),
  recipient_identity: z.string().nullable().optional(),
  occurrence_number: z.number().int().positive().nullable().optional(),
  intent_status: z.string().nullable().optional(),
  scheduled_at_utc: z.string().nullable().optional(),
  delivery_status: z.string().nullable().optional(),
  delivery_task_id: z.number().int().positive().nullable().optional(),
});

export const LineNotificationTimelineSchema = z.strictObject({
  case_no: z.string().min(1),
  records: z.array(LineNotificationTimelineRecordSchema),
});

const EnvelopeSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: LineNotificationTimelineSchema,
  error: z.string().nullable(),
});

export type LineNotificationTimeline = z.infer<typeof LineNotificationTimelineSchema>;

export const lineNotificationTimelineClient = {
  async query(caseNo: string, options?: { signal?: AbortSignal }): Promise<LineNotificationTimeline> {
    const canonicalCaseNo = caseNo.trim();
    if (!canonicalCaseNo) throw new Error('案件編號不得為空。');
    const requestOptions: RequestOptions = {
      signal: options?.signal,
      token: sessionClient.getToken(),
    };
    const endpoint = `/api/v1/line/notification-rules/timeline/${encodeURIComponent(canonicalCaseNo)}`;
    const envelope = decodePayload(EnvelopeSchema, await transport.get(endpoint, requestOptions));
    if (!envelope.success) {
      throw new ApiHttpError(400, 'LINE_NOTIFICATION_TIMELINE_QUERY_FAILED', envelope.error ?? envelope.message, false, envelope);
    }
    if (envelope.data.case_no !== canonicalCaseNo) {
      throw new ApiHttpError(409, 'LINE_NOTIFICATION_TIMELINE_IDENTITY_MISMATCH', 'LINE 通知歷程案件識別不一致。', false, envelope);
    }
    return envelope.data;
  },
};
