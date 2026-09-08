/** Strict client for the LINE notification manual replay Preview/Apply flow. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';

const PreviewSchema = z.strictObject({
  source_event_id: z.number().int().positive(),
  event_code: z.string().trim().min(1),
  historical_silent: z.boolean(),
  matching_rule_count: z.number().int().nonnegative(),
  will_create_new_immutable_source: z.boolean(),
});

const ApplyRequestSchema = z.strictObject({
  reason: z.string().trim().min(1).max(1_000),
  idempotency_key: z.string().trim().min(1).max(191),
  correlation_id: z.string().trim().min(1).max(191),
});

const ApplyReceiptSchema = z.strictObject({
  source_event_id: z.number().int().positive(),
  replayed_source_event_id: z.number().int().positive(),
});

function envelope<T extends z.ZodTypeAny>(schema: T) {
  return z.strictObject({
    success: z.literal(true),
    message: z.string(),
    data: schema,
    error: z.null(),
  });
}

export type LineNotificationManualReplayPreview = z.infer<typeof PreviewSchema>;
export type LineNotificationManualReplayRequest = z.infer<typeof ApplyRequestSchema>;
export type LineNotificationManualReplayReceipt = z.infer<typeof ApplyReceiptSchema>;

export interface LineNotificationManualReplayOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
}

function sourcePath(sourceEventId: number, suffix: string): string {
  if (!Number.isInteger(sourceEventId) || sourceEventId < 1) {
    throw new Error('LINE 通知來源識別值無效。');
  }
  return `/api/v1/line/notification-rules/sources/${sourceEventId}/manual-replay${suffix}`;
}

function requestOptions(options?: LineNotificationManualReplayOptions): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new Error('管理員登入狀態已失效。');
  return {
    token,
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
  };
}

async function preview(
  sourceEventId: number,
  options?: LineNotificationManualReplayOptions,
): Promise<LineNotificationManualReplayPreview> {
  const path = sourcePath(sourceEventId, '/preview');
  const raw = await transport.post<unknown>(path, undefined, requestOptions(options));
  return decodePayload(envelope(PreviewSchema), raw).data;
}

async function apply(
  sourceEventId: number,
  payload: LineNotificationManualReplayRequest,
  options?: LineNotificationManualReplayOptions,
): Promise<LineNotificationManualReplayReceipt> {
  const validPayload = ApplyRequestSchema.parse(payload);
  const path = sourcePath(sourceEventId, '');
  const raw = await transport.post<unknown>(path, validPayload, requestOptions(options));
  const receipt = decodePayload(envelope(ApplyReceiptSchema), raw).data;
  if (receipt.source_event_id !== sourceEventId) {
    throw new Error('LINE 通知重送收據與來源不一致。');
  }
  return receipt;
}

export const lineNotificationManualReplayClient = { preview, apply };
