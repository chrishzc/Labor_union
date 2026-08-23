/**
 * File: staff_availability_client.ts
 * Description: 以即時記憶體 Session 接線 Availability Query、Preview 與 Apply。
 */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';
import {
  mapStaffAvailabilityError,
  StaffAvailabilityUnauthenticatedError,
  StaffAvailabilityValidationError,
} from './staff_availability_errors';
import {
  StaffAvailabilityApplyPayloadSchema,
  StaffAvailabilityDateSchema,
  StaffAvailabilityIntentSchema,
  StaffAvailabilityPreviewResponseSchema,
  StaffAvailabilityQueryResponseSchema,
  StaffAvailabilityReceiptResponseSchema,
  type StaffAvailabilityApplyPayload,
  type StaffAvailabilityIntent,
  type StaffAvailabilityPreview,
  type StaffAvailabilityReceipt,
  type StaffUnavailabilityBlock,
} from './staff_availability_schemas';

export interface StaffAvailabilityRequestOptions {
  correlationId?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
  headers?: Record<string, string>;
}

export interface StaffAvailabilityApplyOptions extends StaffAvailabilityRequestOptions {
  idempotencyKey: string;
}

export interface StaffAvailabilityClient {
  getBlocks(
    staffId: number,
    rangeStart: string,
    rangeEnd: string,
    options?: StaffAvailabilityRequestOptions
  ): Promise<StaffUnavailabilityBlock[]>;
  queryBlocks(
    staffId: number,
    rangeStart: string,
    rangeEnd: string,
    options?: StaffAvailabilityRequestOptions
  ): Promise<StaffUnavailabilityBlock[]>;
  previewChange(
    staffId: number,
    payload: StaffAvailabilityIntent,
    options?: StaffAvailabilityRequestOptions
  ): Promise<StaffAvailabilityPreview>;
  applyChange(
    staffId: number,
    payload: StaffAvailabilityApplyPayload,
    options: StaffAvailabilityApplyOptions
  ): Promise<StaffAvailabilityReceipt>;
  getAvailabilityBlocks: StaffAvailabilityClient['getBlocks'];
  previewAvailabilityChange: StaffAvailabilityClient['previewChange'];
  applyAvailabilityChange: StaffAvailabilityClient['applyChange'];
}

function requireStaffId(staffId: number): void {
  if (!Number.isInteger(staffId) || staffId <= 0) {
    throw new StaffAvailabilityValidationError('staffId 必須是正整數。');
  }
}

function requireDate(value: string, field: string): string {
  const parsed = StaffAvailabilityDateSchema.safeParse(value);
  if (!parsed.success) {
    throw new StaffAvailabilityValidationError(`${field} 必須是有效的 ISO 日期。`, parsed.error);
  }
  return parsed.data;
}

function requireHeaderValue(value: string, field: string): string {
  if (typeof value !== 'string' || value.trim().length < 1 || value.length > 191) {
    throw new StaffAvailabilityValidationError(`${field} 必須是 1 至 191 字元的非空字串。`);
  }
  return value;
}

function newCorrelationId(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return `staff-availability-${globalThis.crypto.randomUUID()}`;
  }
  return `staff-availability-${Math.random().toString(36).slice(2, 18)}`;
}

function mergeHeaders(
  options: StaffAvailabilityRequestOptions | undefined,
  correlationId: string,
  idempotencyKey?: string
): Record<string, string> {
  const headers: Record<string, string> = {};
  for (const [name, value] of Object.entries(options?.headers ?? {})) {
    const normalized = name.toLowerCase();
    if (normalized === 'authorization' || normalized === 'x-correlation-id' || normalized === 'idempotency-key') {
      continue;
    }
    headers[name] = value;
  }
  headers['X-Correlation-ID'] = correlationId;
  if (idempotencyKey !== undefined) headers['Idempotency-Key'] = idempotencyKey;
  return headers;
}

function requestOptions(
  options: StaffAvailabilityRequestOptions | undefined,
  correlationId: string,
  idempotencyKey?: string
): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new StaffAvailabilityUnauthenticatedError();
  return {
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
    headers: mergeHeaders(options, correlationId, idempotencyKey),
    token,
  };
}

