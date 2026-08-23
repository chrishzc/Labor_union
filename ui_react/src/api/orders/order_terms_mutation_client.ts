/**
 * File: order_terms_mutation_client.ts
 * Description: 嚴格解碼 Orders Terms Query／Preview／Apply，並保存 fresh version 與冪等標頭契約。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';
import { decodeMutationError } from './order_mutation_errors';

const DateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const TimeSchema = z.string().regex(/^\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?$/);
const FingerprintSchema = z.string().regex(/^[0-9a-f]{64}$/);
const VersionSchema = z.number().int().nonnegative();

const NullableServiceTimeSchema = z.strictObject({
  start_time: TimeSchema.nullable(),
  end_time: TimeSchema.nullable(),
  end_day_offset: z.number().int().min(0).max(1).nullable(),
}).superRefine((value, context) => {
  const count = [value.start_time, value.end_time, value.end_day_offset]
    .filter((item) => item !== null).length;
  if (count !== 0 && count !== 3) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: '服務時段三欄必須全空或全有。' });
  }
});

export const OrderTermsInputSchema = z.strictObject({
  planned_start_date: DateSchema,
  service_days: z.number().int().positive(),
  service_hours_per_day: z.number().int().positive(),
  requires_cooking: z.boolean(),
  floor_fee_ntd: z.number().int().nonnegative(),
  service_time: z.strictObject({
    start_time: TimeSchema,
    end_time: TimeSchema,
    end_day_offset: z.number().int().min(0).max(1),
  }),
});

export const OrderTermsViewSchema = z.strictObject({
  planned_start_date: DateSchema,
  service_days: z.number().int().positive(),
  service_hours_per_day: z.number().int().positive(),
  requires_cooking: z.boolean().nullable(),
  floor_fee_ntd: z.number().int().nonnegative(),
  service_time: NullableServiceTimeSchema,
});

export const OrderTermsQuerySchema = z.strictObject({
  case_no: z.string().min(1),
  order_version: VersionSchema,
  scheduling_version: VersionSchema,
  scheduling_generation: VersionSchema,
  client_finance_version: VersionSchema,
  payroll_version: VersionSchema,
  service_data_locked: z.boolean(),
  terms: OrderTermsViewSchema,
});

export const OrderTermsPreviewSchema = z.strictObject({
  before: OrderTermsViewSchema,
  after: OrderTermsViewSchema,
  order_version: VersionSchema,
  scheduling_version: VersionSchema,
  scheduling_generation: VersionSchema,
  client_finance_version: VersionSchema,
  payroll_version: VersionSchema,
  scheduling: z.record(z.string(), z.unknown()),
  client_finance_impact: z.record(z.string(), z.unknown()),
  payroll_impact: z.record(z.string(), z.unknown()),
  lifecycle_impact: z.record(z.string(), z.unknown()),
  preview_fingerprint: FingerprintSchema,
});

export const OrderTermsReceiptSchema = z.strictObject({
  case_no: z.string().min(1),
  order_version: VersionSchema,
  scheduling_version: VersionSchema,
  scheduling_generation: VersionSchema,
  client_finance_version: VersionSchema,
  payroll_version: VersionSchema,
  lifecycle_status: z.string().min(1),
  service_data_lock_formed: z.boolean(),
  cancelled_assignment_ids: z.array(z.number().int().positive()),
  created_assignment_keys: z.array(z.string().min(1)),
  official_service_day_count: z.number().int().nonnegative(),
  official_service_hours: z.number().int().nonnegative(),
  preview_fingerprint: FingerprintSchema,
});

export const OrderTermsPreviewPayloadSchema = z.strictObject({
  proposed_terms: OrderTermsInputSchema,
});

export const OrderTermsApplyPayloadSchema = OrderTermsPreviewPayloadSchema.extend({
  expected_order_version: VersionSchema,
  expected_scheduling_version: VersionSchema,
  expected_client_finance_version: VersionSchema,
  expected_payroll_version: VersionSchema,
  preview_fingerprint: FingerprintSchema,
  reason: z.string().trim().min(1).max(500),
}).strict();

export type OrderTermsQuery = z.infer<typeof OrderTermsQuerySchema>;
export type OrderTermsPreview = z.infer<typeof OrderTermsPreviewSchema>;
export type OrderTermsReceipt = z.infer<typeof OrderTermsReceiptSchema>;
export type OrderTermsPreviewPayload = z.infer<typeof OrderTermsPreviewPayloadSchema>;
export type OrderTermsApplyPayload = z.infer<typeof OrderTermsApplyPayloadSchema>;

export interface OrderTermsRequestOptions {
  correlationId?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  headers?: Record<string, string>;
}

export interface OrderTermsApplyOptions extends OrderTermsRequestOptions {
  idempotencyKey: string;
}

const envelope = <T extends z.ZodTypeAny>(schema: T) => z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: schema,
  error: z.string().nullable(),
});

function caseIdentity(caseNo: string): string {
  const value = caseNo.trim();
  if (!value || value.length > 50) throw new Error('案件編號必須為 1 至 50 字元。');
  return value;
}

function commandKey(value: unknown): string {
  if (typeof value !== 'string' || !value.trim() || value.trim().length > 191) {
    throw new Error('Idempotency-Key 必須為 1 至 191 字元。');
  }
  return value.trim();
}

function options(
  source?: OrderTermsRequestOptions,
  requiredHeaders?: Record<string, string>,
): RequestOptions {
  const token = sessionClient.getToken();
  return {
    signal: source?.signal,
    timeoutMs: source?.timeoutMs,
    ...(token ? { token } : {}),
    headers: { ...source?.headers, ...requiredHeaders },
  };
}

function decode<T extends z.ZodTypeAny>(schema: T, raw: unknown): z.output<T> {
  const result = decodePayload(envelope(schema), raw);
  if (!result.success) {
    throw new ApiHttpError(
      400, 'ORDERS_TERMS_BUSINESS_ERROR', result.error ?? result.message, false, raw,
    );
  }
  return result.data;
}

async function run<T>(caseNo: string, endpoint: string, operation: () => Promise<T>): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    throw decodeMutationError(error, { caseNo, endpoint });
  }
}

export const orderTermsMutationClient = {
  async query(caseNo: string, source?: OrderTermsRequestOptions): Promise<OrderTermsQuery> {
    const canonical = caseIdentity(caseNo);
    const endpoint = `/api/v1/orders/${encodeURIComponent(canonical)}/terms`;
    return run(canonical, endpoint, async () => {
      const result = decode(
        OrderTermsQuerySchema,
        await transport.get(endpoint, options(source)),
      );
      if (result.case_no !== canonical) throw new Error('訂單條款案件識別不一致。');
      return result;
    });
  },

  async preview(
    caseNo: string,
    payload: OrderTermsPreviewPayload,
    source?: OrderTermsRequestOptions,
  ): Promise<OrderTermsPreview> {
    const canonical = caseIdentity(caseNo);
    const parsed = OrderTermsPreviewPayloadSchema.parse(payload);
    const endpoint = `/api/v1/orders/${encodeURIComponent(canonical)}/terms/preview`;
    const correlation = source?.correlationId
      ?? `orders-terms-preview-${canonical}-${Date.now()}`;
    return run(canonical, endpoint, async () => decode(
      OrderTermsPreviewSchema,
      await transport.post(
        endpoint,
        parsed,
        options(source, { 'X-Correlation-ID': correlation }),
      ),
    ));
  },

  async apply(
    caseNo: string,
    payload: OrderTermsApplyPayload,
    source: OrderTermsApplyOptions,
  ): Promise<OrderTermsReceipt> {
    const canonical = caseIdentity(caseNo);
    const parsed = OrderTermsApplyPayloadSchema.parse(payload);
    const key = commandKey(source?.idempotencyKey);
    const endpoint = `/api/v1/orders/${encodeURIComponent(canonical)}/terms/apply`;
    const correlation = source?.correlationId
      ?? `orders-terms-apply-${canonical}-${Date.now()}`;
    return run(canonical, endpoint, async () => {
      const result = decode(OrderTermsReceiptSchema, await transport.post(
        endpoint,
        parsed,
        options(source, {
          'X-Correlation-ID': correlation,
          'Idempotency-Key': key,
        }),
      ));
      if (result.case_no !== canonical) throw new Error('訂單條款收據案件識別不一致。');
      return result;
    });
  },
};
