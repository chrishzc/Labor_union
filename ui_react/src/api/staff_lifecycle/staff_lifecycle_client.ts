/**
 * File: staff_lifecycle_client.ts
 * Description: 以即時記憶體 Session 接線 Staff lifecycle Query、Preview 與 Apply。
 */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';
import {
  mapStaffLifecycleError,
  StaffLifecycleUnauthenticatedError,
  StaffLifecycleValidationError,
} from './staff_lifecycle_errors';
import {
  StaffLifecycleActionSchema,
  StaffLifecycleApplyPayloadSchema,
  StaffLifecyclePreviewResponseSchema,
  StaffLifecycleQueryResponseSchema,
  StaffLifecycleReceiptResponseSchema,
  StaffLifecycleTransitionInputSchema,
  type StaffLifecycleAction,
  type StaffLifecycleApplyPayload,
  type StaffLifecycleApplyReceipt,
  type StaffLifecyclePreview,
  type StaffLifecycleTransitionInput,
  type StaffLifecycleView,
} from './staff_lifecycle_schemas';

export interface StaffLifecycleRequestOptions {
  correlationId?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
  headers?: Record<string, string>;
}

export interface StaffLifecycleApplyOptions extends StaffLifecycleRequestOptions {
  idempotencyKey: string;
}

export interface StaffLifecycleClient {
  query(staffId: number, options?: StaffLifecycleRequestOptions): Promise<StaffLifecycleView>;
  queryLifecycle(staffId: number, options?: StaffLifecycleRequestOptions): Promise<StaffLifecycleView>;
  preview(
    staffId: number,
    action: StaffLifecycleAction,
    payload: StaffLifecycleTransitionInput,
    options?: StaffLifecycleRequestOptions
  ): Promise<StaffLifecyclePreview>;
  previewTransition(
    staffId: number,
    action: StaffLifecycleAction,
    payload: StaffLifecycleTransitionInput,
    options?: StaffLifecycleRequestOptions
  ): Promise<StaffLifecyclePreview>;
  apply(
    staffId: number,
    action: StaffLifecycleAction,
    payload: StaffLifecycleApplyPayload,
    options: StaffLifecycleApplyOptions
  ): Promise<StaffLifecycleApplyReceipt>;
  applyTransition(
    staffId: number,
    action: StaffLifecycleAction,
    payload: StaffLifecycleApplyPayload,
    options: StaffLifecycleApplyOptions
  ): Promise<StaffLifecycleApplyReceipt>;
}

function requireStaffId(staffId: number): void {
  if (!Number.isInteger(staffId) || staffId <= 0) {
    throw new StaffLifecycleValidationError('staffId 必須是正整數。');
  }
}

function requireAction(action: StaffLifecycleAction): StaffLifecycleAction {
  const parsed = StaffLifecycleActionSchema.safeParse(action);
  if (!parsed.success) {
    throw new StaffLifecycleValidationError('Staff lifecycle action 不在核准清單。', parsed.error);
  }
  return parsed.data;
}

function requireHeaderValue(value: string, field: string): string {
  if (typeof value !== 'string' || value.trim().length < 1 || value.length > 191) {
    throw new StaffLifecycleValidationError(`${field} 必須是 1 至 191 字元的非空字串。`);
  }
  return value;
}

function newCorrelationId(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return `staff-lifecycle-${globalThis.crypto.randomUUID()}`;
  }
  return `staff-lifecycle-${Math.random().toString(36).slice(2, 18)}`;
}

function mergeHeaders(
  options: StaffLifecycleRequestOptions | undefined,
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
  options: StaffLifecycleRequestOptions | undefined,
  correlationId: string,
  idempotencyKey?: string
): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new StaffLifecycleUnauthenticatedError();
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

