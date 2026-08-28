/**
 * File: staff_payout_remediation_client.test.ts
 * Description: 驗證 PAYOUT-001 client 的 strict Query／Preview／Apply／Job contract。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { staffPayoutRemediationClient } from '../api/staff_payables/staff_payout_remediation_client';
import { StaffPayoutRemediationError } from '../api/staff_payables/staff_payout_remediation_errors';
import type { StaffPayoutPreview } from '../api/staff_payables/staff_payout_remediation_schemas';

const response = (data: unknown, status = 200) => ({ ok: status >= 200 && status < 300, status, statusText: 'OK', headers: new Headers({ 'content-type': 'application/json' }), json: async () => ({ success: true, message: 'ok', data, error: null }) });
const preview: StaffPayoutPreview = {
  event_type: 'payout', staff_payables_version: 4, bank_facts_version: 8,
  candidate: {
    staff_id: 11, bank_total: { amount: 12000 }, obligation_total: { amount: 12000 },
    allocations: [{ bank_fact_identity: 'bank:91', obligation_identity: 'obligation:11:CASE-1', amount: { amount: 12000 } }],
    fingerprint: 'a'.repeat(64), events: [{ identity: 'event:1', event_type: 'payout', status: 'succeeded', staff_id: 11, amount: { amount: 12000 }, finance_import_fact_identity: 'bank:91', reversal_of_event_identity: null }],
    obligation_links: [{ event_identity: 'event:1', obligation_identity: 'obligation:11:CASE-1', allocated_amount: { amount: 12000 } }],
    resulting_status: 'completed', difference_mode: null, recovery: null,
  }, preview_fingerprint: 'b'.repeat(64),
};

describe('PAYOUT-001 remediation client', () => {
  const originalFetch = globalThis.fetch;
  beforeEach(() => sessionClient.setSession('payout-token', { id: 7, username: 'admin', display_name: 'Admin', role: 'admin' }));
  afterEach(() => { globalThis.fetch = originalFetch; sessionClient.clearSession(); vi.restoreAllMocks(); });

  it('Preview／Apply 使用正式 endpoint、版本、fingerprint 與冪等 headers', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(preview))
      .mockResolvedValueOnce(response({ job_id: 'job-1', status_url: '/api/v1/jobs/job-1' }, 202));
    const selected = { financeImportRowIds: [91], obligationIdentities: ['obligation:11:CASE-1'] };
    const received = await staffPayoutRemediationClient.preview(selected);
    expect(received.preview_fingerprint).toBe('b'.repeat(64));
    await staffPayoutRemediationClient.apply(received, selected, '電話核對後核銷既有銀行事實', { idempotencyKey: 'payout.apply:one', correlationId: 'payout-correlation' });
    const calls = vi.mocked(globalThis.fetch).mock.calls;
    expect(calls[0][0]).toBe('/api/v1/staff-payables/payout/preview');
    expect(JSON.parse(String(calls[0][1]?.body))).toEqual({ finance_import_row_ids: [91], obligation_identities: ['obligation:11:CASE-1'] });
    expect(calls[1][0]).toBe('/api/v1/staff-payables/payout/apply');
    expect(JSON.parse(String(calls[1][1]?.body))).toMatchObject({ expected_staff_payables_version: 4, expected_bank_facts_version: 8, preview_fingerprint: 'b'.repeat(64), reason: '電話核對後核銷既有銀行事實' });
    expect(calls[1][1]?.headers).toMatchObject({ Authorization: 'Bearer payout-token', 'Idempotency-Key': 'payout.apply:one', 'X-Correlation-ID': 'payout-correlation' });
  });

  it('Job terminal 嚴格解碼並拒絕錯誤 command 或 identity', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({ job_id: 'job-1', status: 'succeeded', command_type: 'staff_payout_apply', attempt_count: 1, max_attempts: 3, outcome: { kind: 'success', schema_version: 1, result_reference: 'staff_payout:11' } }));
    await expect(staffPayoutRemediationClient.queryJob('job-1')).resolves.toMatchObject({ status: 'succeeded' });
    globalThis.fetch = vi.fn().mockResolvedValue(response({ job_id: 'job-1', status: 'succeeded', command_type: 'wrong', attempt_count: 1, max_attempts: 3, outcome: null }));
    await expect(staffPayoutRemediationClient.queryJob('job-1')).rejects.toMatchObject({ code: 'STAFF_PAYOUT_SCHEMA_MISMATCH' });
  });

  it('拒絕空白／重複 selection、無 reason 與無登入，且不發送 request', async () => {
    const fetch = vi.fn(); globalThis.fetch = fetch;
    await expect(staffPayoutRemediationClient.preview({ financeImportRowIds: [91, 91], obligationIdentities: ['obligation:11:CASE-1'] })).rejects.toBeInstanceOf(StaffPayoutRemediationError);
    await expect(staffPayoutRemediationClient.preview({ financeImportRowIds: [91], obligationIdentities: ['  '] })).rejects.toBeInstanceOf(StaffPayoutRemediationError);
    await expect(staffPayoutRemediationClient.apply(preview, { financeImportRowIds: [91], obligationIdentities: ['obligation:11:CASE-1'] }, ' ', { idempotencyKey: 'x', correlationId: 'y' })).rejects.toBeInstanceOf(StaffPayoutRemediationError);
    sessionClient.clearSession();
    await expect(staffPayoutRemediationClient.preview({ financeImportRowIds: [91], obligationIdentities: ['obligation:11:CASE-1'] })).rejects.toMatchObject({ code: 'STAFF_PAYOUT_UNAUTHENTICATED' });
    expect(fetch).not.toHaveBeenCalled();
  });
});
