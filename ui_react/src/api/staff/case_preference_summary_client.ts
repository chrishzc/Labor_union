/**
 * File: case_preference_summary_client.ts
 * Description: 查詢 Staff roster case-preference summary，root 嚴格、母題可局部降級。
 */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';
import {
  mapStaffCasePreferenceSummaryError,
  StaffCasePreferenceSummaryError,
  StaffCasePreferenceUnauthenticatedError,
  StaffCasePreferenceValidationError,
} from './case_preference_summary_errors';
import {
  STAFF_CASE_PREFERENCE_TOPIC_KEYS,
  StaffCasePreferenceSummaryLooseDataSchema,
  StaffCasePreferenceSummaryLooseResponseSchema,
  StaffCasePreferenceSummaryResponseSchema,
  StaffCasePreferenceTopicSummarySchema,
  type StaffCasePreferenceSummaryRead,
  type StaffCasePreferenceTopicKey,
  type StaffCasePreferenceTopicRead,
} from './case_preference_summary_schemas';

export interface StaffCasePreferenceSummaryRequestOptions {
  correlationId?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
  headers?: Record<string, string>;
}

export interface StaffCasePreferenceSummaryClient {
  query(staffId: number, options?: StaffCasePreferenceSummaryRequestOptions): Promise<StaffCasePreferenceSummaryRead>;
}

function requireStaffId(staffId: number): void {
  if (!Number.isInteger(staffId) || staffId <= 0) {
    throw new StaffCasePreferenceValidationError('staffId 必須是正整數。');
  }
}

function requestOptions(options: StaffCasePreferenceSummaryRequestOptions | undefined): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new StaffCasePreferenceUnauthenticatedError();
  const headers: Record<string, string> = {};
  for (const [name, value] of Object.entries(options?.headers ?? {})) {
    const normalized = name.toLowerCase();
    if (normalized === 'authorization' || normalized === 'x-correlation-id') continue;
    headers[name] = value;
  }
  headers['X-Correlation-ID'] = options?.correlationId?.trim() || `staff-case-preference-${Math.random().toString(36).slice(2, 14)}`;
  return { signal: options?.signal, timeoutMs: options?.timeoutMs, baseUrl: options?.baseUrl, headers, token };
}

function availableTopic(data: unknown): StaffCasePreferenceTopicRead {
  const parsed = StaffCasePreferenceTopicSummarySchema.safeParse(data);
  return parsed.success
    ? { availability: 'available', data: parsed.data }
    : { availability: 'unavailable', reason: 'invalid_topic' };
}

function decode(raw: unknown, staffId: number): StaffCasePreferenceSummaryRead {
  const strict = StaffCasePreferenceSummaryResponseSchema.safeParse(raw);
  if (strict.success) {
    if (!strict.data.success || strict.data.data === null) {
      throw new ApiHttpError(422, 'STAFF_CASE_PREFERENCE_EMPTY', strict.data.error ?? strict.data.message, false, raw);
    }
    if (strict.data.data.staff_id !== staffId) {
      throw new StaffCasePreferenceValidationError('case-preference summary 與 request staff 不一致。');
    }
    const data = strict.data.data;
    return {
      staff_id: data.staff_id,
      service_regions: { availability: 'available', data: data.service_regions },
      service_periods: { availability: 'available', data: data.service_periods },
      rest_schedule: { availability: 'available', data: data.rest_schedule },
      baby_counts: { availability: 'available', data: data.baby_counts },
      holiday_availability: { availability: 'available', data: data.holiday_availability },
      transportation: { availability: 'available', data: data.transportation },
    };
  }

  const envelope = StaffCasePreferenceSummaryLooseResponseSchema.safeParse(raw);
  if (!envelope.success) {
    throw new ApiDecodeError(
      'Staff case-preference summary 回應結構異常。',
      envelope.error.issues.map((issue) => ({ path: issue.path.join('.') || '(root)', message: issue.message, code: issue.code })),
      raw,
    );
  }
  if (!envelope.data.success || envelope.data.data === null) {
    throw new ApiHttpError(422, 'STAFF_CASE_PREFERENCE_EMPTY', envelope.data.error ?? envelope.data.message, false, raw);
  }
  const root = StaffCasePreferenceSummaryLooseDataSchema.safeParse(envelope.data.data);
  if (!root.success) {
    throw new ApiDecodeError(
      'Staff case-preference summary root 結構異常。',
      root.error.issues.map((issue) => ({ path: issue.path.join('.') || '(root)', message: issue.message, code: issue.code })),
      raw,
    );
  }
  if (root.data.staff_id !== staffId) {
    throw new StaffCasePreferenceValidationError('case-preference summary 與 request staff 不一致。');
  }

  const topics = Object.fromEntries(
    STAFF_CASE_PREFERENCE_TOPIC_KEYS.map((key) => [key, availableTopic(root.data[key])]),
  ) as Record<StaffCasePreferenceTopicKey, StaffCasePreferenceTopicRead>;

  return {
    staff_id: root.data.staff_id,
    service_regions: topics.service_regions,
    service_periods: topics.service_periods,
    rest_schedule: topics.rest_schedule,
    baby_counts: topics.baby_counts,
    holiday_availability: topics.holiday_availability,
    transportation: topics.transportation,
  };
}

export async function queryStaffCasePreferenceSummary(staffId: number, options?: StaffCasePreferenceSummaryRequestOptions): Promise<StaffCasePreferenceSummaryRead> {
  requireStaffId(staffId);
  const endpoint = `/api/v1/staff/${encodeURIComponent(String(staffId))}/case-preference-summary`;
  try {
    const raw = await transport.get<unknown>(endpoint, requestOptions(options));
    return decode(raw, staffId);
  } catch (error) {
    throw mapStaffCasePreferenceSummaryError(error);
  }
}

class DefaultStaffCasePreferenceSummaryClient implements StaffCasePreferenceSummaryClient {
  public query(staffId: number, options?: StaffCasePreferenceSummaryRequestOptions): Promise<StaffCasePreferenceSummaryRead> {
    return queryStaffCasePreferenceSummary(staffId, options);
  }
}

export function createStaffCasePreferenceSummaryClient(): StaffCasePreferenceSummaryClient {
  return new DefaultStaffCasePreferenceSummaryClient();
}

export const staffCasePreferenceSummaryClient = createStaffCasePreferenceSummaryClient();

export { StaffCasePreferenceSummaryError };
