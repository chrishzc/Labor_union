/**
 * File: holiday_client.ts
 * Description: 以即時 Session 呼叫國定假日 Query、Preview、Apply 並嚴格解碼結果。
 */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';
import {
  HolidayApplyRequestSchema,
  HolidayCalendarSchema,
  HolidayPreviewRequestSchema,
  HolidayPreviewResponseSchema,
  HolidayQueryResponseSchema,
  HolidayQuerySchema,
  HolidayReceiptResponseSchema,
  type HolidayApplyRequest,
  type HolidayCalendar,
  type HolidayPreview,
  type HolidayPreviewRequest,
  type HolidayQuery,
  type HolidayReceipt,
  type HolidayRow,
} from './holiday_schemas';
import {
  HolidayUnauthenticatedError,
  HolidayValidationError,
  mapHolidayError,
  type HolidayError,
} from './holiday_errors';

export interface HolidayRequestOptions {
  correlationId?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
  headers?: Record<string, string>;
}

export interface HolidayApplyOptions extends HolidayRequestOptions {
  /** Apply caller must provide this at runtime; optional here so negative callers can be tested before fetch. */
  idempotencyKey?: string;
}

export type HolidayQueryResult = HolidayCalendar | HolidayRow[];

export interface HolidayClient {
  query: (query: HolidayQuery, options?: HolidayRequestOptions) => Promise<HolidayCalendar>;
  queryCalendar?: (query: HolidayQuery, options?: HolidayRequestOptions) => Promise<HolidayCalendar>;
  getCalendar?: (fromDate: string, toDate: string, options?: HolidayRequestOptions) => Promise<HolidayCalendar>;
  listHolidays?: (
    fromDateOrOptions?: string | HolidayRequestOptions,
    toDate?: string,
    options?: HolidayRequestOptions,
  ) => Promise<readonly HolidayRow[]>;
  preview(request: HolidayPreviewRequest, options?: HolidayRequestOptions): Promise<HolidayPreview>;
  apply(request: HolidayApplyRequest, options: HolidayApplyOptions): Promise<HolidayReceipt>;
}

let correlationSequence = 0;

function nextCorrelationId(): string {
  correlationSequence += 1;
  return `scheduling-holiday-${correlationSequence.toString(36)}`;
}

function requireHeaderValue(value: string, field: string): string {
  const trimmed = value.trim();
  if (!trimmed || trimmed.length > 191) {
    throw new HolidayValidationError(`${field} 必須是 1 至 191 字元的非空字串。`);
  }
  return trimmed;
}

function queryParams(query: HolidayQuery): { from_date: string; to_date: string } {
  if ('fromDate' in query) {
    return { from_date: query.fromDate, to_date: query.toDate };
  }
  return { from_date: query.from_date, to_date: query.to_date };
}

function requestOptions(
  options: HolidayRequestOptions | undefined,
  idempotencyKey?: string,
): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new HolidayUnauthenticatedError();

  let headerCorrelation: string | undefined;
  let headerIdempotency: string | undefined;
  const headers: Record<string, string> = {};
  for (const [name, value] of Object.entries(options?.headers ?? {})) {
    const normalized = name.toLowerCase();
    if (normalized === 'authorization') continue;
    if (normalized === 'x-correlation-id') {
      if (headerCorrelation !== undefined) {
        throw new HolidayValidationError('X-Correlation-ID 不得重複。');
      }
      headerCorrelation = value;
      continue;
    }
    if (normalized === 'idempotency-key') {
      if (headerIdempotency !== undefined) {
        throw new HolidayValidationError('Idempotency-Key 不得重複。');
      }
      headerIdempotency = value;
      continue;
    }
    headers[name] = value;
  }

  const explicitCorrelation = options?.correlationId;
  if (explicitCorrelation !== undefined && headerCorrelation !== undefined) {
    throw new HolidayValidationError('X-Correlation-ID 不得同時由 options 與 headers 指定。');
  }
  const correlationId = requireHeaderValue(
    explicitCorrelation ?? headerCorrelation ?? nextCorrelationId(),
    'X-Correlation-ID',
  );

  if (idempotencyKey === undefined && (headerIdempotency !== undefined)) {
    throw new HolidayValidationError('Idempotency-Key 只允許用於 Apply。');
  }
  if (idempotencyKey !== undefined && headerIdempotency !== undefined) {
    throw new HolidayValidationError('Idempotency-Key 不得同時由 options 與 headers 指定。');
  }

  headers['X-Correlation-ID'] = correlationId;
  if (idempotencyKey !== undefined) {
    headers['Idempotency-Key'] = requireHeaderValue(idempotencyKey, 'Idempotency-Key');
  }
  return {
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
    headers,
    token,
  };
}

function formatIssues(error: { issues: readonly { path: (string | number)[]; message: string; code?: string }[] }): string {
  return error.issues
    .map((issue) => `[${issue.path.join('.') || '(root)'}] ${issue.message}`)
    .join(', ');
}

function validate<T>(
  schema: { safeParse(value: unknown): { success: true; data: T } | { success: false; error: { issues: readonly { path: (string | number)[]; message: string; code?: string }[] } } },
  value: unknown,
  label: string,
): T {
  const parsed = schema.safeParse(value);
  if (!parsed.success) {
    throw new HolidayValidationError(`${label} 不符合 strict contract：${formatIssues(parsed.error)}`, parsed.error);
  }
  return parsed.data;
}