function decodeIssues(result: { error: { issues: readonly { path: (string | number)[]; message: string; code: string }[] } }, message: string, raw: unknown): ApiDecodeError {
  return new ApiDecodeError(
    message,
    result.error.issues.map((issue) => ({
      path: issue.path.join('.') || '(root)',
      message: issue.message,
      code: issue.code,
    })),
    raw
  );
}

function decodeBlocks(raw: unknown, staffId: number): StaffUnavailabilityBlock[] {
  const decoded = StaffAvailabilityQueryResponseSchema.safeParse(raw);
  if (!decoded.success) throw decodeIssues(decoded, 'Availability 查詢回應結構異常。', raw);
  if (!decoded.data.success) {
    throw new ApiHttpError(400, 'BUSINESS_ERROR', decoded.data.error ?? decoded.data.message, false, raw);
  }
  if (decoded.data.data === null) {
    throw new ApiDecodeError('Availability 查詢成功但缺少 data 本體。', [], raw);
  }
  if (decoded.data.data.some((block) => block.staff_id !== staffId)) {
    throw new StaffAvailabilityValidationError('Availability query block identity 與 request staffId 不一致。');
  }
  return decoded.data.data;
}

function decodePreview(raw: unknown, staffId: number): StaffAvailabilityPreview {
  const decoded = StaffAvailabilityPreviewResponseSchema.safeParse(raw);
  if (!decoded.success) throw decodeIssues(decoded, 'Availability Preview 回應結構異常。', raw);
  if (!decoded.data.success) {
    throw new ApiHttpError(400, 'BUSINESS_ERROR', decoded.data.error ?? decoded.data.message, false, raw);
  }
  if (decoded.data.data === null) {
    throw new ApiDecodeError('Availability Preview 成功但缺少 data 本體。', [], raw);
  }
  if (
    decoded.data.data.staff_id !== staffId
    || (decoded.data.data.target_block !== null && decoded.data.data.target_block.staff_id !== staffId)
  ) {
    throw new StaffAvailabilityValidationError('Availability preview identity 與 request staffId 不一致。');
  }
  return decoded.data.data;
}

function decodeReceipt(raw: unknown, staffId: number): StaffAvailabilityReceipt {
  const decoded = StaffAvailabilityReceiptResponseSchema.safeParse(raw);
  if (!decoded.success) throw decodeIssues(decoded, 'Availability Apply 回應結構異常。', raw);
  if (!decoded.data.success) {
    throw new ApiHttpError(400, 'BUSINESS_ERROR', decoded.data.error ?? decoded.data.message, false, raw);
  }
  if (decoded.data.data === null) {
    throw new ApiDecodeError('Availability Apply 成功但缺少 data 本體。', [], raw);
  }
  if (decoded.data.data.staff_id !== staffId || decoded.data.data.block.staff_id !== staffId) {
    throw new StaffAvailabilityValidationError('Availability receipt identity 與 request staffId 不一致。');
  }
  return decoded.data.data;
}

function validateIntent(payload: StaffAvailabilityIntent): StaffAvailabilityIntent {
  const parsed = StaffAvailabilityIntentSchema.safeParse(payload);
  if (!parsed.success) {
    throw new StaffAvailabilityValidationError('Availability intent 不符合後端契約。', parsed.error);
  }
  return parsed.data;
}

function validateApplyPayload(payload: StaffAvailabilityApplyPayload): StaffAvailabilityApplyPayload {
  const parsed = StaffAvailabilityApplyPayloadSchema.safeParse(payload);
  if (!parsed.success) {
    throw new StaffAvailabilityValidationError('Availability Apply payload 不符合後端契約。', parsed.error);
  }
  return parsed.data;
}

function correlation(options: StaffAvailabilityRequestOptions | undefined): string {
  return requireHeaderValue(options?.correlationId ?? newCorrelationId(), 'X-Correlation-ID');
}

function idempotency(options: StaffAvailabilityApplyOptions): string {
  return requireHeaderValue(options.idempotencyKey, 'Idempotency-Key');
}

export async function getAvailabilityBlocks(
  staffId: number,
  rangeStart: string,
  rangeEnd: string,
  options?: StaffAvailabilityRequestOptions
): Promise<StaffUnavailabilityBlock[]> {
  requireStaffId(staffId);
  const start = requireDate(rangeStart, 'range_start');
  const end = requireDate(rangeEnd, 'range_end');
  const request = requestOptions(options, correlation(options));
  const endpoint = `/api/v1/scheduling/staff/${encodeURIComponent(String(staffId))}/availability-blocks`;
  try {
    const raw = await transport.get(endpoint, {
      ...request,
      params: { range_start: start, range_end: end },
    });
    return decodeBlocks(raw, staffId);
  } catch (error) {
    throw mapStaffAvailabilityError(error);
  }
}

