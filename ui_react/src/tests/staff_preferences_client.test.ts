/**
 * File: staff_preferences_client.test.ts
 * Description: 驗證 Staff 偏好 client 的 strict decode、fresh token、標頭與完整 snapshot。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  applyProfile,
  createStaffPreferencesClient,
  previewProfile,
  queryDefinitions,
  queryProfile,
} from '../api/staff_preferences/staff_preferences_client';
import {
  StaffPreferencesConflictError,
  StaffPreferencesUnauthenticatedError,
  StaffPreferencesValidationError,
} from '../api/staff_preferences/staff_preferences_errors';
import {
  STAFF_PREFERENCE_APPLY_RECEIPT_RESPONSE,
  STAFF_PREFERENCE_DEFINITIONS_EXTRA_FIELD_RESPONSE,
  STAFF_PREFERENCE_DEFINITIONS_RESPONSE,
  STAFF_PREFERENCE_PREVIEW_NULL_FINGERPRINT_RESPONSE,
  STAFF_PREFERENCE_PROFILE_MISSING_VERSION_RESPONSE,
  STAFF_PREFERENCE_PROFILE_PREVIEW_RESPONSE,
  STAFF_PREFERENCE_PROFILE_RESPONSE,
  STAFF_PREFERENCE_PROFILE_WRONG_VALUE_KIND_RESPONSE,
} from './fixtures/staff/staff_preferences_contract_fixtures';

function response(body: object, ok = true, status = 200) {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
  };
}

const PROFILE_INPUT = {
  values: [
    {
      preference_key: 'preferred_service_days',
      value: { kind: 'integer_range' as const, minimum: 22, maximum: 30 },
    },
    {
      preference_key: 'daily_service_hours',
      value: { kind: 'integer_set' as const, values: [4, 8] },
    },
  ],
};

describe('staff preferences client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    sessionClient.setSession('preferences-token-1', {
      id: 7,
      username: 'preferences-reader',
      display_name: 'Preferences Reader',
      role: 'admin',
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    sessionClient.clearSession();
  });

  it('queries definitions and profile with strict GET contracts', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(STAFF_PREFERENCE_DEFINITIONS_RESPONSE))
      .mockResolvedValueOnce(response(STAFF_PREFERENCE_PROFILE_RESPONSE));

    const definitions = await queryDefinitions();
    const profile = await queryProfile(7);

    expect(definitions).toHaveLength(2);
    expect(profile.staff_id).toBe(7);
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
    expect(vi.mocked(globalThis.fetch).mock.calls[0][0]).toBe(
      '/api/v1/scheduling/staff-matching-preferences/definitions',
    );
    expect(vi.mocked(globalThis.fetch).mock.calls[1][0]).toBe(
      '/api/v1/scheduling/staff-matching-preferences/staff/7',
    );
    for (const [, options] of vi.mocked(globalThis.fetch).mock.calls) {
      expect(options?.method).toBe('GET');
      expect(options?.headers).toMatchObject({
        Authorization: 'Bearer preferences-token-1',
      });
      expect(options?.headers).toHaveProperty('X-Correlation-ID');
    }
  });

  it('uses fresh memory token and strips caller Authorization', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(STAFF_PREFERENCE_PROFILE_RESPONSE))
      .mockResolvedValueOnce(response(STAFF_PREFERENCE_PROFILE_RESPONSE));
    const client = createStaffPreferencesClient();

    await client.queryProfile(7, {
      headers: { Authorization: 'Bearer caller-token', 'X-Trace': 'trace-01' },
    });
    sessionClient.setSession('preferences-token-2', {
      id: 8,
      username: 'rotated-preferences-reader',
      display_name: 'Rotated Preferences Reader',
      role: 'admin',
    });
    await client.queryProfile(7);

    expect(vi.mocked(globalThis.fetch).mock.calls[0][1]?.headers).toMatchObject({
      Authorization: 'Bearer preferences-token-1',
      'X-Trace': 'trace-01',
    });
    expect(vi.mocked(globalThis.fetch).mock.calls[0][1]?.headers).not.toMatchObject({
      Authorization: 'Bearer caller-token',
    });
    expect(vi.mocked(globalThis.fetch).mock.calls[1][1]?.headers).toMatchObject({
      Authorization: 'Bearer preferences-token-2',
    });
  });

  it('sends complete profile snapshot and exact preview/apply headers', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(STAFF_PREFERENCE_PROFILE_PREVIEW_RESPONSE))
      .mockResolvedValueOnce(response(STAFF_PREFERENCE_APPLY_RECEIPT_RESPONSE));

    await previewProfile(7, PROFILE_INPUT, { correlationId: 'preferences-preview-01' });
    await applyProfile(
      7,
      {
        ...PROFILE_INPUT,
        expected_version: 4,
        preview_fingerprint: 'a'.repeat(64),
        reason: '人工維護月嫂偏好',
      },
      {
        idempotencyKey: 'preferences-apply-01',
        correlationId: 'preferences-apply-01-correlation',
      },
    );

    const previewCall = vi.mocked(globalThis.fetch).mock.calls[0][1];
    const applyCall = vi.mocked(globalThis.fetch).mock.calls[1][1];
    expect(previewCall?.method).toBe('POST');
    expect(previewCall?.headers).toMatchObject({
      Authorization: 'Bearer preferences-token-1',
      'X-Correlation-ID': 'preferences-preview-01',
    });
    expect(applyCall?.method).toBe('POST');
    expect(applyCall?.headers).toMatchObject({
      Authorization: 'Bearer preferences-token-1',
      'X-Correlation-ID': 'preferences-apply-01-correlation',
      'Idempotency-Key': 'preferences-apply-01',
    });
    expect(JSON.parse(String(applyCall?.body))).toEqual({
      values: PROFILE_INPUT.values,
      expected_version: 4,
      preview_fingerprint: 'a'.repeat(64),
      reason: '人工維護月嫂偏好',
    });
  });

  it('fails closed without token and rejects duplicate snapshot identities', async () => {
    globalThis.fetch = vi.fn();
    sessionClient.clearSession();
    await expect(queryProfile(7)).rejects.toBeInstanceOf(
      StaffPreferencesUnauthenticatedError,
    );
    expect(globalThis.fetch).not.toHaveBeenCalled();

    sessionClient.setSession('preferences-token-1', {
      id: 7,
      username: 'preferences-reader',
      display_name: 'Preferences Reader',
      role: 'admin',
    });
    await expect(
      previewProfile(7, {
        values: [PROFILE_INPUT.values[0], PROFILE_INPUT.values[0]],
      }),
    ).rejects.toBeInstanceOf(StaffPreferencesValidationError);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('rejects missing, null, wrong discriminators and extra fields', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(STAFF_PREFERENCE_DEFINITIONS_EXTRA_FIELD_RESPONSE))
      .mockResolvedValueOnce(response(STAFF_PREFERENCE_PROFILE_MISSING_VERSION_RESPONSE))
      .mockResolvedValueOnce(response(STAFF_PREFERENCE_PREVIEW_NULL_FINGERPRINT_RESPONSE))
      .mockResolvedValueOnce(response(STAFF_PREFERENCE_PROFILE_WRONG_VALUE_KIND_RESPONSE));

    await expect(queryDefinitions()).rejects.toBeInstanceOf(StaffPreferencesValidationError);
    await expect(queryProfile(7)).rejects.toBeInstanceOf(StaffPreferencesValidationError);
    await expect(
      previewProfile(7, PROFILE_INPUT),
    ).rejects.toBeInstanceOf(StaffPreferencesValidationError);
    await expect(queryProfile(7)).rejects.toBeInstanceOf(StaffPreferencesValidationError);
  });

  it('binds query, preview and apply receipts to the requested staff identity', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response({
        ...STAFF_PREFERENCE_PROFILE_RESPONSE,
        data: { ...STAFF_PREFERENCE_PROFILE_RESPONSE.data, staff_id: 8 },
      }))
      .mockResolvedValueOnce(response({
        ...STAFF_PREFERENCE_PROFILE_PREVIEW_RESPONSE,
        data: { ...STAFF_PREFERENCE_PROFILE_PREVIEW_RESPONSE.data, staff_id: 8 },
      }))
      .mockResolvedValueOnce(response({
        ...STAFF_PREFERENCE_APPLY_RECEIPT_RESPONSE,
        data: { ...STAFF_PREFERENCE_APPLY_RECEIPT_RESPONSE.data, staff_id: 8 },
      }));

    await expect(queryProfile(7)).rejects.toBeInstanceOf(StaffPreferencesValidationError);
    await expect(previewProfile(7, PROFILE_INPUT)).rejects.toBeInstanceOf(StaffPreferencesValidationError);
    await expect(applyProfile(7, {
      ...PROFILE_INPUT,
      expected_version: 4,
      preview_fingerprint: 'a'.repeat(64),
      reason: 'identity 驗證',
    }, { idempotencyKey: 'preferences-identity-01' })).rejects.toBeInstanceOf(StaffPreferencesValidationError);
  });

  it('maps typed conflict envelope without presenting success', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      response(
        {
          detail: {
            error: {
              category: 'conflict',
              code: 'stale_version',
              message: '版本已過期',
              field_errors: [],
              domain_blockers: ['profile_version'],
              retryable: false,
              correlation_id: 'preferences-conflict-01',
              current_version: 5,
            },
          },
        },
        false,
        409,
      ),
    );

    await expect(
      applyProfile(
        7,
        {
          ...PROFILE_INPUT,
          expected_version: 4,
          preview_fingerprint: 'a'.repeat(64),
          reason: '重試舊預覽',
        },
        { idempotencyKey: 'preferences-conflict-01' },
      ),
    ).rejects.toBeInstanceOf(StaffPreferencesConflictError);
  });
});
