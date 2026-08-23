/**
 * File: account_query_client.test.ts
 * Description: 驗證帳號、稽核與背景工作查詢的 GET、Bearer 與 strict decode。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { queryAccountDirectory } from '../api/access/account_directory_client';
import { queryAdminAudit } from '../api/access/audit_query_client';
import { queryJobObservation } from '../api/jobs/job_observation_client';
import { ACCOUNT_DIRECTORY_FIXTURE, AUDIT_PAGE_FIXTURE, JOB_OBSERVATION_FIXTURE } from './fixtures/access/account_query_contract_fixtures';

describe('Account query clients', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    sessionClient.setSession('account-query-token', { id: 1, username: 'root-user', display_name: '根帳號', role: 'system_admin' });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('queries the three strict GET contracts with the latest bearer', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, headers: new Headers({ 'content-type': 'application/json' }), json: async () => ({ success: true, message: 'ok', data: ACCOUNT_DIRECTORY_FIXTURE, error: null }) })
      .mockResolvedValueOnce({ ok: true, status: 200, headers: new Headers({ 'content-type': 'application/json' }), json: async () => ({ success: true, message: 'ok', data: AUDIT_PAGE_FIXTURE, error: null }) })
      .mockResolvedValueOnce({ ok: true, status: 200, headers: new Headers({ 'content-type': 'application/json' }), json: async () => ({ success: true, message: 'ok', data: JOB_OBSERVATION_FIXTURE, error: null }) });

    await expect(queryAccountDirectory()).resolves.toEqual(ACCOUNT_DIRECTORY_FIXTURE);
    await expect(queryAdminAudit({ page: 1 })).resolves.toEqual(AUDIT_PAGE_FIXTURE);
    await expect(queryJobObservation('job-observation-1')).resolves.toEqual(JOB_OBSERVATION_FIXTURE);
    expect(globalThis.fetch).toHaveBeenCalledTimes(3);
    for (const [, request] of vi.mocked(globalThis.fetch).mock.calls) {
      expect(request?.method).toBe('GET');
      expect(request?.headers).toMatchObject({ Authorization: 'Bearer account-query-token' });
    }
  });

  it('rejects extra fields and never falls back to local data', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ success: true, message: 'ok', data: ACCOUNT_DIRECTORY_FIXTURE, extra: 'raw' }),
    });
    await expect(queryAccountDirectory()).rejects.toMatchObject({ code: 'ACCOUNT_DIRECTORY_INVALID' });
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });
});