export async function previewStaffAvailabilityChange(
  staffId: number,
  payload: StaffAvailabilityIntent,
  options?: StaffAvailabilityRequestOptions
): Promise<StaffAvailabilityPreview> {
  requireStaffId(staffId);
  const validated = validateIntent(payload);
  const request = requestOptions(options, correlation(options));
  const endpoint = `/api/v1/scheduling/staff/${encodeURIComponent(String(staffId))}/availability-blocks/preview`;
  try {
    const raw = await transport.post(endpoint, validated, request);
    return decodePreview(raw, staffId);
  } catch (error) {
    throw mapStaffAvailabilityError(error);
  }
}

export async function applyStaffAvailabilityChange(
  staffId: number,
  payload: StaffAvailabilityApplyPayload,
  options: StaffAvailabilityApplyOptions
): Promise<StaffAvailabilityReceipt> {
  requireStaffId(staffId);
  const validated = validateApplyPayload(payload);
  const key = idempotency(options);
  const request = requestOptions(options, correlation(options), key);
  const endpoint = `/api/v1/scheduling/staff/${encodeURIComponent(String(staffId))}/availability-blocks/apply`;
  try {
    const raw = await transport.post(endpoint, validated, request);
    return decodeReceipt(raw, staffId);
  } catch (error) {
    throw mapStaffAvailabilityError(error);
  }
}

export class DefaultStaffAvailabilityClient implements StaffAvailabilityClient {
  private readonly defaultOptions?: StaffAvailabilityRequestOptions;

  public constructor(defaultOptions?: StaffAvailabilityRequestOptions) {
    this.defaultOptions = defaultOptions;
  }

  private mergeOptions(options?: StaffAvailabilityRequestOptions): StaffAvailabilityRequestOptions | undefined {
    if (!this.defaultOptions) return options;
    if (!options) return this.defaultOptions;
    return {
      ...this.defaultOptions,
      ...options,
      headers: { ...this.defaultOptions.headers, ...options.headers },
    };
  }

  private mergeApplyOptions(options: StaffAvailabilityApplyOptions): StaffAvailabilityApplyOptions {
    return {
      ...this.mergeOptions(options),
      ...options,
      headers: { ...this.defaultOptions?.headers, ...options.headers },
    };
  }

  public getBlocks(staffId: number, rangeStart: string, rangeEnd: string, options?: StaffAvailabilityRequestOptions): Promise<StaffUnavailabilityBlock[]> {
    return getAvailabilityBlocks(staffId, rangeStart, rangeEnd, this.mergeOptions(options));
  }

  public queryBlocks(staffId: number, rangeStart: string, rangeEnd: string, options?: StaffAvailabilityRequestOptions): Promise<StaffUnavailabilityBlock[]> {
    return this.getBlocks(staffId, rangeStart, rangeEnd, options);
  }

  public previewChange(staffId: number, payload: StaffAvailabilityIntent, options?: StaffAvailabilityRequestOptions): Promise<StaffAvailabilityPreview> {
    return previewStaffAvailabilityChange(staffId, payload, this.mergeOptions(options));
  }

  public applyChange(staffId: number, payload: StaffAvailabilityApplyPayload, options: StaffAvailabilityApplyOptions): Promise<StaffAvailabilityReceipt> {
    return applyStaffAvailabilityChange(staffId, payload, this.mergeApplyOptions(options));
  }

  public getAvailabilityBlocks = this.getBlocks.bind(this);
  public previewAvailabilityChange = this.previewChange.bind(this);
  public applyAvailabilityChange = this.applyChange.bind(this);
}

export function createStaffAvailabilityClient(defaultOptions?: StaffAvailabilityRequestOptions): StaffAvailabilityClient {
  return new DefaultStaffAvailabilityClient(defaultOptions);
}

export const staffAvailabilityClient: StaffAvailabilityClient = createStaffAvailabilityClient();

export const queryStaffAvailabilityBlocks = getAvailabilityBlocks;
export const previewAvailabilityChange = previewStaffAvailabilityChange;
export const applyAvailabilityChange = applyStaffAvailabilityChange;
