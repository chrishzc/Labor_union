/**
 * File: staff_preferences_client.ts
 * Description: 以最新記憶體 Session 接線 Staff 偏好 query、preview、apply 與 receipt。
 */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import {
  StaffPreferenceDefinitionsResponseSchema,
  StaffPreferenceProfileApplyPayloadSchema,
  StaffPreferenceProfileApplyReceiptResponseSchema,
  StaffPreferenceProfilePreviewResponseSchema,
  StaffPreferenceProfileResponseSchema,
  StaffPreferenceProfileInputSchema,
  type StaffPreferenceDefinition,
  type StaffPreferenceProfile,
  type StaffPreferenceProfileApplyPayload,
  type StaffPreferenceProfileApplyReceipt,
  type StaffPreferenceProfileInput,
  type StaffPreferenceProfilePreview,
} from './staff_preferences_schemas';
import {
  StaffPreferencesAbortedError,
  StaffPreferencesError,
  StaffPreferencesUnauthenticatedError,
  StaffPreferencesValidationError,
  mapStaffPreferencesError,
} from './staff_preferences_errors';

const PREFERENCES_BASE_PATH = '/api/v1/scheduling/staff-matching-preferences';
let correlationSequence = 0;

export interface StaffPreferencesRequestOptions {
  correlationId?: string;
  signal?: AbortSignal;
  headers?: Record<string, string>;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface StaffPreferencesDefinitionsOptions extends StaffPreferencesRequestOptions {
  includeInactive?: boolean;
}

export interface StaffPreferencesApplyOptions extends StaffPreferencesRequestOptions {
  idempotencyKey: string;
}

export interface StaffPreferencesClient {
  queryDefinitions(options?: StaffPreferencesDefinitionsOptions): Promise<StaffPreferenceDefinition[]>;
  queryProfile(staffId: number, options?: StaffPreferencesRequestOptions): Promise<StaffPreferenceProfile>;
  previewProfile(
    staffId: number,
    payload: StaffPreferenceProfileInput,
    options?: StaffPreferencesRequestOptions,
  ): Promise<StaffPreferenceProfilePreview>;
  applyProfile(
    staffId: number,
    payload: StaffPreferenceProfileApplyPayload,
    options: StaffPreferencesApplyOptions,
  ): Promise<StaffPreferenceProfileApplyReceipt>;
  getDefinitions(options?: StaffPreferencesDefinitionsOptions): Promise<StaffPreferenceDefinition[]>;
  getProfile(staffId: number, options?: StaffPreferencesRequestOptions): Promise<StaffPreferenceProfile>;
}

function nextCorrelationId(): string {
  correlationSequence += 1;
  return `staff-preferences-ui-${correlationSequence.toString(36)}`;
}

function requireStaffId(staffId: number): void {
  if (!Number.isInteger(staffId) || staffId <= 0) {
    throw new StaffPreferencesValidationError('staffId 必須是正整數。');
  }
}

function requireText(value: string, field: string, maximum: number): string {
  const trimmed = value.trim();
  if (trimmed.length < 1 || trimmed.length > maximum) {
    throw new StaffPreferencesValidationError(`${field} 必須是 1 至 ${maximum} 字元。`);
  }
  return trimmed;
}

function requestOptions(
  options: StaffPreferencesRequestOptions | undefined,
  idempotencyKey?: string,
): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new StaffPreferencesUnauthenticatedError();

  const headers: Record<string, string> = {};
  let headerCorrelationId: string | undefined;
  for (const [name, value] of Object.entries(options?.headers ?? {})) {
    const normalized = name.toLowerCase();
    if (normalized === 'authorization' || normalized === 'idempotency-key') continue;
    if (normalized === 'x-correlation-id') {
      if (headerCorrelationId !== undefined) {
        throw new StaffPreferencesValidationError('X-Correlation-ID 不得重複。');
      }
      headerCorrelationId = value;
      continue;
    }
    headers[name] = value;
  }

  const correlationId = requireText(
    options?.correlationId ?? headerCorrelationId ?? nextCorrelationId(),
    'X-Correlation-ID',
    191,
  );
  headers['X-Correlation-ID'] = correlationId;

