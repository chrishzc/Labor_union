/**
 * File: line_notification_template_client.ts
 * Description: 查詢與更新通知規則目前引用的文字訊息模板。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';

const IdentifierSchema = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/);

const LineNotificationTemplateSchema = z.strictObject({
  rule_id: IdentifierSchema,
  template_id: IdentifierSchema,
  name: z.string(),
  content: z.string(),
  revision: z.number().int().nonnegative(),
  variables: z.array(z.string()),
  sample_preview: z.string(),
});

const LineNotificationTemplateEnvelopeSchema = z.object({
  success: z.literal(true),
  message: z.string().optional(),
  data: LineNotificationTemplateSchema,
  error: z.null().optional(),
});

export type LineNotificationTemplateData = z.infer<typeof LineNotificationTemplateSchema>;

export interface UpdateLineNotificationTemplatePayload {
  content: string;
  expected_revision: number;
  reason?: string;
}

export interface LineNotificationTemplateClientOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface LineNotificationTemplateClient {
  get(
    ruleId: string,
    options?: LineNotificationTemplateClientOptions,
  ): Promise<LineNotificationTemplateData>;
  update(
    ruleId: string,
    payload: UpdateLineNotificationTemplatePayload,
    options?: LineNotificationTemplateClientOptions,
  ): Promise<LineNotificationTemplateData>;
}

function rulePath(ruleId: string): string {
  const parsed = IdentifierSchema.safeParse(ruleId);
  if (!parsed.success) throw new Error('通知規則 ID 格式不正確。');
  return `/api/v1/line/notification-rules/${encodeURIComponent(parsed.data)}/message-template`;
}

function requestOptions(options?: LineNotificationTemplateClientOptions): RequestOptions {
  const token = sessionClient.getToken();
  return {
    token: token ?? undefined,
    signal: options?.signal,
    timeoutMs: options?.timeoutMs ?? 10_000,
    baseUrl: options?.baseUrl,
  };
}

export class DefaultLineNotificationTemplateClient implements LineNotificationTemplateClient {
  async get(
    ruleId: string,
    options?: LineNotificationTemplateClientOptions,
  ): Promise<LineNotificationTemplateData> {
    const raw = await transport.get<object>(rulePath(ruleId), requestOptions(options));
    return decodePayload(LineNotificationTemplateEnvelopeSchema, raw).data;
  }

  async update(
    ruleId: string,
    payload: UpdateLineNotificationTemplatePayload,
    options?: LineNotificationTemplateClientOptions,
  ): Promise<LineNotificationTemplateData> {
    const raw = await transport.put<object>(
      rulePath(ruleId),
      {
        content: payload.content,
        expected_revision: payload.expected_revision,
        reason: payload.reason ?? '更新通知規則訊息內容',
      },
      requestOptions(options),
    );
    return decodePayload(LineNotificationTemplateEnvelopeSchema, raw).data;
  }
}

export const lineNotificationTemplateClient: LineNotificationTemplateClient =
  new DefaultLineNotificationTemplateClient();
