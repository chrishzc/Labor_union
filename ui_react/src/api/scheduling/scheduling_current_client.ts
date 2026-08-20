/**
 * File: scheduling_current_client.ts
 * Description: 使用最新記憶體 Session 執行 bounded current-calendar GET 並拒絕 projection 漂移。
 */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import {
  SchedulingCurrentResponseSchema,
  type SchedulingCurrentProjection,
} from './scheduling_current_schemas';
import {
  SchedulingUnauthenticatedError,
  SchedulingValidationError,
  mapSchedulingCurrentError,
} from './scheduling_current_errors';

export interface SchedulingCurrentQuery {
  staffId: number;
  rangeStart: string;
  rangeEnd: string;
}

export interface SchedulingCurrentQueryOptions {
  signal?: AbortSignal;
  headers?: Record<string, string>;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface SchedulingCurrentClient {
  queryCurrentCalendar(
    query: SchedulingCurrentQuery,
    options?: SchedulingCurrentQueryOptions
  ): Promise<SchedulingCurrentProjection>;
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const MAXIMUM_RANGE_DAY_COUNT = 62;
let correlationSequence = 0;

function parseIsoDate(value: string, field: string): number {
  if (!ISO_DATE.test(value)) {
    throw new SchedulingValidationError(`${field} 必須是 YYYY-MM-DD。`);
  }
  const [year, month, day] = value.split('-').map(Number);
  const timestamp = Date.UTC(year, month - 1, day);
  const parsed = new Date(timestamp);
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day
  ) {
    throw new SchedulingValidationError(`${field} 不是有效日期。`);
  }
  return timestamp;
}

function validateQuery(query: SchedulingCurrentQuery): void {
  if (!Number.isInteger(query.staffId) || query.staffId <= 0) {
    throw new SchedulingValidationError('staffId 必須是正整數。');
  }
  const start = parseIsoDate(query.rangeStart, 'rangeStart');
  const end = parseIsoDate(query.rangeEnd, 'rangeEnd');
  if (end < start) {
    throw new SchedulingValidationError('rangeEnd 不得早於 rangeStart。');
  }
  const dayCount = Math.floor((end - start) / 86_400_000) + 1;
  if (dayCount > MAXIMUM_RANGE_DAY_COUNT) {
    throw new SchedulingValidationError('日期範圍不得超過 62 天。');
  }
}

function nextCorrelationId(): string {
  correlationSequence += 1;
  return `scheduling-ui-${correlationSequence.toString(36)}`;
}

function requestOptions(options?: SchedulingCurrentQueryOptions): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new SchedulingUnauthenticatedError();

  const headers: Record<string, string> = {};
  let correlationId: string | null = null;
  for (const [name, value] of Object.entries(options?.headers ?? {})) {
    const normalized = name.toLowerCase();
    if (normalized === 'authorization') continue;
    if (normalized === 'x-correlation-id') {
      if (correlationId !== null) {
        throw new SchedulingValidationError('X-Correlation-ID 不得重複。');
      }
      correlationId = value.trim();
      continue;
    }
    headers[name] = value;
  }
  headers['X-Correlation-ID'] = correlationId || nextCorrelationId();

  return {
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
    headers,
    token,
  };
}

function assertUnique(values: readonly (number | string)[], label: string): void {
  if (new Set(values).size !== values.length) {
    throw new SchedulingValidationError(`${label} 包含重複 identity。`);
  }
}

function validateProjection(
  projection: SchedulingCurrentProjection,
  query: SchedulingCurrentQuery
): SchedulingCurrentProjection {
  if (projection.staff_id !== query.staffId) {
    throw new SchedulingValidationError('projection staff_id 與 request 不一致。');
  }
  if (
    projection.range_start !== query.rangeStart ||
    projection.range_end !== query.rangeEnd
  ) {
    throw new SchedulingValidationError('projection range 與 request 不一致。');
  }

  assertUnique(
    projection.assignments.map((assignment) => assignment.assignment_id),
    'assignments'
  );
  assertUnique(
    projection.days.map((day) => day.calendar_date),
    'days'
  );
  assertUnique(
    projection.case_versions.map((item) => item.case_no),
    'case_versions'
  );

  for (const assignment of projection.assignments) {
    if (assignment.staff_id !== query.staffId) {
      throw new SchedulingValidationError('assignment staff_id 與 request 不一致。');
    }
  }
  for (const day of projection.days) {
    if (day.calendar_date < query.rangeStart || day.calendar_date > query.rangeEnd) {
      throw new SchedulingValidationError('calendar_date 超出 request range。');
    }
    if (day.available !== (day.entries.length === 0)) {
      throw new SchedulingValidationError('day available 與 occupancy entries 不一致。');
    }
  }
  return projection;
}

function decodeProjection(
  raw: unknown,
  query: SchedulingCurrentQuery
): SchedulingCurrentProjection {
  const decoded = SchedulingCurrentResponseSchema.safeParse(raw);
  if (!decoded.success) {
    throw new ApiDecodeError(
      '排班日曆回應結構異常。',
      decoded.error.issues.map((issue) => ({
        path: issue.path.join('.') || '(root)',
        message: issue.message,
        code: issue.code,
      })),
      raw
    );
  }
  if (!decoded.data.success) {
    throw new SchedulingValidationError(
      decoded.data.error ?? decoded.data.message
    );
  }
  return validateProjection(decoded.data.data, query);
}

class DefaultSchedulingCurrentClient implements SchedulingCurrentClient {
  public async queryCurrentCalendar(
    query: SchedulingCurrentQuery,
    options?: SchedulingCurrentQueryOptions
  ): Promise<SchedulingCurrentProjection> {
    validateQuery(query);
    try {
      const raw = await transport.get<unknown>(
        `/api/v1/scheduling/staff/${query.staffId}/current-calendar`,
        {
          ...requestOptions(options),
          params: {
            range_start: query.rangeStart,
            range_end: query.rangeEnd,
          },
        }
      );
      return decodeProjection(raw, query);
    } catch (error) {
      throw mapSchedulingCurrentError(error);
    }
  }
}

export function createSchedulingCurrentClient(): SchedulingCurrentClient {
  return new DefaultSchedulingCurrentClient();
}

export const schedulingCurrentClient: SchedulingCurrentClient =
  createSchedulingCurrentClient();
