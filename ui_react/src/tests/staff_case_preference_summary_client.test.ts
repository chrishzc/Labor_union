import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { createStaffCasePreferenceSummaryClient } from '../api/staff/case_preference_summary_client';
import { StaffCasePreferenceValidationError } from '../api/staff/case_preference_summary_errors';
import { STAFF_CASE_PREFERENCE_RESPONSE } from './fixtures/staff/staff_case_preference_contract_fixtures';

function response(body: object, ok = true, status = 200) {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
  };
}

describe('Staff case-preference summary client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    sessionClient.setSession('staff-token-1', {
      id: 7,
      username: 'staff-reader',
      display_name: 'Staff Reader',
      role: 'admin',
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    sessionClient.clearSession();
  });

  it('uses one authenticated GET and keeps the bounded route', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response(STAFF_CASE_PREFERENCE_RESPONSE));
    const result = await createStaffCasePreferenceSummaryClient().query(11);

    expect(result.transportation).toMatchObject({
      availability: 'available',
      data: { other_detail: null, other_detail_status: 'source_not_ready' },
    });
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(url).toBe('/api/v1/staff/11/case-preference-summary');
    expect(options?.method).toBe('GET');
    expect(options?.headers).toMatchObject({ Authorization: 'Bearer staff-token-1' });
  });

  it('degrades only one malformed topic after a strict full-contract failure', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({
      ...STAFF_CASE_PREFERENCE_RESPONSE,
      data: {
        ...STAFF_CASE_PREFERENCE_RESPONSE.data,
        transportation: {
          ...STAFF_CASE_PREFERENCE_RESPONSE.data.transportation,
          forbidden_extra_field: true,
        },
      },
    }));

    const result = await createStaffCasePreferenceSummaryClient().query(11);
    expect(result.transportation).toEqual({ availability: 'unavailable', reason: 'invalid_topic' });
    expect(result.service_regions.availability).toBe('available');
    expect(result.service_periods.availability).toBe('available');
  });

  it('rejects malformed root fields rather than silently widening the API', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({
      ...STAFF_CASE_PREFERENCE_RESPONSE,
      data: { ...STAFF_CASE_PREFERENCE_RESPONSE.data, raw_workbook: {} },
    }));
    await expect(createStaffCasePreferenceSummaryClient().query(11)).rejects.toBeInstanceOf(StaffCasePreferenceValidationError);
  });
});
