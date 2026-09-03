/**
 * File: staff_case_preference_summary_client.test.ts
 * Description: 驗證接案偏好摘要 client 的 strict decode、Session 與 identity 邊界。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { createStaffCasePreferenceSummaryClient } from '../api/staff_case_preference_summary/staff_case_preference_summary_client';
import { ApiDecodeError, ApiHttpError } from '../api/shared/typed_errors';
import { STAFF_CASE_PREFERENCE_SUMMARY_RESPONSE } from './fixtures/staff/staff_case_preference_summary_contract_fixtures';

function response(body: object, ok = true, status = 200) {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
  };
}

describe('staff case preference summary client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    sessionClient.setSession('staff-case-preference-token', {
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

  it('sends one identity-bound GET with the current memory token', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response(STAFF_CASE_PREFERENCE_SUMMARY_RESPONSE));

    const summary = await createStaffCasePreferenceSummaryClient().query(11, {
      headers: { Authorization: 'Bearer injected' },
    });

    expect(summary).toEqual(STAFF_CASE_PREFERENCE_SUMMARY_RESPONSE.data);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(url).toBe('/api/v1/staff/11/case-preference-summary');
    expect(options?.method).toBe('GET');
    expect(options?.headers).toMatchObject({ Authorization: 'Bearer staff-case-preference-token' });
  });

  it('strictly rejects extra fields and invalid other-detail status invariants', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response({
        ...STAFF_CASE_PREFERENCE_SUMMARY_RESPONSE,
        data: {
          ...STAFF_CASE_PREFERENCE_SUMMARY_RESPONSE.data,
          transportation: {
            ...STAFF_CASE_PREFERENCE_SUMMARY_RESPONSE.data.transportation,
            unexpected: true,
          },
        },
      }))
      .mockResolvedValueOnce(response({
        ...STAFF_CASE_PREFERENCE_SUMMARY_RESPONSE,
        data: {
          ...STAFF_CASE_PREFERENCE_SUMMARY_RESPONSE.data,
          transportation: {
            values: ['機車'],
            other_detail: '不得出現',
            other_detail_status: 'source_not_ready',
          },
        },
      }));
    const client = createStaffCasePreferenceSummaryClient();

    await expect(client.query(11)).rejects.toBeInstanceOf(ApiDecodeError);
    await expect(client.query(11)).rejects.toBeInstanceOf(ApiDecodeError);
  });

  it('rejects response identity drift', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({
      ...STAFF_CASE_PREFERENCE_SUMMARY_RESPONSE,
      data: { ...STAFF_CASE_PREFERENCE_SUMMARY_RESPONSE.data, staff_id: 12 },
    }));

    await expect(createStaffCasePreferenceSummaryClient().query(11)).rejects.toBeInstanceOf(ApiDecodeError);
  });

  it('fails before fetch without a memory session', async () => {
    globalThis.fetch = vi.fn();
    sessionClient.clearSession();

    await expect(createStaffCasePreferenceSummaryClient().query(11)).rejects.toBeInstanceOf(ApiHttpError);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