function decodeQuery(raw: unknown, staffId: number): StaffLifecycleView {
  const decoded = StaffLifecycleQueryResponseSchema.safeParse(raw);
  if (!decoded.success) throw decodeIssues(decoded, 'Staff lifecycle 查詢回應結構異常。', raw);
  if (!decoded.data.success) {
    throw new ApiHttpError(400, 'BUSINESS_ERROR', decoded.data.error ?? decoded.data.message, false, raw);
  }
  if (decoded.data.data === null) {
    throw new ApiDecodeError('Staff lifecycle 查詢成功但缺少 data 本體。', [], raw);
  }
  if (decoded.data.data.staff_id !== staffId) {
    throw new StaffLifecycleValidationError('Staff lifecycle query identity 與 request staffId 不一致。');
  }
  return decoded.data.data;
}

function decodePreview(raw: unknown, staffId: number): StaffLifecyclePreview {
  const decoded = StaffLifecyclePreviewResponseSchema.safeParse(raw);
  if (!decoded.success) throw decodeIssues(decoded, 'Staff lifecycle Preview 回應結構異常。', raw);
  if (!decoded.data.success) {
    throw new ApiHttpError(400, 'BUSINESS_ERROR', decoded.data.error ?? decoded.data.message, false, raw);
  }
  if (decoded.data.data === null) {
    throw new ApiDecodeError('Staff lifecycle Preview 成功但缺少 data 本體。', [], raw);
  }
  if (decoded.data.data.staff_id !== staffId) {
    throw new StaffLifecycleValidationError('Staff lifecycle preview identity 與 request staffId 不一致。');
  }
  return decoded.data.data;
}

function decodeReceipt(raw: unknown, staffId: number): StaffLifecycleApplyReceipt {
  const decoded = StaffLifecycleReceiptResponseSchema.safeParse(raw);
  if (!decoded.success) throw decodeIssues(decoded, 'Staff lifecycle Apply 回應結構異常。', raw);
  if (!decoded.data.success) {
    throw new ApiHttpError(400, 'BUSINESS_ERROR', decoded.data.error ?? decoded.data.message, false, raw);
  }
  if (decoded.data.data === null) {
    throw new ApiDecodeError('Staff lifecycle Apply 成功但缺少 data 本體。', [], raw);
  }
  if (decoded.data.data.staff_id !== staffId) {
    throw new StaffLifecycleValidationError('Staff lifecycle receipt identity 與 request staffId 不一致。');
  }
  return decoded.data.data;
}

function validateTransition(payload: StaffLifecycleTransitionInput): StaffLifecycleTransitionInput {
  const parsed = StaffLifecycleTransitionInputSchema.safeParse(payload);
  if (!parsed.success) {
    throw new StaffLifecycleValidationError('Staff lifecycle Preview payload 不符合後端契約。', parsed.error);
  }
  return parsed.data;
}

function validateApplyPayload(payload: StaffLifecycleApplyPayload): StaffLifecycleApplyPayload {
  const parsed = StaffLifecycleApplyPayloadSchema.safeParse(payload);
  if (!parsed.success) {
    throw new StaffLifecycleValidationError('Staff lifecycle Apply payload 不符合後端契約。', parsed.error);
  }
  return parsed.data;
}

function correlation(options: StaffLifecycleRequestOptions | undefined): string {
  return requireHeaderValue(options?.correlationId ?? newCorrelationId(), 'X-Correlation-ID');
}

function idempotency(options: StaffLifecycleApplyOptions): string {
  return requireHeaderValue(options.idempotencyKey, 'Idempotency-Key');
}

export async function queryStaffLifecycle(
  staffId: number,
  options?: StaffLifecycleRequestOptions
): Promise<StaffLifecycleView> {
  requireStaffId(staffId);
  const request = requestOptions(options, correlation(options));
  const endpoint = `/api/v1/staff/${encodeURIComponent(String(staffId))}/lifecycle`;
  try {
    const raw = await transport.get(endpoint, request);
    return decodeQuery(raw, staffId);
  } catch (error) {
    throw mapStaffLifecycleError(error);
  }
}

