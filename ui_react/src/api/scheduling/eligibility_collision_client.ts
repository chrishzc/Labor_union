/**
 * File: eligibility_collision_client.ts
 * Description: 執行 Scheduling case、staff、as_of 綁定的唯讀資格衝突 GET。
 */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';
import {
  mapSchedulingEligibilityCollisionError,
  SchedulingEligibilityCollisionError,
  SchedulingEligibilityUnauthenticatedError,
  SchedulingEligibilityValidationError,
} from './eligibility_collision_errors';
import {
  SchedulingEligibilityCollisionResponseSchema,
  type SchedulingEligibilityCollisionProjection,
} from './eligibility_collision_schemas';

export interface SchedulingEligibilityCollisionQuery {
  caseNo: string;
  staffId: number;
  asOf: string;
}

export interface SchedulingEligibilityCollisionRequestOptions {
  correlationId?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
  headers?: Record<string, string>;
}

export interface SchedulingEligibilityCollisionClient {
  query(query: SchedulingEligibilityCollisionQuery, options?: SchedulingEligibilityCollisionRequestOptions): Promise<SchedulingEligibilityCollisionProjection>;
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function requireDate(value: string, field: string): string {
  if (!ISO_DATE.test(value)) throw new SchedulingEligibilityValidationError(`${field} 必須是 YYYY-MM-DD。`);
  const [year, month, day] = value.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    throw new SchedulingEligibilityValidationError(`${field} 不是有效日期。`);
  }
  return value;
}

function validateQuery(query: SchedulingEligibilityCollisionQuery): SchedulingEligibilityCollisionQuery {
  if (typeof query.caseNo !== 'string' || query.caseNo.trim().length < 1 || query.caseNo.length > 50) {
    throw new SchedulingEligibilityValidationError('caseNo 必須是 1 至 50 字元的非空字串。');
  }
  if (query.caseNo !== query.caseNo.trim()) throw new SchedulingEligibilityValidationError('caseNo 不得包含前後空白。');
  if (!Number.isInteger(query.staffId) || query.staffId <= 0) throw new SchedulingEligibilityValidationError('staffId 必須是正整數。');
  return { ...query, asOf: requireDate(query.asOf, 'asOf') };
}

function requestOptions(options: SchedulingEligibilityCollisionRequestOptions | undefined): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new SchedulingEligibilityUnauthenticatedError();
  const headers: Record<string, string> = {};
  for (const [name, value] of Object.entries(options?.headers ?? {})) {
    const normalized = name.toLowerCase();
    if (normalized === 'authorization' || normalized === 'x-correlation-id') continue;
    headers[name] = value;
  }
  headers['X-Correlation-ID'] = options?.correlationId?.trim() || `scheduling-eligibility-${Math.random().toString(36).slice(2, 14)}`;
  return { signal: options?.signal, timeoutMs: options?.timeoutMs, baseUrl: options?.baseUrl, headers, token };
}

function decode(raw: unknown, query: SchedulingEligibilityCollisionQuery): SchedulingEligibilityCollisionProjection {
  const parsed = SchedulingEligibilityCollisionResponseSchema.safeParse(raw);
  if (!parsed.success) {
    throw new ApiDecodeError('Scheduling 資格衝突回應結構異常。', parsed.error.issues.map((issue) => ({ path: issue.path.join('.') || '(root)', message: issue.message, code: issue.code })), raw);
  }
  if (!parsed.data.success || parsed.data.data === null) {
    throw new ApiHttpError(422, 'SCHEDULING_ELIGIBILITY_EMPTY', parsed.data.error ?? parsed.data.message, false, raw);
  }
  const projection = parsed.data.data;
  if (projection.case_no !== query.caseNo || projection.as_of !== query.asOf) {
    throw new SchedulingEligibilityValidationError('資格衝突 projection 與 request case/as_of 不一致。');
  }
  if (projection.staff.length !== 1 || projection.staff[0]?.staff_id !== query.staffId) {
    throw new SchedulingEligibilityValidationError('資格衝突 projection 未精確回傳選定 staff。');
  }
  const staff = projection.staff[0];
  if (new Set(staff.qualification_checks.map((item) => item.code)).size !== staff.qualification_checks.length) {
    throw new SchedulingEligibilityValidationError('資格檢查包含重複 code。');
  }
  return projection;
}

export async function querySchedulingEligibilityCollision(query: SchedulingEligibilityCollisionQuery, options?: SchedulingEligibilityCollisionRequestOptions): Promise<SchedulingEligibilityCollisionProjection> {
  const validated = validateQuery(query);
  const endpoint = '/api/v1/scheduling/eligibility-collisions';
  try {
    const raw = await transport.get<unknown>(endpoint, {
      ...requestOptions(options),
      params: { case_no: validated.caseNo, staff_id: validated.staffId, as_of: validated.asOf },
    });
    return decode(raw, validated);
  } catch (error) {
    throw mapSchedulingEligibilityCollisionError(error);
  }
}

class DefaultSchedulingEligibilityCollisionClient implements SchedulingEligibilityCollisionClient {
  public query(query: SchedulingEligibilityCollisionQuery, options?: SchedulingEligibilityCollisionRequestOptions): Promise<SchedulingEligibilityCollisionProjection> {
    return querySchedulingEligibilityCollision(query, options);
  }
}

export function createSchedulingEligibilityCollisionClient(): SchedulingEligibilityCollisionClient {
  return new DefaultSchedulingEligibilityCollisionClient();
}

export const schedulingEligibilityCollisionClient = createSchedulingEligibilityCollisionClient();

export { SchedulingEligibilityCollisionError };
