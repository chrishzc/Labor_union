/**
 * File: order_query_client.ts
 * Description: 只呼叫八個核准 Orders GET，並以 strict decode、fresh token 與短時 single-flight 發送。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';
import { mapHttpErrorToOrderError, OrderValidationError } from './order_query_errors';
import {
  ActualStartSchema,
  AssignmentPlanSchema,
  ContractCompletionSchema,
  FormManagementContextSchema,
  OrderCalendarDetailSchema,
  OrderDetailSchema,
  OrderSummaryPageSchema,
  OrderTermsSchema,
  createOrderQueryEnvelopeSchema,
  type ActualStart,
  type AssignmentPlan,
  type ContractCompletion,
  type FormManagementContext,
  type OrderCalendarDetail,
  type OrderDetail,
  type OrderSummaryPage,
  type OrderTerms,
} from './order_query_schemas';

export interface OrderQueryOptions {
  signal?: AbortSignal;
  token?: string | null;
  headers?: Record<string, string>;
  timeoutMs?: number;
  ifNoneMatch?: string;
  baseUrl?: string;
}

export interface OrderSummaryQueryParams {
  page_size?: number;
  after_case_no?: string;
  query_text?: string;
  lifecycle_scope?: 'all' | 'unfinished';
}

export interface OrdersQueryClient {
  getOrderSummaries(params?: OrderSummaryQueryParams, options?: OrderQueryOptions): Promise<OrderSummaryPage>;
  getOrderDetail(caseNo: string, options?: OrderQueryOptions): Promise<OrderDetail>;
  getOrderCalendarDetail(caseNo: string, options?: OrderQueryOptions): Promise<OrderCalendarDetail>;
  getOrderTerms(caseNo: string, options?: OrderQueryOptions): Promise<OrderTerms>;
  getFormManagementContext(caseNo: string, options?: OrderQueryOptions): Promise<FormManagementContext>;
  getActualStart(caseNo: string, options?: OrderQueryOptions): Promise<ActualStart>;
  getContractCompletion(caseNo: string, options?: OrderQueryOptions): Promise<ContractCompletion>;
  getAssignmentPlan(caseNo: string, options?: OrderQueryOptions): Promise<AssignmentPlan>;
}

const SummaryParamsSchema = z.strictObject({
  page_size: z.number().int().min(1).max(200).optional(),
  after_case_no: z.string().optional(),
  query_text: z.string().optional(),
  lifecycle_scope: z.enum(['all', 'unfinished']).optional(),
});

export class OrderSummaryContinuationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'OrderSummaryContinuationError';
  }
}

export async function loadAllOrderSummaries(
  query: (params: OrderSummaryQueryParams, options?: OrderQueryOptions) => Promise<OrderSummaryPage>,
  params: OrderSummaryQueryParams = {},
  options?: OrderQueryOptions,
): Promise<OrderSummaryPage> {
  const parsed = SummaryParamsSchema.parse(params);
  const itemsByCaseNo = new Map<string, OrderSummaryPage['items'][number]>();
  const seenCursors = new Set<string>();
  let afterCaseNo = parsed.after_case_no?.trim();
  let lastCursor: string | undefined = afterCaseNo;
  let lastPage: OrderSummaryPage | null = null;

  while (true) {
    const page = await query(
      { ...parsed, ...(afterCaseNo ? { after_case_no: afterCaseNo } : {}) },
      options,
    );
    lastPage = page;
    for (const item of page.items) itemsByCaseNo.set(item.case_no, item);
    const nextCursor = page.next_cursor;
    if (nextCursor === null) break;
    if (page.items.length === 0 || seenCursors.has(nextCursor) || (lastCursor !== undefined && nextCursor <= lastCursor)) {
      throw new OrderSummaryContinuationError('Orders 摘要 continuation cursor 未前進，無法取得完整清單。');
    }
    const lastItem = page.items[page.items.length - 1];
    if (lastItem.case_no !== nextCursor) {
      throw new OrderSummaryContinuationError('Orders 摘要 continuation cursor 與頁尾案件不一致。');
    }
    seenCursors.add(nextCursor);
    lastCursor = nextCursor;
    afterCaseNo = nextCursor;
  }

  if (!lastPage) throw new OrderSummaryContinuationError('Orders 摘要未取得任何頁面。');
  return {
    items: [...itemsByCaseNo.values()].sort((left, right) => left.case_no.localeCompare(right.case_no)),
    next_cursor: null,
    etag: lastPage.etag,
  };
}

const summaryFlights = new Map<string, Promise<OrderSummaryPage>>();
const SUMMARY_BURST_TTL_MS = 250;

function sanitizeCaseNo(caseNo: string): string {
  const trimmed = caseNo.trim();
  if (!trimmed) {
    throw new OrderValidationError('案件編號 (case_no) 不得為空字串');
  }
  return trimmed;
}

function mergeQueryOptions(defaults?: OrderQueryOptions, custom?: OrderQueryOptions): OrderQueryOptions {
  return {
    signal: custom?.signal ?? defaults?.signal,
    token: custom?.token !== undefined ? custom.token : defaults?.token,
    timeoutMs: custom?.timeoutMs ?? defaults?.timeoutMs,
    baseUrl: custom?.baseUrl !== undefined ? custom.baseUrl : defaults?.baseUrl,
    ifNoneMatch: custom?.ifNoneMatch ?? defaults?.ifNoneMatch,
    headers: { ...(defaults?.headers ?? {}), ...(custom?.headers ?? {}) },
  };
}

function requestOptions(options?: OrderQueryOptions): RequestOptions {
  const headers = { ...(options?.headers ?? {}) };
  if (options?.ifNoneMatch) headers['If-None-Match'] = options.ifNoneMatch;
  return {
    signal: options?.signal,
    token: options?.token !== undefined ? options.token : sessionClient.getToken(),
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
    headers,
  };
}

function decodeOrderEnvelope<T extends z.ZodTypeAny>(dataSchema: T, raw: unknown): z.output<T> {
  const envelope = decodePayload(createOrderQueryEnvelopeSchema(dataSchema), raw);
  if (!envelope.success) {
    throw new ApiHttpError(
      400,
      'ORDERS_QUERY_BUSINESS_ERROR',
      envelope.error ?? envelope.message,
      false,
      raw
    );
  }
  return envelope.data;
}

async function readResolved<T extends z.ZodTypeAny>(
  endpoint: string,
  schema: T,
  resolvedOptions: RequestOptions,
  caseNo?: string,
  params?: RequestOptions['params']
): Promise<z.output<T>> {
  try {
    const raw = await transport.get(endpoint, { ...resolvedOptions, params });
    return decodeOrderEnvelope(schema, raw);
  } catch (error) {
    if (error instanceof ApiHttpError) {
      throw mapHttpErrorToOrderError(error, { endpoint, caseNo });
    }
    throw error;
  }
}

function read<T extends z.ZodTypeAny>(
  endpoint: string,
  schema: T,
  options?: OrderQueryOptions,
  caseNo?: string,
  params?: RequestOptions['params']
): Promise<z.output<T>> {
  return readResolved(endpoint, schema, requestOptions(options), caseNo, params);
}

function sortedEntries(values?: Record<string, string>) {
  return Object.entries(values ?? {}).sort(([left], [right]) => left.localeCompare(right));
}

function summaryFlightKey(
  options: RequestOptions,
  params: NonNullable<RequestOptions['params']>
): string {
  return JSON.stringify({
    baseUrl: options.baseUrl ?? '',
    token: options.token ?? null,
    timeoutMs: options.timeoutMs ?? null,
    headers: sortedEntries(options.headers),
    params: Object.entries(params).sort(([left], [right]) => left.localeCompare(right)),
  });
}

export function getOrderSummaries(
  params: OrderSummaryQueryParams = {},
  options?: OrderQueryOptions
): Promise<OrderSummaryPage> {
  const parsed = SummaryParamsSchema.parse(params);
  const queryParams: NonNullable<RequestOptions['params']> = {};
  if (parsed.page_size !== undefined) queryParams.page_size = parsed.page_size;
  const afterCaseNo = parsed.after_case_no?.trim();
  if (afterCaseNo) queryParams.after_case_no = afterCaseNo;
  const queryText = parsed.query_text?.trim();
  if (queryText) queryParams.query_text = queryText;
  if (parsed.lifecycle_scope) queryParams.lifecycle_scope = parsed.lifecycle_scope;
  const resolvedOptions = requestOptions(options);
  if (resolvedOptions.signal) {
    return readResolved(
      '/api/v1/orders/summaries',
      OrderSummaryPageSchema,
      resolvedOptions,
      undefined,
      queryParams
    );
  }

  const flightKey = summaryFlightKey(resolvedOptions, queryParams);
  const existing = summaryFlights.get(flightKey);
  if (existing) return existing;

  const pending = readResolved(
    '/api/v1/orders/summaries',
    OrderSummaryPageSchema,
    resolvedOptions,
    undefined,
    queryParams
  );
  summaryFlights.set(flightKey, pending);
  const clear = () => {
    if (summaryFlights.get(flightKey) === pending) summaryFlights.delete(flightKey);
  };
  void pending.then(
    () => { setTimeout(clear, SUMMARY_BURST_TTL_MS); },
    clear
  );
  return pending;
}

export function getOrderDetail(caseNo: string, options?: OrderQueryOptions): Promise<OrderDetail> {
  const validCaseNo = sanitizeCaseNo(caseNo);
  const endpoint = `/api/v1/orders/${encodeURIComponent(validCaseNo)}`;
  return read(endpoint, OrderDetailSchema, options, validCaseNo);
}

export function getOrderCalendarDetail(
  caseNo: string,
  options?: OrderQueryOptions
): Promise<OrderCalendarDetail> {
  const validCaseNo = sanitizeCaseNo(caseNo);
  const endpoint = `/api/v1/orders/${encodeURIComponent(validCaseNo)}/calendar-detail`;
  return read(endpoint, OrderCalendarDetailSchema, options, validCaseNo);
}

export function getOrderTerms(caseNo: string, options?: OrderQueryOptions): Promise<OrderTerms> {
  const validCaseNo = sanitizeCaseNo(caseNo);
  const endpoint = `/api/v1/orders/${encodeURIComponent(validCaseNo)}/terms`;
  return read(endpoint, OrderTermsSchema, options, validCaseNo);
}

export function getFormManagementContext(
  caseNo: string,
  options?: OrderQueryOptions
): Promise<FormManagementContext> {
  const validCaseNo = sanitizeCaseNo(caseNo);
  const endpoint = `/api/v1/orders/${encodeURIComponent(validCaseNo)}/form-management-context`;
  return read(endpoint, FormManagementContextSchema, options, validCaseNo);
}

export function getActualStart(caseNo: string, options?: OrderQueryOptions): Promise<ActualStart> {
  const validCaseNo = sanitizeCaseNo(caseNo);
  const endpoint = `/api/v1/orders/${encodeURIComponent(validCaseNo)}/actual-start`;
  return read(endpoint, ActualStartSchema, options, validCaseNo);
}

export function getContractCompletion(
  caseNo: string,
  options?: OrderQueryOptions
): Promise<ContractCompletion> {
  const validCaseNo = sanitizeCaseNo(caseNo);
  const endpoint = `/api/v1/orders/${encodeURIComponent(validCaseNo)}/contract-completion`;
  return read(endpoint, ContractCompletionSchema, options, validCaseNo);
}

export function getAssignmentPlan(caseNo: string, options?: OrderQueryOptions): Promise<AssignmentPlan> {
  const validCaseNo = sanitizeCaseNo(caseNo);
  const endpoint = `/api/v1/orders/${encodeURIComponent(validCaseNo)}/assignment-plan`;
  return read(endpoint, AssignmentPlanSchema, options, validCaseNo);
}

export class DefaultOrdersQueryClient implements OrdersQueryClient {
  private readonly defaultOptions?: OrderQueryOptions;

  constructor(defaultOptions?: OrderQueryOptions) {
    this.defaultOptions = defaultOptions;
  }

  getOrderSummaries(params?: OrderSummaryQueryParams, options?: OrderQueryOptions) {
    return getOrderSummaries(params, mergeQueryOptions(this.defaultOptions, options));
  }
  getOrderDetail(caseNo: string, options?: OrderQueryOptions) {
    return getOrderDetail(caseNo, mergeQueryOptions(this.defaultOptions, options));
  }
  getOrderCalendarDetail(caseNo: string, options?: OrderQueryOptions) {
    return getOrderCalendarDetail(caseNo, mergeQueryOptions(this.defaultOptions, options));
  }
  getOrderTerms(caseNo: string, options?: OrderQueryOptions) {
    return getOrderTerms(caseNo, mergeQueryOptions(this.defaultOptions, options));
  }
  getFormManagementContext(caseNo: string, options?: OrderQueryOptions) {
    return getFormManagementContext(caseNo, mergeQueryOptions(this.defaultOptions, options));
  }
  getActualStart(caseNo: string, options?: OrderQueryOptions) {
    return getActualStart(caseNo, mergeQueryOptions(this.defaultOptions, options));
  }
  getContractCompletion(caseNo: string, options?: OrderQueryOptions) {
    return getContractCompletion(caseNo, mergeQueryOptions(this.defaultOptions, options));
  }
  getAssignmentPlan(caseNo: string, options?: OrderQueryOptions) {
    return getAssignmentPlan(caseNo, mergeQueryOptions(this.defaultOptions, options));
  }
}

export function createOrdersQueryClient(defaultOptions?: OrderQueryOptions): OrdersQueryClient {
  return new DefaultOrdersQueryClient(defaultOptions);
}

export const ordersQueryClient: OrdersQueryClient = new DefaultOrdersQueryClient();
