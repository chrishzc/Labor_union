/**
 * File: holiday_flow_adapter.ts
 * Description: 協調國定假日 Query、Preview、Apply、receipt 與 re-query，保留重試與觀察失敗邊界。
 */
import {
  holidayClient,
  type HolidayApplyOptions,
  type HolidayClient,
  type HolidayQueryResult,
  type HolidayQuery,
  type HolidayRequestOptions,
} from '../../api/scheduling/holiday_client';
import {
  HolidayContractError as HolidayFlowContractError,
  HolidayError,
} from '../../api/scheduling/holiday_errors';
import type {
  HolidayAction,
  HolidayCalendar,
  HolidayHorizon,
  HolidayPreview,
  HolidayPreviewRequest,
  HolidayReceipt,
  HolidayRow,
  HolidayApplyRequest,
} from '../../api/scheduling/holiday_schemas';

export type {
  HolidayAction,
  HolidayCalendar,
  HolidayHorizon,
  HolidayPreview,
  HolidayPreviewRequest,
  HolidayReceipt,
  HolidayRow,
  HolidayApplyRequest,
};

export interface HolidayFlowClient {
  readonly query?: HolidayClient['query'];
  readonly queryCalendar?: HolidayClient['queryCalendar'];
  readonly preview: HolidayClient['preview'];
  readonly apply: HolidayClient['apply'];
}

export interface HolidayFlowOptions extends HolidayRequestOptions {
  readonly client?: HolidayFlowClient;
  readonly idempotencyKey?: string;
}

export type HolidayFlowError = HolidayError;
export { HolidayFlowContractError };

export type HolidayFlowStatus =
  | 'idle'
  | 'query_loading'
  | 'query_ready'
  | 'preview_loading'
  | 'preview_ready'
  | 'apply_pending'
  | 'receipt_received'
  | 'requery_loading'
  | 'observed'
  | 'typed_error'
  | 'stale'
  | 'conflict'
  | 'outcome_unknown'
  | 'observation_failed';

export interface HolidayFlowDraft {
  readonly flowKey: string;
  readonly query: HolidayQuery | null;
  readonly calendar: HolidayCalendar | null;
  readonly previewRequest: HolidayPreviewRequest | null;
  readonly preview: HolidayPreview | null;
  readonly applyRequest: HolidayApplyRequest | null;
  readonly idempotencyKey: string;
  readonly correlationId: string;
  readonly receipt: HolidayReceipt | null;
  readonly status: HolidayFlowStatus;
  readonly error: HolidayFlowError | null;
  readonly replayed: boolean;
}

export type HolidayMachineState =
  | { readonly type: 'idle'; readonly flowKey: string }
  | { readonly type: 'query_loading'; readonly flowKey: string }
  | { readonly type: 'query_ready'; readonly flowKey: string; readonly calendar: HolidayCalendar }
  | { readonly type: 'preview_loading'; readonly flowKey: string; readonly request: HolidayPreviewRequest }
  | { readonly type: 'preview_ready'; readonly flowKey: string; readonly request: HolidayPreviewRequest; readonly preview: HolidayPreview }
  | { readonly type: 'apply_pending'; readonly flowKey: string; readonly preview: HolidayPreview; readonly request: HolidayApplyRequest; readonly idempotencyKey: string }
  | { readonly type: 'receipt_received'; readonly flowKey: string; readonly receipt: HolidayReceipt }
  | { readonly type: 'requery_loading'; readonly flowKey: string; readonly receipt: HolidayReceipt }
  | { readonly type: 'observed'; readonly flowKey: string; readonly calendar: HolidayCalendar; readonly receipt: HolidayReceipt; readonly replayed: boolean }
  | { readonly type: 'typed_error'; readonly flowKey: string; readonly error: HolidayFlowError }
  | { readonly type: 'stale'; readonly flowKey: string; readonly error: HolidayFlowError; readonly requiresFreshQuery: true; readonly requiresFreshPreview: true }
  | { readonly type: 'conflict'; readonly flowKey: string; readonly error: HolidayFlowError }
  | { readonly type: 'outcome_unknown'; readonly flowKey: string; readonly preview: HolidayPreview; readonly request: HolidayApplyRequest; readonly idempotencyKey: string; readonly error: HolidayFlowError }
  | { readonly type: 'observation_failed'; readonly flowKey: string; readonly receipt: HolidayReceipt; readonly error: HolidayFlowError };

