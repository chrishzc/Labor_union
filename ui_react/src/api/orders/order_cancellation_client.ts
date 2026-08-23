/**
 * File: order_cancellation_client.ts
 * Description: 提供 Orders Cancellation 嚴格 typed Query 與零寫入 Preview client。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';

const DateOnlySchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const ServiceDaySchema = z.strictObject({
  service_date: DateOnlySchema,
  staff_id: z.number().int().positive(),
  reason: z.string().min(1).max(500).nullable(),
});
const CaregiverOptionSchema = z.strictObject({
  staff_id: z.number().int().positive(),
  display_name: z.string().min(1),
});

export const OrderCancellationQuerySchema = z.strictObject({
  case_no: z.string().min(1),
  lifecycle_status: z.string().min(1),
  actual_start_date: DateOnlySchema.nullable(),
  contracted_service_days: z.number().int().positive(),
  service_hours_per_day: z.number().int().positive(),
  service_started: z.boolean(),
  service_data_locked: z.boolean(),
  order_version: z.number().int().nonnegative(),
  scheduling_version: z.number().int().nonnegative(),
  scheduling_generation: z.number().int().nonnegative(),
  client_finance_version: z.number().int().nonnegative(),
  payroll_version: z.number().int().nonnegative(),
  confirmed_service_days: z.array(ServiceDaySchema),
  caregiver_options: z.array(CaregiverOptionSchema),
});

export const OrderCancellationPreviewSchema = z.strictObject({
  cancellation_date: DateOnlySchema,
  actual_end_date: DateOnlySchema.nullable(),
  confirmed_service_days: z.array(ServiceDaySchema),
  official_service_day_count: z.number().int().nonnegative(),
  official_service_hours: z.number().int().nonnegative(),
  order_version: z.number().int().nonnegative(),
  scheduling_version: z.number().int().nonnegative(),
  scheduling_generation: z.number().int().nonnegative(),
  client_finance_version: z.number().int().nonnegative(),
  payroll_version: z.number().int().nonnegative(),
  scheduling: z.record(z.string(), z.unknown()),
  client_finance_impact: z.record(z.string(), z.unknown()),
  payroll_impact: z.record(z.string(), z.unknown()),
  lifecycle_impact: z.record(z.string(), z.unknown()),
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
});

const envelope = <T extends z.ZodTypeAny>(schema: T) => z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: schema,
  error: z.string().nullable(),
});

export type OrderCancellationQuery = z.infer<typeof OrderCancellationQuerySchema>;
export type OrderCancellationPreview = z.infer<typeof OrderCancellationPreviewSchema>;
type ServiceDay = z.infer<typeof ServiceDaySchema>;

function options(signal?: AbortSignal, headers?: Record<string, string>): RequestOptions {
  return { signal, token: sessionClient.getToken(), headers };
}

function decode<T extends z.ZodTypeAny>(schema: T, raw: unknown): z.output<T> {
  const result = decodePayload(envelope(schema), raw);
  if (!result.success) throw new ApiHttpError(400, 'ORDER_CANCELLATION_FAILED', result.error ?? result.message, false, raw);
  return result.data;
}

export const orderCancellationClient = {
  async query(caseNo: string, signal?: AbortSignal): Promise<OrderCancellationQuery> {
    const raw = await transport.get(`/api/v1/orders/${encodeURIComponent(caseNo)}/cancellation`, options(signal));
    const result = decode(OrderCancellationQuerySchema, raw);
    if (result.case_no !== caseNo) throw new Error('訂單取消案件識別不一致。');
    return result;
  },
  async preview(caseNo: string, confirmedServiceDays: ServiceDay[], signal?: AbortSignal): Promise<OrderCancellationPreview> {
    const raw = await transport.post(
      `/api/v1/orders/${encodeURIComponent(caseNo)}/cancellation/preview`,
      { confirmed_service_days: confirmedServiceDays },
      options(signal, { 'X-Correlation-ID': `orders-cancellation-preview-${caseNo}-${Date.now()}` }),
    );
    return decode(OrderCancellationPreviewSchema, raw);
  },
};