  if (idempotencyKey !== undefined) {
    headers['Idempotency-Key'] = requireText(idempotencyKey, 'Idempotency-Key', 191);
  }

  return {
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
    headers,
    token,
  };
}

function decodeDefinitions(raw: unknown): StaffPreferenceDefinition[] {
  const decoded = StaffPreferenceDefinitionsResponseSchema.safeParse(raw);
  if (!decoded.success) {
    throw new ApiDecodeError(
      '月嫂偏好 definitions 回應結構異常。',
      decoded.error.issues.map((issue) => ({
        path: issue.path.join('.') || '(root)',
        message: issue.message,
        code: issue.code,
      })),
      raw,
    );
  }
  if (!decoded.data.success) {
    throw new StaffPreferencesValidationError(decoded.data.error ?? decoded.data.message);
  }
  return decoded.data.data;
}

function decodeProfile(raw: unknown, staffId: number): StaffPreferenceProfile {
  const decoded = StaffPreferenceProfileResponseSchema.safeParse(raw);
  if (!decoded.success) {
    throw new ApiDecodeError(
      '月嫂偏好 profile 回應結構異常。',
      decoded.error.issues.map((issue) => ({
        path: issue.path.join('.') || '(root)',
        message: issue.message,
        code: issue.code,
      })),
      raw,
    );
  }
  if (!decoded.data.success) {
    throw new StaffPreferencesValidationError(decoded.data.error ?? decoded.data.message);
  }
  if (decoded.data.data.staff_id !== staffId) {
    throw new StaffPreferencesValidationError('月嫂偏好 profile identity 與 request staffId 不一致。');
  }
  return decoded.data.data;
}

function decodePreview(raw: unknown, staffId: number): StaffPreferenceProfilePreview {
  const decoded = StaffPreferenceProfilePreviewResponseSchema.safeParse(raw);
  if (!decoded.success) {
    throw new ApiDecodeError(
      '月嫂偏好 preview 回應結構異常。',
      decoded.error.issues.map((issue) => ({
        path: issue.path.join('.') || '(root)',
        message: issue.message,
        code: issue.code,
      })),
      raw,
    );
  }
  if (!decoded.data.success) {
    throw new StaffPreferencesValidationError(decoded.data.error ?? decoded.data.message);
  }
  if (decoded.data.data.staff_id !== staffId) {
    throw new StaffPreferencesValidationError('月嫂偏好 preview identity 與 request staffId 不一致。');
  }
  return decoded.data.data;
}

function decodeReceipt(raw: unknown, staffId: number): StaffPreferenceProfileApplyReceipt {
  const decoded = StaffPreferenceProfileApplyReceiptResponseSchema.safeParse(raw);
  if (!decoded.success) {
    throw new ApiDecodeError(
      '月嫂偏好 apply receipt 回應結構異常。',
      decoded.error.issues.map((issue) => ({
        path: issue.path.join('.') || '(root)',
        message: issue.message,
        code: issue.code,
      })),
      raw,
    );
  }
  if (!decoded.data.success) {
    throw new StaffPreferencesValidationError(decoded.data.error ?? decoded.data.message);
  }
  if (decoded.data.data.staff_id !== staffId) {
    throw new StaffPreferencesValidationError('月嫂偏好 receipt identity 與 request staffId 不一致。');
  }
  return decoded.data.data;
}

function validateProfileInput(payload: StaffPreferenceProfileInput): StaffPreferenceProfileInput {
  const parsed = StaffPreferenceProfileInputSchema.safeParse(payload);
  if (!parsed.success) {
    throw new StaffPreferencesValidationError(
      '月嫂偏好 profile snapshot 不符合 strict contract。',
      { originalError: parsed.error },
    );
  }
  const keys = parsed.data.values.map((item) => item.preference_key);
  if (new Set(keys).size !== keys.length) {
    throw new StaffPreferencesValidationError('月嫂偏好 profile snapshot 不得包含重複 preference_key。');
  }
  return parsed.data;
}