type MutableDraft = {
  flowKey: string;
  query: HolidayQuery | null;
  calendar: HolidayCalendar | null;
  previewRequest: HolidayPreviewRequest | null;
  preview: HolidayPreview | null;
  applyRequest: HolidayApplyRequest | null;
  idempotencyKey: string;
  correlationId: string;
  receipt: HolidayReceipt | null;
  status: HolidayFlowStatus;
  error: HolidayFlowError | null;
  replayed: boolean;
};

const DEFAULT_FLOW_KEY = 'scheduling-holidays';
const HOLIDAY_CLIENT = holidayClient as unknown as HolidayFlowClient;

function newKey(prefix: string): string {
  if (typeof globalThis.crypto !== 'undefined' && typeof globalThis.crypto.randomUUID === 'function') {
    return `${prefix}-${globalThis.crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

function stableValue(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value) ?? 'undefined';
  if (Array.isArray(value)) return `[${value.map(stableValue).join(',')}]`;
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).sort().map((key) => `${JSON.stringify(key)}:${stableValue(record[key])}`).join(',')}}`;
}

function sameValue(left: unknown, right: unknown): boolean {
  return stableValue(left) === stableValue(right);
}

function copyRequest(request: HolidayPreviewRequest): HolidayPreviewRequest {
  return { ...request };
}

function copyApplyRequest(request: HolidayApplyRequest): HolidayApplyRequest {
  return { ...request };
}

function copyCalendar(calendar: HolidayCalendar): HolidayCalendar {
  return { ...calendar, planning_horizon: { ...calendar.planning_horizon }, holidays: calendar.holidays.map((row) => ({ ...row })) };
}

function requireHorizon(request: HolidayPreviewRequest): HolidayHorizon {
  if (!request.from_date || !request.to_date) {
    throw new HolidayFlowContractError('國定假日 Preview／Apply 必須攜帶完整 planning horizon。');
  }
  return { from_date: request.from_date, to_date: request.to_date };
}

function requestOptionsOf(
  options: HolidayFlowOptions | undefined,
  correlationId: string,
): HolidayRequestOptions {
  if (!options) return { correlationId };
  const { client: _client, idempotencyKey: _idempotencyKey, ...requestOptions } = options;
  return { ...requestOptions, correlationId };
}

function normalize(error: unknown): HolidayFlowError {
  if (typeof error === 'object' && error !== null && 'message' in error) {
    const candidate = error as Partial<HolidayFlowError>;
    return Object.assign(candidate, { retryable: candidate.retryable ?? false }) as HolidayFlowError;
  }
  return new HolidayFlowContractError('國定假日流程發生未知錯誤。');
}

function errorText(error: HolidayFlowError): string {
  return `${error.publicCode ?? ''} ${error.code ?? ''} ${error.message}`.toLowerCase();
}

function isStale(error: HolidayFlowError): boolean {
  const text = errorText(error);
  return error.status === 409 && (text.includes('stale') || text.includes('version') || text.includes('fingerprint'));
}

function isConflict(error: HolidayFlowError): boolean {
  const text = errorText(error);
  return error.status === 409 || text.includes('conflict') || text.includes('idempotency');
}

function isOutcomeUnknown(error: HolidayFlowError): boolean {
  if (error.status !== undefined && [502, 503, 504].includes(error.status)) return true;
  const text = errorText(error);
  return error.retryable || text.includes('timeout') || text.includes('network') || text.includes('unavailable');
}

function requireDraft(flowKey: string): MutableDraft {
  const draft = holidayFlowStore.get(flowKey);
  if (!draft) throw new HolidayFlowContractError('請先建立國定假日流程狀態。');
  return draft;
}

function requirePreview(draft: MutableDraft): HolidayPreview {
  if (!draft.preview) throw new HolidayFlowContractError('請先取得最新國定假日 Preview。');
  return draft.preview;
}

function assertApplyMatchesPreview(draft: MutableDraft, request: HolidayApplyRequest): void {
  const preview = requirePreview(draft);
  if (request.preview_fingerprint !== preview.preview_fingerprint) {
    throw new HolidayFlowContractError('Apply payload 的 preview fingerprint 已失效。');
  }
  if (request.expected_calendar_version !== preview.calendar_version) {
    throw new HolidayFlowContractError('Apply payload 的 calendar version 必須來自最新 Preview。');
  }
  const { expected_calendar_version: _version, preview_fingerprint: _fingerprint, reason: _reason, ...identity } = request;
  const { expected_calendar_version: _previewVersion, ...previewIdentity } = preview.command;
  if (!sameValue(identity, previewIdentity)) {
    throw new HolidayFlowContractError('Apply payload identity 與 Preview request 不一致。');
  }
}

function queryClient(
  client: HolidayFlowClient,
  query: HolidayQuery,
  options?: HolidayRequestOptions,
): Promise<HolidayCalendar> {
  if (client.query) {
    return client.query(query, options).then((result: HolidayQueryResult) => {
      if (!('planning_horizon' in result)) {
        throw new HolidayFlowContractError('ranged Holiday Query 未回傳 calendar view。');
      }
      return result;
    });
  }
  if (client.queryCalendar) return client.queryCalendar(query, options);
  throw new HolidayFlowContractError('Holiday client 缺少 typed query method。');
}

export class HolidayFlowStore {
  private readonly drafts = new Map<string, MutableDraft>();
  private readonly listeners = new Set<() => void>();

  public subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    for (const listener of this.listeners) listener();
  }

  public get(flowKey = DEFAULT_FLOW_KEY): HolidayFlowDraft | undefined {
    return this.drafts.get(flowKey);
  }

  private getOrCreate(flowKey: string): MutableDraft {
    const existing = this.drafts.get(flowKey);
    if (existing) return existing;
    const draft: MutableDraft = {
      flowKey,
      query: null,
      calendar: null,
      previewRequest: null,
      preview: null,
      applyRequest: null,
      idempotencyKey: newKey('holiday-apply'),
      correlationId: newKey('scheduling-holiday'),
      receipt: null,
      status: 'idle',
      error: null,
      replayed: false,
    };
    this.drafts.set(flowKey, draft);
    return draft;
  }

  public setQueryLoading(flowKey: string): MutableDraft {
    const draft = this.getOrCreate(flowKey);
    draft.status = 'query_loading';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setQueryReady(flowKey: string, calendar: HolidayCalendar, query?: HolidayQuery): MutableDraft {
    const draft = this.getOrCreate(flowKey);
    if (query) draft.query = query;
    draft.calendar = copyCalendar(calendar);
    draft.status = 'query_ready';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setDraft(flowKey: string, request: HolidayPreviewRequest): MutableDraft {
    const draft = this.getOrCreate(flowKey);
    if (draft.status === 'apply_pending' || draft.status === 'outcome_unknown' || draft.status === 'receipt_received' || draft.status === 'requery_loading') return draft;
    draft.previewRequest = copyRequest(request);
    draft.preview = null;
    draft.applyRequest = null;
    draft.receipt = null;
    draft.idempotencyKey = newKey('holiday-apply');
    draft.replayed = false;
    draft.status = draft.calendar ? 'query_ready' : 'idle';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setPreviewLoading(flowKey: string): MutableDraft {
    const draft = this.getOrCreate(flowKey);
    draft.status = 'preview_loading';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setPreviewReady(flowKey: string, preview: HolidayPreview): MutableDraft {
    const draft = this.getOrCreate(flowKey);
    draft.preview = preview;
    draft.status = 'preview_ready';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setApplyPending(flowKey: string, request: HolidayApplyRequest): MutableDraft {
    const draft = this.getOrCreate(flowKey);
    draft.applyRequest = copyApplyRequest(request);
    draft.status = 'apply_pending';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setReceiptReceived(flowKey: string, receipt: HolidayReceipt): MutableDraft {
    const draft = this.getOrCreate(flowKey);
    draft.receipt = receipt;
    draft.status = 'receipt_received';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setRequeryLoading(flowKey: string): MutableDraft {
    const draft = this.getOrCreate(flowKey);
    draft.status = 'requery_loading';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setObserved(flowKey: string, calendar: HolidayCalendar, replayed = false): MutableDraft {
    const draft = this.getOrCreate(flowKey);
    draft.calendar = copyCalendar(calendar);
    draft.replayed = replayed;
    draft.status = 'observed';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setTypedError(flowKey: string, error: HolidayFlowError): MutableDraft {
    const draft = this.getOrCreate(flowKey);
    draft.status = 'typed_error';
    draft.error = error;
    this.notify();
    return draft;
  }

  public setStale(flowKey: string, error: HolidayFlowError): MutableDraft {
    const draft = this.getOrCreate(flowKey);
    draft.preview = null;
    draft.applyRequest = null;
    draft.status = 'stale';
    draft.error = error;
    this.notify();
    return draft;
  }

  public setConflict(flowKey: string, error: HolidayFlowError): MutableDraft {
    const draft = this.getOrCreate(flowKey);
    draft.status = 'conflict';
    draft.error = error;
    this.notify();
    return draft;
  }

  public setOutcomeUnknown(flowKey: string, error: HolidayFlowError): MutableDraft {
    const draft = this.getOrCreate(flowKey);
    draft.status = 'outcome_unknown';
    draft.error = error;
    this.notify();
    return draft;
  }

  public setObservationFailed(flowKey: string, error: HolidayFlowError): MutableDraft {
    const draft = this.getOrCreate(flowKey);
    draft.status = 'observation_failed';
    draft.error = error;
    this.notify();
    return draft;
  }

  public clear(flowKey = DEFAULT_FLOW_KEY): void {
    this.drafts.delete(flowKey);
    this.notify();
  }

  public clearAll(): void {
    this.drafts.clear();
    this.notify();
  }
}

export const holidayFlowStore = new HolidayFlowStore();

export function resolveHolidayMachineState(
  draft: HolidayFlowDraft | undefined,
): HolidayMachineState {
  if (!draft) return { type: 'idle', flowKey: DEFAULT_FLOW_KEY };
  switch (draft.status) {
    case 'idle': return { type: 'idle', flowKey: draft.flowKey };
    case 'query_loading': return { type: 'query_loading', flowKey: draft.flowKey };
    case 'query_ready':
      if (!draft.calendar) throw new HolidayFlowContractError('國定假日 query ready 缺少 calendar。');
      return { type: 'query_ready', flowKey: draft.flowKey, calendar: draft.calendar };
    case 'preview_loading':
      if (!draft.previewRequest) throw new HolidayFlowContractError('國定假日 Preview loading 缺少 request。');
      return { type: 'preview_loading', flowKey: draft.flowKey, request: draft.previewRequest };
    case 'preview_ready':
      if (!draft.previewRequest || !draft.preview) throw new HolidayFlowContractError('國定假日 Preview ready 缺少 request 或 preview。');
      return { type: 'preview_ready', flowKey: draft.flowKey, request: draft.previewRequest, preview: draft.preview };
    case 'apply_pending':
      if (!draft.preview || !draft.applyRequest) throw new HolidayFlowContractError('國定假日 Apply pending 缺少 preview 或 request。');
      return { type: 'apply_pending', flowKey: draft.flowKey, preview: draft.preview, request: draft.applyRequest, idempotencyKey: draft.idempotencyKey };
    case 'receipt_received':
      if (!draft.receipt) throw new HolidayFlowContractError('國定假日 receipt state 缺少 receipt。');
      return { type: 'receipt_received', flowKey: draft.flowKey, receipt: draft.receipt };
    case 'requery_loading':
      if (!draft.receipt) throw new HolidayFlowContractError('國定假日 re-query 缺少 receipt。');
      return { type: 'requery_loading', flowKey: draft.flowKey, receipt: draft.receipt };
    case 'observed':
      if (!draft.calendar || !draft.receipt) throw new HolidayFlowContractError('國定假日 observed 缺少 calendar 或 receipt。');
      return { type: 'observed', flowKey: draft.flowKey, calendar: draft.calendar, receipt: draft.receipt, replayed: draft.replayed };
    case 'typed_error':
      return { type: 'typed_error', flowKey: draft.flowKey, error: draft.error ?? new HolidayFlowContractError('國定假日 typed error 缺少錯誤內容。') };
    case 'stale':
      return { type: 'stale', flowKey: draft.flowKey, error: draft.error ?? new HolidayFlowContractError('國定假日 Preview 已失效。'), requiresFreshQuery: true, requiresFreshPreview: true };
    case 'conflict':
      return { type: 'conflict', flowKey: draft.flowKey, error: draft.error ?? new HolidayFlowContractError('國定假日流程發生衝突。') };
    case 'outcome_unknown':
      if (!draft.preview || !draft.applyRequest) throw new HolidayFlowContractError('國定假日 outcome unknown 缺少 preview 或 request。');
      return { type: 'outcome_unknown', flowKey: draft.flowKey, preview: draft.preview, request: draft.applyRequest, idempotencyKey: draft.idempotencyKey, error: draft.error ?? new HolidayFlowContractError('國定假日 Apply 結果未明。') };
    case 'observation_failed':
      if (!draft.receipt) throw new HolidayFlowContractError('國定假日 observation failure 缺少 receipt。');
      return { type: 'observation_failed', flowKey: draft.flowKey, receipt: draft.receipt, error: draft.error ?? new HolidayFlowContractError('國定假日 receipt 觀察失敗。') };
  }
}

export function setHolidayDraft(
  request: HolidayPreviewRequest,
  flowKey = DEFAULT_FLOW_KEY,
): HolidayFlowDraft {
  return holidayFlowStore.setDraft(flowKey, request);
}

export async function queryHolidayFlow(
  query: HolidayQuery,
  options?: HolidayFlowOptions,
): Promise<HolidayCalendar>;
export async function queryHolidayFlow(
  fromDate: string,
  toDate: string,
  options?: HolidayFlowOptions,
): Promise<HolidayCalendar>;
export async function queryHolidayFlow(
  queryOrFromDate: HolidayQuery | string,
  toDateOrOptions?: string | HolidayFlowOptions,
  maybeOptions?: HolidayFlowOptions,
): Promise<HolidayCalendar> {
  const flowKey = DEFAULT_FLOW_KEY;
  const query: HolidayQuery = typeof queryOrFromDate === 'string'
    ? { fromDate: queryOrFromDate, toDate: toDateOrOptions as string }
    : queryOrFromDate;
  const options = typeof toDateOrOptions === 'object' ? toDateOrOptions : maybeOptions;
  holidayFlowStore.setQueryLoading(flowKey);
  try {
    const calendar = await queryClient(options?.client ?? HOLIDAY_CLIENT, query, options);
    holidayFlowStore.setQueryReady(flowKey, calendar, query);
    return calendar;
  } catch (error) {
    const typed = normalize(error);
    holidayFlowStore.setTypedError(flowKey, typed);
    throw typed;
  }
}

function isFlowOptions(value: HolidayPreviewRequest | HolidayFlowOptions): value is HolidayFlowOptions {
  return 'client' in value || 'timeoutMs' in value || 'baseUrl' in value || 'signal' in value || 'idempotencyKey' in value;
}

export async function previewHolidayFlow(options?: HolidayFlowOptions): Promise<HolidayPreview>;
export async function previewHolidayFlow(
  request: HolidayPreviewRequest,
  options?: HolidayFlowOptions,
): Promise<HolidayPreview>;
export async function previewHolidayFlow(
  requestOrOptions?: HolidayPreviewRequest | HolidayFlowOptions,
  maybeOptions?: HolidayFlowOptions,
): Promise<HolidayPreview> {
  const flowKey = DEFAULT_FLOW_KEY;
  const draft = requireDraft(flowKey);
  const options = requestOrOptions && isFlowOptions(requestOrOptions) ? requestOrOptions : maybeOptions;
  const request = requestOrOptions && !isFlowOptions(requestOrOptions) ? requestOrOptions : undefined;
  const previewRequest = request ?? draft.previewRequest;
  if (!previewRequest) throw new HolidayFlowContractError('請先提供完整國定假日 Preview request。');
  const horizon = requireHorizon(previewRequest);
  if (draft.calendar && (draft.calendar.planning_horizon.from_date !== horizon.from_date || draft.calendar.planning_horizon.to_date !== horizon.to_date)) {
    throw new HolidayFlowContractError('Preview horizon 必須與最新 Query horizon 一致。');
  }
  holidayFlowStore.setDraft(flowKey, previewRequest);
  holidayFlowStore.setPreviewLoading(flowKey);
  try {
    const preview = await (options?.client ?? HOLIDAY_CLIENT).preview(previewRequest, {
      ...requestOptionsOf(options, draft.correlationId),
    });
    holidayFlowStore.setPreviewReady(flowKey, preview);
    return preview;
  } catch (error) {
    const typed = normalize(error);
    if (isStale(typed)) holidayFlowStore.setStale(flowKey, typed);
    else if (isConflict(typed)) holidayFlowStore.setConflict(flowKey, typed);
    else holidayFlowStore.setTypedError(flowKey, typed);
    throw typed;
  }
}

async function requeryAfterReceipt(
  flowKey: string,
  options: HolidayFlowOptions | undefined,
  replayed: boolean,
): Promise<HolidayCalendar> {
  const draft = requireDraft(flowKey);
  if (!draft.receipt) throw new HolidayFlowContractError('收到的國定假日 receipt 不存在。');
  holidayFlowStore.setRequeryLoading(flowKey);
  try {
    const applyRequest = draft.applyRequest ?? draft.previewRequest;
    if (!applyRequest) throw new HolidayFlowContractError('receipt re-query 缺少原始 horizon。');
    const horizon = requireHorizon(applyRequest);
    const query = draft.query ?? { from_date: horizon.from_date, to_date: horizon.to_date };
    const calendar = await queryClient(options?.client ?? HOLIDAY_CLIENT, query, options);
    holidayFlowStore.setObserved(flowKey, calendar, replayed);
    return calendar;
  } catch (error) {
    const typed = normalize(error);
    holidayFlowStore.setObservationFailed(flowKey, typed);
    throw typed;
  }
}

export async function applyHolidayFlow(
  request?: HolidayApplyRequest,
  options?: HolidayFlowOptions,
): Promise<HolidayReceipt> {
  const flowKey = DEFAULT_FLOW_KEY;
  const draft = requireDraft(flowKey);
  const preview = requirePreview(draft);
  const isRetry = draft.status === 'outcome_unknown';
  const applyRequest = request ?? draft.applyRequest;
  if (!applyRequest) throw new HolidayFlowContractError('請先提供完整國定假日 Apply payload。');
  if (isRetry && draft.applyRequest && !sameValue(draft.applyRequest, applyRequest)) {
    throw new HolidayFlowContractError('結果未明時只能以完全相同 payload 重試。');
  }
  try {
    assertApplyMatchesPreview(draft, applyRequest);
  } catch (error) {
    const typed = normalize(error);
    holidayFlowStore.setTypedError(flowKey, typed);
    throw typed;
  }
  holidayFlowStore.setApplyPending(flowKey, applyRequest);
  try {
    const receipt = await (options?.client ?? HOLIDAY_CLIENT).apply(applyRequest, {
      ...requestOptionsOf(options, draft.correlationId),
      idempotencyKey: draft.idempotencyKey,
    } as HolidayApplyOptions);
    if (receipt.holiday_date !== applyRequest.holiday_date || receipt.preview_fingerprint !== preview.preview_fingerprint || receipt.action !== applyRequest.action) {
      throw new HolidayFlowContractError('國定假日 receipt 與 request／Preview identity 不一致。');
    }
    holidayFlowStore.setReceiptReceived(flowKey, receipt);
    await requeryAfterReceipt(flowKey, options, isRetry);
    return receipt;
  } catch (error) {
    const typed = normalize(error);
    const current = holidayFlowStore.get(flowKey);
    if (current?.receipt) {
      holidayFlowStore.setObservationFailed(flowKey, typed);
    } else if (isStale(typed)) {
      holidayFlowStore.setStale(flowKey, typed);
    } else if (isConflict(typed)) {
      holidayFlowStore.setConflict(flowKey, typed);
    } else if (isOutcomeUnknown(typed)) {
      holidayFlowStore.setOutcomeUnknown(flowKey, typed);
    } else {
      holidayFlowStore.setTypedError(flowKey, typed);
    }
    throw typed;
  }
}

export async function retryHolidayApplyFlow(
  options?: HolidayFlowOptions,
): Promise<HolidayReceipt> {
  const draft = requireDraft(DEFAULT_FLOW_KEY);
  if (draft.status !== 'outcome_unknown' || !draft.applyRequest) throw new HolidayFlowContractError('只有結果未明的國定假日 Apply 可以重試。');
  return applyHolidayFlow(draft.applyRequest, options);
}

export async function retryHolidayObservationFlow(
  options?: HolidayFlowOptions,
): Promise<HolidayCalendar> {
  const draft = requireDraft(DEFAULT_FLOW_KEY);
  if (draft.status !== 'observation_failed' || !draft.receipt) throw new HolidayFlowContractError('只有 receipt 觀察失敗可以重試觀察。');
  return requeryAfterReceipt(DEFAULT_FLOW_KEY, options, draft.replayed);
}
