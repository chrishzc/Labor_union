/**
 * File: scheduling_current_client.test.ts
 * Description: 驗證 current-calendar client 的 fresh Session、strict decode、range 與 abort 邊界。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { createSchedulingCurrentClient } from '../api/scheduling/scheduling_current_client';
import {
  SchedulingAbortedError,
  SchedulingUnauthenticatedError,
  SchedulingValidationError,
} from '../api/scheduling/scheduling_current_errors';
import {
  SCHEDULING_RESPONSE_DUPLICATE_DAY,
  SCHEDULING_RESPONSE_EXTRA_FIELD,
  SCHEDULING_RESPONSE_READY,
} from './fixtures/scheduling/scheduling_current_contract_fixtures';

function response(body: object) {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
  };
}

describe('scheduling current client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    sessionClient.setSession('scheduling-token-1', {
      id: 7,
      username: 'scheduling-reader',
      display_name: 'Scheduling Reader',
      role: 'admin',
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    sessionClient.clearSession();
  });

  it('sends one bounded GET with the latest memory token and correlation', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response(SCHEDULING_RESPONSE_READY));
    const client = createSchedulingCurrentClient();

    const result = await client.queryCurrentCalendar(
      { staffId: 11, rangeStart: '2026-08-01', rangeEnd: '2026-08-03' },
      { headers: { 'X-Correlation-ID': 'scheduling-test' } }
    );

    expect(result.projection_token).toBe('a'.repeat(64));
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(url).toBe(
      '/api/v1/scheduling/staff/11/current-calendar?range_start=2026-08-01&range_end=2026-08-03'
    );
    expect(options?.method).toBe('GET');
    expect(options?.headers).toMatchObject({
      Authorization: 'Bearer scheduling-token-1',
      'X-Correlation-ID': 'scheduling-test',
    });
  });

  it('fails before fetch without Session or with invalid range', async () => {
    globalThis.fetch = vi.fn();
    sessionClient.clearSession();
    const client = createSchedulingCurrentClient();
    await expect(
      client.queryCurrentCalendar({
        staffId: 11,
        rangeStart: '2026-08-01',
        rangeEnd: '2026-08-03',
      })
    ).rejects.toBeInstanceOf(SchedulingUnauthenticatedError);
    sessionClient.setSession('token', {
      id: 1,
      username: 'reader',
      display_name: 'Reader',
      role: 'admin',
    });
    await expect(
      client.queryCurrentCalendar({
        staffId: 11,
        rangeStart: '2026-08-03',
        rangeEnd: '2026-08-01',
      })
    ).rejects.toBeInstanceOf(SchedulingValidationError);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('rejects extra fields, duplicate, incomplete or out-of-order days and pre-aborted requests', async () => {
    const incompleteDays = {
      ...SCHEDULING_RESPONSE_READY,
      data: {
        ...SCHEDULING_RESPONSE_READY.data,
        days: SCHEDULING_RESPONSE_READY.data.days.slice(0, 2),
      },
    };
    const outOfOrderDays = {
      ...SCHEDULING_RESPONSE_READY,
      data: {
        ...SCHEDULING_RESPONSE_READY.data,
        days: [
          SCHEDULING_RESPONSE_READY.data.days[1],
          SCHEDULING_RESPONSE_READY.data.days[0],
          SCHEDULING_RESPONSE_READY.data.days[2],
        ],
      },
    };
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(response(SCHEDULING_RESPONSE_EXTRA_FIELD))
      .mockResolvedValueOnce(response(SCHEDULING_RESPONSE_DUPLICATE_DAY))
      .mockResolvedValueOnce(response(incompleteDays))
      .mockResolvedValueOnce(response(outOfOrderDays));
    const client = createSchedulingCurrentClient();
    const query = {
      staffId: 11,
      rangeStart: '2026-08-01',
      rangeEnd: '2026-08-03',
    };
    await expect(client.queryCurrentCalendar(query)).rejects.toBeInstanceOf(
      SchedulingValidationError
    );
    await expect(client.queryCurrentCalendar(query)).rejects.toBeInstanceOf(
      SchedulingValidationError
    );
    await expect(client.queryCurrentCalendar(query)).rejects.toBeInstanceOf(
      SchedulingValidationError
    );
    await expect(client.queryCurrentCalendar(query)).rejects.toBeInstanceOf(
      SchedulingValidationError
    );
    const controller = new AbortController();
    controller.abort();
    await expect(
      client.queryCurrentCalendar(query, { signal: controller.signal })
    ).rejects.toBeInstanceOf(SchedulingAbortedError);
    expect(globalThis.fetch).toHaveBeenCalledTimes(4);
  });

  it('rejects an unavailability entry that omits its typed reason', async () => {
    const missingReason = {
      ...SCHEDULING_RESPONSE_READY,
      data: {
        ...SCHEDULING_RESPONSE_READY.data,
        assignments: [],
        days: SCHEDULING_RESPONSE_READY.data.days.map((day, index) => index === 0 ? {
          ...day,
          entries: [{
            occupancy_kind: 'staff_unavailability',
            case_no: null,
            assignment_id: null,
            assignment_status: null,
            lock_id: null,
            segment_id: null,
            availability_block_id: 91,
            unavailability_kind: 'long_leave',
            unavailability_reason: null,
          }],
        } : day),
      },
    };
    globalThis.fetch = vi.fn().mockResolvedValue(response(missingReason));
    const client = createSchedulingCurrentClient();

    await expect(client.queryCurrentCalendar({
      staffId: 11,
      rangeStart: '2026-08-01',
      rangeEnd: '2026-08-03',
    })).rejects.toBeInstanceOf(SchedulingValidationError);
  });
});
