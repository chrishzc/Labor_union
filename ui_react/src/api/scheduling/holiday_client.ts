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
  HolidayDateSchema,
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
  parseCsv(csvText: string): HolidayCsvParseResult;
  previewCsv(parsed: HolidayCsvParseResult, options?: HolidayRequestOptions): Promise<HolidayCsvBatchPreview>;
  applyCsv(
    batch: HolidayCsvBatchPreview,
    reason: string,
    options: HolidayApplyOptions,
  ): Promise<HolidayCsvBatchResult>;
}

export interface HolidayCsvRow {
  source_row: number;
  holiday_date: string;
  weekday: string;
  is_holiday: true;
  holiday_name: string;
  note: string;
}

export interface HolidayCsvParseResult {
  year: number | null;
  rows: readonly HolidayCsvRow[];
  blank_weekend_rows: number;
  issues: readonly string[];
}

export interface HolidayCsvBatchPreview {
  parsed: HolidayCsvParseResult;
  entries: readonly { row: HolidayCsvRow; preview: HolidayPreview }[];
  skipped: readonly { holiday_date: string; reason: string }[];
  issues: readonly string[];
  zero_write: true;
}

export interface HolidayCsvBatchResult {
  attempted: number;
  applied: number;
  unchanged: number;
  skipped: number;
  replayed: number;
  readback_status: 'not_run' | 'observed' | 'failed';
  readback_error?: string;
  receipts: readonly HolidayReceipt[];
  failures: readonly { holiday_date: string; message: string }[];
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

function csvRecords(csvText: string): { records: string[][]; unclosed_quote: boolean } {
  const text = csvText.replace(/^\uFEFF/, '');
  const records: string[][] = [];
  let record: string[] = [];
  let field = '';
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (character === '"') {
      if (quoted && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (character === ',' && !quoted) {
      record.push(field.trim());
      field = '';
    } else if ((character === '\n' || character === '\r') && !quoted) {
      if (character === '\r' && text[index + 1] === '\n') index += 1;
      record.push(field.trim());
      if (record.some((value) => value !== '')) records.push(record);
      record = [];
      field = '';
    } else {
      field += character;
    }
  }
  if (field !== '' || record.length > 0) {
    record.push(field.trim());
    if (record.some((value) => value !== '')) records.push(record);
  }
  return { records, unclosed_quote: quoted };
}

function normalizedCsvHeader(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/[\s_\-]/g, '');
}

function csvColumn(headers: readonly string[], aliases: readonly string[]): number {
  const normalized = headers.map(normalizedCsvHeader);
  const normalizedAliases = aliases.map(normalizedCsvHeader);
  return normalized.findIndex((header) => normalizedAliases.includes(header));
}

function csvValue(row: readonly string[], column: number): string {
  return column === -1 ? '' : (row[column] ?? '').trim();
}

function parseHolidayFlag(value: string): boolean | null {
  const normalized = value.trim().toLocaleLowerCase();
  if (normalized === '2') return true;
  if (normalized === '0') return false;
  return null;
}

function isWeekend(isoDate: string): boolean {
  const day = new Date(`${isoDate}T00:00:00Z`).getUTCDay();
  return day === 0 || day === 6;
}

export function parseHolidayCsv(csvText: string): HolidayCsvParseResult {
  const parsedRecords = csvRecords(csvText);
  if (parsedRecords.unclosed_quote) {
    return { year: null, rows: [], blank_weekend_rows: 0, issues: ['CSV 引號未關閉，已拒絕匯入。'] };
  }
  const records = parsedRecords.records;
  if (records.length === 0) {
    return { year: null, rows: [], blank_weekend_rows: 0, issues: ['CSV 沒有資料。'] };
  }
  const headers = records[0];
  const dateColumn = csvColumn(headers, ['date', '日期', '西元日期', 'holidaydate']);
  const weekdayColumn = csvColumn(headers, ['weekday', '星期', '週']);
  const holidayColumn = csvColumn(headers, ['isholiday', '是否放假', 'holiday', 'isrestday']);
  const noteColumn = csvColumn(headers, ['note', '備註', '節日名稱', 'holidayname']);
  const missing = [
    dateColumn === -1 ? 'date/日期' : null,
    weekdayColumn === -1 ? 'weekday/星期' : null,
    holidayColumn === -1 ? 'is holiday/是否放假' : null,
    noteColumn === -1 ? 'note/備註' : null,
  ].filter((value): value is string => value !== null);
  if (missing.length > 0) {
    return {
      year: null,
      rows: [],
      blank_weekend_rows: 0,
      issues: [`CSV 缺少必要欄位：${missing.join('、')}。`],
    };
  }

  const rows: HolidayCsvRow[] = [];
  const issues: string[] = [];
  const seen = new Set<string>();
  let blankWeekendRows = 0;
  let year: number | null = null;
  records.slice(1).forEach((record, offset) => {
    const sourceRow = offset + 2;
    const holidayDate = csvValue(record, dateColumn);
    const weekday = csvValue(record, weekdayColumn);
    const flag = parseHolidayFlag(csvValue(record, holidayColumn));
    const note = csvValue(record, noteColumn);
    const dateResult = HolidayDateSchema.safeParse(holidayDate);
    if (!dateResult.success) {
      issues.push(`第 ${sourceRow} 列日期無效：${holidayDate || '(空白)'}`);
      return;
    }
    const rowYear = Number(holidayDate.slice(0, 4));
    if (year === null) year = rowYear;
    if (rowYear !== year) {
      issues.push(`第 ${sourceRow} 列與 CSV 其他資料不是同一年度。`);
      return;
    }
    if (!weekday) {
      issues.push(`第 ${sourceRow} 列缺少星期。`);
      return;
    }
    if (flag === null) {
      issues.push(`第 ${sourceRow} 列是否放假值無法辨識。`);
      return;
    }
    if (isWeekend(holidayDate) && !note) {
      blankWeekendRows += 1;
      return;
    }
    if (!flag) return;
    if (!note) {
      issues.push(`第 ${sourceRow} 列國定假日缺少備註或節日名稱。`);
      return;
    }
    if (seen.has(holidayDate)) {
      issues.push(`第 ${sourceRow} 列日期重複：${holidayDate}。`);
      return;
    }
    seen.add(holidayDate);
    rows.push({
      source_row: sourceRow,
      holiday_date: holidayDate,
      weekday,
      is_holiday: true,
      holiday_name: note,
      note,
    });
  });
  if (rows.length === 0 && issues.length === 0) issues.push('CSV 沒有可匯入的國定假日資料。');
  return { year, rows, blank_weekend_rows: blankWeekendRows, issues };
}

export async function previewHolidayCsv(
  parsed: HolidayCsvParseResult,
  options?: HolidayRequestOptions,
): Promise<HolidayCsvBatchPreview> {
  const entries: { row: HolidayCsvRow; preview: HolidayPreview }[] = [];
  const skipped: { holiday_date: string; reason: string }[] = [];
  const issues = [...parsed.issues];
  for (const row of parsed.rows) {
    try {
      const calendar = await queryHolidayCalendar(
        { from_date: row.holiday_date, to_date: row.holiday_date },
        options,
      );
      const existing = calendar.holidays.find((holiday) => holiday.holiday_date === row.holiday_date);
      if (existing?.holiday_name === row.holiday_name) {
        skipped.push({ holiday_date: row.holiday_date, reason: '既有政策相同，略過重複套用。' });
        continue;
      }
      const preview = await previewHolidayChange({
        action: 'upsert',
        holiday_date: row.holiday_date,
        holiday_name: row.holiday_name,
        ...(existing ? { is_double_pay_default: existing.is_double_pay_default } : {}),
        from_date: row.holiday_date,
        to_date: row.holiday_date,
      }, options);
      if (calendar.planning_horizon.from_date !== row.holiday_date) {
        issues.push(`${row.holiday_date} 回讀區間不一致。`);
      }
      entries.push({ row, preview });
    } catch (error) {
      issues.push(`${row.holiday_date} 預覽失敗：${error instanceof Error ? error.message : '未知錯誤'}。`);
    }
  }
  return { parsed, entries, skipped, issues, zero_write: true };
}

export async function applyHolidayCsv(
  batch: HolidayCsvBatchPreview,
  reason: string,
  options: HolidayApplyOptions,
): Promise<HolidayCsvBatchResult> {
  const baseKey = requireHeaderValue(options.idempotencyKey ?? '', 'Idempotency-Key');
  const receipts: HolidayReceipt[] = [];
  const failures: { holiday_date: string; message: string }[] = [];
  const skipped = [...batch.skipped];
  for (const entry of batch.entries) {
    try {
      const freshCalendar = await queryHolidayCalendar({
        from_date: entry.row.holiday_date,
        to_date: entry.row.holiday_date,
      }, options);
      const existing = freshCalendar.holidays.find((holiday) => holiday.holiday_date === entry.row.holiday_date);
      if (existing?.holiday_name === entry.row.holiday_name) {
        skipped.push({ holiday_date: entry.row.holiday_date, reason: '套用前回讀已相同，略過重複套用。' });
        continue;
      }
      const freshPreview = await previewHolidayChange({
        action: 'upsert',
        holiday_date: entry.row.holiday_date,
        holiday_name: entry.row.holiday_name,
        ...(existing ? { is_double_pay_default: existing.is_double_pay_default } : {}),
        from_date: freshCalendar.planning_horizon.from_date,
        to_date: freshCalendar.planning_horizon.to_date,
      }, options);
      const receipt = await applyHolidayChange({
        ...freshPreview.command,
        expected_calendar_version: freshPreview.command.expected_calendar_version,
        preview_fingerprint: freshPreview.preview_fingerprint,
        reason,
      }, { ...options, idempotencyKey: `${baseKey}-${entry.row.holiday_date}` });
      receipts.push(receipt);
    } catch (error) {
      failures.push({
        holiday_date: entry.row.holiday_date,
        message: error instanceof Error ? error.message : '未知錯誤',
      });
    }
  }
  return {
    attempted: batch.entries.length,
    applied: receipts.filter((receipt) => receipt.changed).length,
    unchanged: receipts.filter((receipt) => !receipt.changed).length,
    skipped: skipped.length,
    replayed: 0,
    readback_status: 'not_run',
    receipts,
    failures,
  };
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

  public parseCsv(csvText: string): HolidayCsvParseResult {
    return parseHolidayCsv(csvText);
  }

  public previewCsv(parsed: HolidayCsvParseResult, options?: HolidayRequestOptions): Promise<HolidayCsvBatchPreview> {
    return previewHolidayCsv(parsed, options);
  }

  public applyCsv(
    batch: HolidayCsvBatchPreview,
    reason: string,
    options: HolidayApplyOptions,
  ): Promise<HolidayCsvBatchResult> {
    return applyHolidayCsv(batch, reason, options);
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
