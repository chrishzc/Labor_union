/**
 * File: order_terminal_aggregate_client.ts
 * Description: 取得待辦看板 Beta 完全結案唯讀 aggregate。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';

const TerminalCompletionComponentSchema = z.strictObject({
  code: z.string().min(1),
  owner: z.string().min(1),
  completed: z.boolean(),
  reason: z.string().min(1).nullable(),
});

const OrderTerminalAggregateSchema = z.strictObject({
  case_no: z.string().min(1),
  applicable: z.boolean(),
  fully_closed: z.boolean(),
  components: z.array(TerminalCompletionComponentSchema),
});

const OrderTerminalAggregatePageSchema = z.strictObject({
  items: z.array(OrderTerminalAggregateSchema),
  next_cursor: z.string().min(1).nullable(),
});

const ParamsSchema = z.strictObject({
  page_size: z.number().int().min(1).max(200).optional(),
  after_case_no: z.string().trim().min(1).max(50).optional(),
  case_no_search: z.string().trim().min(1).max(50).optional(),
});

export type TerminalCompletionComponent = z.infer<typeof TerminalCompletionComponentSchema>;
export type OrderTerminalAggregate = z.infer<typeof OrderTerminalAggregateSchema>;
export type OrderTerminalAggregatePage = z.infer<typeof OrderTerminalAggregatePageSchema>;

export interface OrderTerminalAggregateQueryParams {
  page_size?: number;
  after_case_no?: string;
  case_no_search?: string;
}

export interface OrderTerminalAggregateQueryOptions {
  signal?: AbortSignal;
  token?: string | null;
  headers?: Record<string, string>;
  timeoutMs?: number;
  baseUrl?: string;
}

function requestOptions(options?: OrderTerminalAggregateQueryOptions): RequestOptions {
  return {
    signal: options?.signal,
    token: options?.token !== undefined ? options.token : sessionClient.getToken(),
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
    headers: options?.headers,
  };
}

function decodeEnvelope(raw: unknown): OrderTerminalAggregatePage {
  const envelope = decodePayload(
    z.strictObject({
      success: z.boolean(),
      message: z.string(),
      data: OrderTerminalAggregatePageSchema,
      error: z.string().nullable(),
    }),
    raw,
  );
  if (!envelope.success) {
    throw new ApiHttpError(
      400,
      'ORDER_TERMINAL_AGGREGATE_BUSINESS_ERROR',
      envelope.error ?? envelope.message,
      false,
      raw,
    );
  }
  return envelope.data;
}

export async function getOrderTerminalAggregates(
  params: OrderTerminalAggregateQueryParams = {},
  options?: OrderTerminalAggregateQueryOptions,
): Promise<OrderTerminalAggregatePage> {
  const parsed = ParamsSchema.parse(params);
  const query: NonNullable<RequestOptions['params']> = {};
  if (parsed.page_size !== undefined) query.page_size = parsed.page_size;
  if (parsed.after_case_no !== undefined) query.after_case_no = parsed.after_case_no;
  if (parsed.case_no_search !== undefined) query.case_no_search = parsed.case_no_search;

  const raw = await transport.get('/api/orders/terminal-aggregates', {
    ...requestOptions(options),
    params: query,
  });
  return decodeEnvelope(raw);
}

export const orderTerminalAggregateClient = {
  getAggregates: getOrderTerminalAggregates,
};