function decode<T>(
  schema: {
    safeParse(value: unknown):
      | { success: true; data: { success: boolean; message: string; data: T | null; error?: string | null } }
      | { success: false; error: { issues: readonly { path: (string | number)[]; message: string; code?: string }[] } };
  },
  raw: unknown,
  operation: string,
): T {
  const parsed = schema.safeParse(raw);
  if (!parsed.success) {
    throw new ApiDecodeError(
      `國定假日 ${operation} 回應結構異常。`,
      parsed.error.issues.map((issue) => ({
        path: issue.path.join('.') || '(root)',
        message: issue.message,
        code: issue.code,
      })),
      raw,
    );
  }
  if (!parsed.data.success || parsed.data.data === null) {
    throw new ApiHttpError(
      422,
      `HOLIDAY_${operation.toUpperCase()}_EMPTY`,
      parsed.data.error ?? parsed.data.message,
      false,
      raw,
    );
  }
  return parsed.data.data;
}

function validateQuery(query: HolidayQuery): HolidayQuery {
  return validate(HolidayQuerySchema, query, '國定假日 Query');
}

function validatePreview(request: HolidayPreviewRequest): HolidayPreviewRequest {
  return validate(HolidayPreviewRequestSchema, request, '國定假日 Preview');
}

function validateApply(request: HolidayApplyRequest): HolidayApplyRequest {
  return validate(HolidayApplyRequestSchema, request, '國定假日 Apply');
}

export async function queryHolidays(
  query?: HolidayQuery,
  options?: HolidayRequestOptions,
): Promise<HolidayQueryResult> {
  const validated = query === undefined ? undefined : validateQuery(query);
  try {
    return decode(
      HolidayQueryResponseSchema,
      await transport.get<unknown>('/api/v1/holidays', {
        ...requestOptions(options),
        params: validated ? queryParams(validated) : undefined,
      }),
      'Query',
    );
  } catch (error) {
    throw mapHolidayError(error, 'query');
  }
}

export async function queryHolidayCalendar(
  query: HolidayQuery,
  options?: HolidayRequestOptions,
): Promise<HolidayCalendar> {
  const result = await queryHolidays(query, options);
  const parsed = HolidayCalendarSchema.safeParse(result);
  if (!parsed.success) {
    throw new HolidayValidationError('國定假日 ranged Query 未回傳 calendar view。', parsed.error);
  }
  return parsed.data;
}

export async function listHolidayRows(
  options?: HolidayRequestOptions,
): Promise<readonly HolidayRow[]> {
  const result = await queryHolidays(undefined, options);
  if (!Array.isArray(result)) {
    throw new HolidayValidationError('國定假日 legacy Query 未回傳 row list。');
  }
  return result;
}

export async function previewHolidayChange(
  request: HolidayPreviewRequest,
  options?: HolidayRequestOptions,
): Promise<HolidayPreview> {
  const validated = validatePreview(request);
  try {
    return decode(
      HolidayPreviewResponseSchema,
      await transport.post<unknown>('/api/v1/holidays/preview', validated, requestOptions(options)),
      'Preview',
    );
  } catch (error) {
    throw mapHolidayError(error, 'preview');
  }
}

export async function applyHolidayChange(
  request: HolidayApplyRequest,
  options: HolidayApplyOptions,
): Promise<HolidayReceipt> {
  const validated = validateApply(request);
  const key = requireHeaderValue(options.idempotencyKey ?? '', 'Idempotency-Key');
  try {
    return decode(
      HolidayReceiptResponseSchema,
      await transport.post<unknown>('/api/v1/holidays/apply', validated, requestOptions(options, key)),
      'Apply',
    );
  } catch (error) {
    throw mapHolidayError(error, 'apply', key);
  }
}

class DefaultHolidayClient implements HolidayClient {
  public query(query: HolidayQuery, options?: HolidayRequestOptions): Promise<HolidayCalendar> {
    return queryHolidayCalendar(query, options);
  }

  public queryCalendar(query: HolidayQuery, options?: HolidayRequestOptions): Promise<HolidayCalendar> {
    return queryHolidayCalendar(query, options);
  }

  public preview(request: HolidayPreviewRequest, options?: HolidayRequestOptions): Promise<HolidayPreview> {
    return previewHolidayChange(request, options);
  }

  public apply(request: HolidayApplyRequest, options: HolidayApplyOptions): Promise<HolidayReceipt> {
    return applyHolidayChange(request, options);
  }

  public getCalendar(fromDate: string, toDate: string, options?: HolidayRequestOptions): Promise<HolidayCalendar> {
    return queryHolidayCalendar({ from_date: fromDate, to_date: toDate }, options);
  }

  public listHolidays(
    fromDateOrOptions?: string | HolidayRequestOptions,
    toDate?: string,
    options?: HolidayRequestOptions,
  ): Promise<readonly HolidayRow[]> {
    if (typeof fromDateOrOptions !== 'string') return listHolidayRows(fromDateOrOptions);
    if (toDate === undefined) throw new HolidayValidationError('國定假日 list query 必須提供完整 horizon。');
    return queryHolidayCalendar({ from_date: fromDateOrOptions, to_date: toDate }, options)
      .then((calendar) => calendar.holidays);
  }
}

export function createHolidayClient(): HolidayClient {
  return new DefaultHolidayClient();
}

export const holidayClient = createHolidayClient();

// 相鄰 Scheduling client 採用的命名別名，避免 transport caller 需要知道實作類別名稱。
export const getHolidays = queryHolidays;
export const getHolidayCalendar = queryHolidayCalendar;
export const listHolidays = listHolidayRows;
export const previewHoliday = previewHolidayChange;
export const applyHoliday = applyHolidayChange;

export type { HolidayError };
export type { HolidayQuery } from './holiday_schemas';
