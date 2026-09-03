/**
 * File: access_audit_query_client.test.ts
 * Description: 驗證 Access Audit list/detail GET、Bearer 與 strict decode。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { queryAdminAudit, queryAdminAuditDetail } from '../api/access/audit_query_client';
import { sessionClient } from '../api/auth/session_client';
import { AUDIT_DETAIL_FIXTURE, AUDIT_PAGE_FIXTURE } from './fixtures/access/audit_query_contract_fixtures';

const response = (data: unknown) => new Response(
  JSON.stringify({ success: true, message: 'ok', data, error: null }),
  { status: 200, headers: { 'content-type': 'application/json' } },
);

describe('Access Audit query client', () => {
  beforeEach(() => sessionClient.setSession('fresh-audit-token', {
    id: 1, username: 'root', display_name: 'Root', role: 'system_admin',
  }));
  afterEach(() => { sessionClient.clearSession(); vi.restoreAllMocks(); });

  it('uses GET and current memory bearer for list and detail', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(response(AUDIT_PAGE_FIXTURE))
      .mockResolvedValueOnce(response(AUDIT_DETAIL_FIXTURE));
    await expect(queryAdminAudit({ page: 1 })).resolves.toEqual(AUDIT_PAGE_FIXTURE);
    await expect(queryAdminAuditDetail(10)).resolves.toEqual(AUDIT_DETAIL_FIXTURE);
    expect(fetchMock.mock.calls.map(([, request]) => request?.method)).toEqual(['GET', 'GET']);
    expect(fetchMock.mock.calls[1][0]).toContain('/api/v1/admin/audits/10');
    expect(fetchMock.mock.calls[1][1]?.headers).toMatchObject({ Authorization: 'Bearer fresh-audit-token' });
  });

  it('rejects raw or extra detail fields without fallback', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({
      ...AUDIT_DETAIL_FIXTURE,
      details: [{ key: 'password', value: 'secret' }],
      raw_payload: { phone: '0900000000' },
    }));
    await expect(queryAdminAuditDetail(10)).rejects.toMatchObject({ code: 'AUDIT_QUERY_INVALID' });
  });

  it('does not fetch without an authenticated token', async () => {
    sessionClient.clearSession();
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    await expect(queryAdminAuditDetail(10)).rejects.toMatchObject({ code: 'AUDIT_QUERY_UNAUTHENTICATED' });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
