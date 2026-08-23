/**
 * File: qualification_master_client.ts
 * Description: 執行選定 Staff 的 qualification master 唯讀 GET 並驗證六區段。
 */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';
import {
  mapStaffQualificationMasterError,
  StaffQualificationMasterError,
  StaffQualificationUnauthenticatedError,
  StaffQualificationValidationError,
} from './qualification_master_errors';
import {
  StaffQualificationDateSchema,
  StaffQualificationMasterResponseSchema,
  type StaffQualificationMaster,
} from './qualification_master_schemas';

export interface StaffQualificationMasterRequestOptions {
  correlationId?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
  headers?: Record<string, string>;
}

export interface StaffQualificationMasterClient {
  query(staffId: number, asOf: string, options?: StaffQualificationMasterRequestOptions): Promise<StaffQualificationMaster>;
}

function requireStaffId(staffId: number): void {
  if (!Number.isInteger(staffId) || staffId <= 0) throw new StaffQualificationValidationError('staffId 必須是正整數。');
}

function requireDate(asOf: string): string {
  const parsed = StaffQualificationDateSchema.safeParse(asOf);
  if (!parsed.success) throw new StaffQualificationValidationError('asOf 必須是 YYYY-MM-DD。');
  const [year, month, day] = asOf.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) throw new StaffQualificationValidationError('asOf 不是有效日期。');
  return parsed.data;
}

function requestOptions(options: StaffQualificationMasterRequestOptions | undefined): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new StaffQualificationUnauthenticatedError();
  const headers: Record<string, string> = {};
  for (const [name, value] of Object.entries(options?.headers ?? {})) {
    const normalized = name.toLowerCase();
    if (normalized === 'authorization' || normalized === 'x-correlation-id') continue;
    headers[name] = value;
  }
  headers['X-Correlation-ID'] = options?.correlationId?.trim() || `staff-qualification-${Math.random().toString(36).slice(2, 14)}`;
  return { signal: options?.signal, timeoutMs: options?.timeoutMs, baseUrl: options?.baseUrl, headers, token };
}

function decode(raw: unknown, staffId: number, asOf: string): StaffQualificationMaster {
  const parsed = StaffQualificationMasterResponseSchema.safeParse(raw);
  if (!parsed.success) {
    throw new ApiDecodeError('Staff qualification master 回應結構異常。', parsed.error.issues.map((issue) => ({ path: issue.path.join('.') || '(root)', message: issue.message, code: issue.code })), raw);
  }
  if (!parsed.data.success || parsed.data.data === null) throw new ApiHttpError(422, 'STAFF_QUALIFICATION_EMPTY', parsed.data.error ?? parsed.data.message, false, raw);
  const master = parsed.data.data;
  if (master.staff_id !== staffId || master.as_of !== asOf) throw new StaffQualificationValidationError('qualification master 與 request staff/as_of 不一致。');
  const expected = ['skills', 'cooking', 'certifications', 'medical', 'validity', 'unavailability'] as const;
  const actual = master.sections.map((section) => section.kind);
  if (actual.length !== expected.length || actual.some((kind, index) => kind !== expected[index])) throw new StaffQualificationValidationError('qualification master 六區段順序或集合不完整。');
  for (const section of master.sections) {
    if (new Set(section.items.map((item) => item.code)).size !== section.items.length) throw new StaffQualificationValidationError(`qualification section ${section.kind} 包含重複 code。`);
  }
  return master;
}

export async function queryStaffQualificationMaster(staffId: number, asOf: string, options?: StaffQualificationMasterRequestOptions): Promise<StaffQualificationMaster> {
  requireStaffId(staffId);
  const validatedAsOf = requireDate(asOf);
  const endpoint = `/api/v1/staff/${encodeURIComponent(String(staffId))}/qualification-master`;
  try {
    const raw = await transport.get<unknown>(endpoint, { ...requestOptions(options), params: { as_of: validatedAsOf } });
    return decode(raw, staffId, validatedAsOf);
  } catch (error) {
    throw mapStaffQualificationMasterError(error);
  }
}

class DefaultStaffQualificationMasterClient implements StaffQualificationMasterClient {
  public query(staffId: number, asOf: string, options?: StaffQualificationMasterRequestOptions): Promise<StaffQualificationMaster> {
    return queryStaffQualificationMaster(staffId, asOf, options);
  }
}

export function createStaffQualificationMasterClient(): StaffQualificationMasterClient {
  return new DefaultStaffQualificationMasterClient();
}

export const staffQualificationMasterClient = createStaffQualificationMasterClient();

export { StaffQualificationMasterError };
