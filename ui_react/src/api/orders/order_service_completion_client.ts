/**
 * File: order_service_completion_client.ts
 * Description: 嚴格處理 Orders 服務完成 Preview、canonical Apply 與 receipt。
 */
import { z } from 'zod';

import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';

const IsoDateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const IsoDateTimeSchema = z.string().refine(
  (value) => !Number.isNaN(Date.parse(value)),
  { message: '預期有效 ISO 日期時間' },
);
const FingerprintSchema = z.string().regex(/^[0-9a-f]{64}$/);
const PreviewSchema = z.strictObject({
  case_no: z.string().min(1).max(50),
  expected_order_version: z.number().int().nonnegative(),
  resulting_order_version: z.number().int().positive(),
  current_status: z.string().min(1),
  completion_instant: IsoDateTimeSchema,
  evaluation_at: IsoDateTimeSchema,
  official_service_dates: z.array(IsoDateSchema).min(1),
  fingerprint: FingerprintSchema,
});
const ReceiptSchema = z.strictObject({
  case_no: z.string().min(1).max(50),
  idempotency_key: z.string().min(1),
  order_version: z.number().int().positive(),
  lifecycle_event_id: z.number().int().positive(),
  completion_instant: IsoDateTimeSchema,
  evaluation_at: IsoDateTimeSchema,
  command_fingerprint: FingerprintSchema,
});
const envelope = <T extends z.ZodTypeAny>(schema: T) => z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: schema.nullable(),
  error: z.string().nullable(),
});

export type OrderServiceCompletionPreview = z.infer<typeof PreviewSchema>;
export type OrderServiceCompletionReceipt = z.infer<typeof ReceiptSchema>;

function options(idempotencyKey?: string): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
  const headers: Record<string, string> = {
    'X-Correlation-ID': `order-service-completion-${crypto.randomUUID()}`,
  };
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  return { token, headers };
}

function decode<T>(schema: z.ZodType<T>, raw: unknown, operation: string): T {
  const parsed = envelope(schema).safeParse(raw);
  if (!parsed.success) {
    throw new ApiDecodeError(
      `服務完成${operation}回應結構異常。`,
      parsed.error.issues.map((issue) => ({
        path: issue.path.join('.'),
        message: issue.message,
        code: issue.code,
      })),
      raw,
    );
  }
  if (!parsed.data.success || parsed.data.data === null) {
    throw new ApiHttpError(
      422,
      'ORDER_SERVICE_COMPLETION_EMPTY_RESPONSE',
      parsed.data.error ?? parsed.data.message,
      false,
      raw,
    );
  }
  return parsed.data.data as T;
}

export const orderServiceCompletionClient = {
  async preview(caseNo: string): Promise<OrderServiceCompletionPreview> {
    const raw = await transport.post<unknown>(
      `/api/v1/orders/${encodeURIComponent(caseNo)}/service-completion/preview`,
      { evaluation_at: new Date().toISOString() },
      options(),
    );
    const result = decode(PreviewSchema, raw, ' Preview');
    if (result.case_no !== caseNo) {
      throw new ApiDecodeError('服務完成 Preview 案件 identity 不一致。');
    }
    return result;
  },

  async apply(
    caseNo: string,
    preview: OrderServiceCompletionPreview,
    reason: string,
    idempotencyKey: string,
  ): Promise<OrderServiceCompletionReceipt> {
    const raw = await transport.post<unknown>(
      `/api/v1/orders/${encodeURIComponent(caseNo)}/service-completion/apply`,
      {
        expected_order_version: preview.expected_order_version,
        evaluation_at: preview.evaluation_at,
        reason: reason.trim(),
        preview_fingerprint: preview.fingerprint,
      },
      options(idempotencyKey),
    );
    const result = decode(ReceiptSchema, raw, ' Apply');
    if (result.case_no !== caseNo) {
      throw new ApiDecodeError('服務完成 receipt 案件 identity 不一致。');
    }
    return result;
  },
};
