/**
 * File: subsidy_report_query_client.test.ts
 * Description: 驗證補助報表client的fresh Session、GET、strict decode、aggregate與PII拒絕。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { subsidyReportQueryClient } from '../api/reports/subsidy_report_query_client';
import { SUBSIDY_REPORT_RESPONSE } from './fixtures/reports/subsidy_report_query_contract_fixtures';
function response(body: object) { return { ok: true, status: 200, statusText: 'OK', headers: new Headers({ 'content-type': 'application/json' }), json: async () => body }; }
describe('subsidy report query client', () => {
  const originalFetch = globalThis.fetch;
  beforeEach(() => sessionClient.setSession('reports-token', { id: 7, username: 'reports', display_name: 'Reports', role: 'admin' }));
  afterEach(() => { globalThis.fetch = originalFetch; sessionClient.clearSession(); });
  it('uses one GET with fresh bearer and strict period', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response(SUBSIDY_REPORT_RESPONSE));
    await subsidyReportQueryClient.query({ kind: 'quarterly', applicationYear: 2026, quarter: 1 });
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    expect(vi.mocked(globalThis.fetch).mock.calls[0][0]).toBe('/api/v1/finance-reports/subsidy-reconciliation/quarterly?application_year=2026&quarter=1');
    expect(vi.mocked(globalThis.fetch).mock.calls[0][1]?.method).toBe('GET');
  });
  it('rejects raw PII and aggregate mismatch', async () => {
    const row = SUBSIDY_REPORT_RESPONSE.data.partitions[0].rows[0];
    globalThis.fetch = vi.fn().mockResolvedValueOnce(response({ ...SUBSIDY_REPORT_RESPONSE, data: { ...SUBSIDY_REPORT_RESPONSE.data, partitions: [{ ...SUBSIDY_REPORT_RESPONSE.data.partitions[0], rows: [{ ...row, identity_card_masked: 'A123456789' }] }, SUBSIDY_REPORT_RESPONSE.data.partitions[1]] } })).mockResolvedValueOnce(response({ ...SUBSIDY_REPORT_RESPONSE, data: { ...SUBSIDY_REPORT_RESPONSE.data, total_amount_ntd: 1 } }));
    await expect(subsidyReportQueryClient.query({ kind: 'quarterly', applicationYear: 2026, quarter: 1 })).rejects.toThrow(/PII/);
    await expect(subsidyReportQueryClient.query({ kind: 'quarterly', applicationYear: 2026, quarter: 1 })).rejects.toThrow(/aggregate/);
  });
});