export async function previewStaffLifecycleTransition(
  staffId: number,
  action: StaffLifecycleAction,
  payload: StaffLifecycleTransitionInput,
  options?: StaffLifecycleRequestOptions
): Promise<StaffLifecyclePreview> {
  requireStaffId(staffId);
  const validatedAction = requireAction(action);
  const validatedPayload = validateTransition(payload);
  const request = requestOptions(options, correlation(options));
  const endpoint = `/api/v1/staff/${encodeURIComponent(String(staffId))}/${validatedAction}/preview`;
  try {
    const raw = await transport.post(endpoint, validatedPayload, request);
    return decodePreview(raw, staffId);
  } catch (error) {
    throw mapStaffLifecycleError(error);
  }
}

export async function applyStaffLifecycleTransition(
  staffId: number,
  action: StaffLifecycleAction,
  payload: StaffLifecycleApplyPayload,
  options: StaffLifecycleApplyOptions
): Promise<StaffLifecycleApplyReceipt> {
  requireStaffId(staffId);
  const validatedAction = requireAction(action);
  const validatedPayload = validateApplyPayload(payload);
  const key = idempotency(options);
  const request = requestOptions(options, correlation(options), key);
  const endpoint = `/api/v1/staff/${encodeURIComponent(String(staffId))}/${validatedAction}/apply`;
  try {
    const raw = await transport.post(endpoint, validatedPayload, request);
    return decodeReceipt(raw, staffId);
  } catch (error) {
    throw mapStaffLifecycleError(error);
  }
}

export class DefaultStaffLifecycleClient implements StaffLifecycleClient {
  private readonly defaultOptions?: StaffLifecycleRequestOptions;

  public constructor(defaultOptions?: StaffLifecycleRequestOptions) {
    this.defaultOptions = defaultOptions;
  }

  private mergeOptions(options?: StaffLifecycleRequestOptions): StaffLifecycleRequestOptions | undefined {
    if (!this.defaultOptions) return options;
    if (!options) return this.defaultOptions;
    return {
      ...this.defaultOptions,
      ...options,
      headers: { ...this.defaultOptions.headers, ...options.headers },
    };
  }

  private mergeApplyOptions(options: StaffLifecycleApplyOptions): StaffLifecycleApplyOptions {
    return {
      ...this.mergeOptions(options),
      ...options,
      headers: { ...this.defaultOptions?.headers, ...options.headers },
    };
  }

  public query(staffId: number, options?: StaffLifecycleRequestOptions): Promise<StaffLifecycleView> {
    return queryStaffLifecycle(staffId, this.mergeOptions(options));
  }

  public queryLifecycle(staffId: number, options?: StaffLifecycleRequestOptions): Promise<StaffLifecycleView> {
    return this.query(staffId, options);
  }

  public preview(staffId: number, action: StaffLifecycleAction, payload: StaffLifecycleTransitionInput, options?: StaffLifecycleRequestOptions): Promise<StaffLifecyclePreview> {
    return previewStaffLifecycleTransition(staffId, action, payload, this.mergeOptions(options));
  }

  public previewTransition(staffId: number, action: StaffLifecycleAction, payload: StaffLifecycleTransitionInput, options?: StaffLifecycleRequestOptions): Promise<StaffLifecyclePreview> {
    return this.preview(staffId, action, payload, options);
  }

  public apply(staffId: number, action: StaffLifecycleAction, payload: StaffLifecycleApplyPayload, options: StaffLifecycleApplyOptions): Promise<StaffLifecycleApplyReceipt> {
    return applyStaffLifecycleTransition(staffId, action, payload, this.mergeApplyOptions(options));
  }

  public applyTransition(staffId: number, action: StaffLifecycleAction, payload: StaffLifecycleApplyPayload, options: StaffLifecycleApplyOptions): Promise<StaffLifecycleApplyReceipt> {
    return this.apply(staffId, action, payload, options);
  }
}

export function createStaffLifecycleClient(defaultOptions?: StaffLifecycleRequestOptions): StaffLifecycleClient {
  return new DefaultStaffLifecycleClient(defaultOptions);
}

export const staffLifecycleClient: StaffLifecycleClient = createStaffLifecycleClient();

export const getStaffLifecycle = queryStaffLifecycle;
export const previewLifecycleTransition = previewStaffLifecycleTransition;
export const applyLifecycleTransition = applyStaffLifecycleTransition;