export async function queryDefinitions(
  options?: StaffPreferencesDefinitionsOptions,
): Promise<StaffPreferenceDefinition[]> {
  try {
    const raw = await transport.get<unknown>(
      `${PREFERENCES_BASE_PATH}/definitions`,
      {
        ...requestOptions(options),
        params: options?.includeInactive === undefined
          ? undefined
          : { include_inactive: options.includeInactive },
      },
    );
    return decodeDefinitions(raw);
  } catch (error) {
    throw mapStaffPreferencesError(error);
  }
}

export async function queryProfile(
  staffId: number,
  options?: StaffPreferencesRequestOptions,
): Promise<StaffPreferenceProfile> {
  requireStaffId(staffId);
  try {
    const raw = await transport.get<unknown>(
      `${PREFERENCES_BASE_PATH}/staff/${staffId}`,
      requestOptions(options),
    );
    return decodeProfile(raw, staffId);
  } catch (error) {
    throw mapStaffPreferencesError(error);
  }
}

export async function previewProfile(
  staffId: number,
  payload: StaffPreferenceProfileInput,
  options?: StaffPreferencesRequestOptions,
): Promise<StaffPreferenceProfilePreview> {
  requireStaffId(staffId);
  const validatedPayload = validateProfileInput(payload);
  try {
    const raw = await transport.post<unknown>(
      `${PREFERENCES_BASE_PATH}/staff/${staffId}/preview`,
      validatedPayload,
      requestOptions(options),
    );
    return decodePreview(raw, staffId);
  } catch (error) {
    throw mapStaffPreferencesError(error);
  }
}

export async function applyProfile(
  staffId: number,
  payload: StaffPreferenceProfileApplyPayload,
  options: StaffPreferencesApplyOptions,
): Promise<StaffPreferenceProfileApplyReceipt> {
  requireStaffId(staffId);
  const validatedPayload = StaffPreferenceProfileApplyPayloadSchema.safeParse(payload);
  if (!validatedPayload.success) {
    throw new StaffPreferencesValidationError(
      '月嫂偏好 apply payload 不符合 strict contract。',
      { originalError: validatedPayload.error },
    );
  }
  const snapshot = validateProfileInput({ values: validatedPayload.data.values });
  const body: StaffPreferenceProfileApplyPayload = {
    ...validatedPayload.data,
    values: snapshot.values,
  };
  try {
    const raw = await transport.post<unknown>(
      `${PREFERENCES_BASE_PATH}/staff/${staffId}/apply`,
      body,
      requestOptions(options, options.idempotencyKey),
    );
    return decodeReceipt(raw, staffId);
  } catch (error) {
    throw mapStaffPreferencesError(error);
  }
}

export const getDefinitions = queryDefinitions;
export const getProfile = queryProfile;

export class DefaultStaffPreferencesClient implements StaffPreferencesClient {
  public queryDefinitions(options?: StaffPreferencesDefinitionsOptions) {
    return queryDefinitions(options);
  }

  public queryProfile(staffId: number, options?: StaffPreferencesRequestOptions) {
    return queryProfile(staffId, options);
  }

  public previewProfile(
    staffId: number,
    payload: StaffPreferenceProfileInput,
    options?: StaffPreferencesRequestOptions,
  ) {
    return previewProfile(staffId, payload, options);
  }

  public applyProfile(
    staffId: number,
    payload: StaffPreferenceProfileApplyPayload,
    options: StaffPreferencesApplyOptions,
  ) {
    return applyProfile(staffId, payload, options);
  }

  public getDefinitions(options?: StaffPreferencesDefinitionsOptions) {
    return this.queryDefinitions(options);
  }

  public getProfile(staffId: number, options?: StaffPreferencesRequestOptions) {
    return this.queryProfile(staffId, options);
  }
}

export function createStaffPreferencesClient(): StaffPreferencesClient {
  return new DefaultStaffPreferencesClient();
}

export const staffPreferencesClient = createStaffPreferencesClient();

export { StaffPreferencesAbortedError, StaffPreferencesError };
