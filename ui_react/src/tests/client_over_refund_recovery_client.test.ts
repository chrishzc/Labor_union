/**
 * File: client_over_refund_recovery_client.test.ts
 * Description: 驗證 client recovery owner client 的 strict decode、固定 endpoint、evidence 與 command identity。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { clientOverRefundRecoveryClient } from '../api/client_finance/client_over_refund_recovery_client';
import { ClientOverRefundRecoveryError } from '../api/client_finance/client_over_refund_recovery_errors';

const query = {
  case_no: 'CASE-1', recovery_identity: 'recovery:1', remaining_amount_ntd: 500, status: 'open',
  recovery_version: 3, account_version: 8, source_row_reference: 'bank:10', current_matchings: [],
};
const matchingPreview = {
  recovery_identity: 'recovery:1', finance_import_row_identity: '10', recovery_version: 3, account_version: 8, preview_fingerprint: 'a'.repeat(64),
};
function response(data: unknown) { return { ok: true, status: 200, statusText: 'OK', headers: new Headers({ 'content-type': 'application/json' }), json: async () => ({ success: true, message: 'ok', data, error: null }) }; }

describe('client over-refund recovery owner client', () => {
  beforeEach(() => {
    sessionClient.setSession('client-recovery-token', { id: 1, username: 'operator', display_name: 'Operator', role: 'admin' });
    vi.spyOn(globalThis, 'fetch');
  });
  afterEach(() => { vi.restoreAllMocks(); sessionClient.clearSession(); });

  it('queries the owner root with a strict GET contract', async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(response(query) as Response);
    await expect(clientOverRefundRecoveryClient.query('CASE-1', 'recovery:1')).resolves.toMatchObject(query);
    expect(vi.mocked(globalThis.fetch).mock.calls[0][0]).toBe('/api/v1/orders/CASE-1/client-finance/refund-overage-recovery/recovery%3A1');
    expect(vi.mocked(globalThis.fetch).mock.calls[0][1]?.method).toBe('GET');
  });

  it('rejects terminal/status drift and never lets malformed data reach the renderer', async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(response({ ...query, status: 'recovered', remaining_amount_ntd: 5 }) as Response);
    await expect(clientOverRefundRecoveryClient.query('CASE-1', 'recovery:1')).rejects.toMatchObject({ code: 'CLIENT_RECOVERY_SCHEMA_MISMATCH' });
  });

  it('rejects a valid-shaped Query response for a different owner identity', async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(response({ ...query, recovery_identity: 'recovery:other' }) as Response);
    await expect(clientOverRefundRecoveryClient.query('CASE-1', 'recovery:1')).rejects.toMatchObject({
      code: 'CLIENT_RECOVERY_OWNER_MISMATCH',
    });
  });

  it('sends independent evidence and expected versions on Apply', async () => {
    vi.mocked(globalThis.fetch)
      .mockResolvedValueOnce(response(matchingPreview) as Response)
      .mockResolvedValueOnce(response({ matching_identity: 'match:1', matching_version: 1, recovery_identity: 'recovery:1', finance_import_row_identity: '10', recovery_version: 3, account_version: 8, evidence_reference: 'phone-log:1' }) as Response);
    const preview = await clientOverRefundRecoveryClient.previewMatching('CASE-1', { recovery_identity: 'recovery:1', finance_import_row_id: 10, evidence_reference: 'phone-log:1' });
    await clientOverRefundRecoveryClient.applyMatching('CASE-1', { recovery_identity: 'recovery:1', finance_import_row_id: 10, evidence_reference: 'phone-log:1', expected_recovery_version: preview.recovery_version, expected_account_version: preview.account_version, preview_fingerprint: preview.preview_fingerprint, reason: '電話確認後建立配對' }, { idempotencyKey: 'client-recovery-match-1', correlationId: 'client-recovery-correlation-1' });
    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[1];
    expect(url).toBe('/api/v1/orders/CASE-1/client-finance/refund-overage-recovery/matching/apply');
    expect(options?.headers).toMatchObject({ 'Idempotency-Key': 'client-recovery-match-1', 'X-Correlation-ID': 'client-recovery-correlation-1' });
    expect(JSON.parse(String(options?.body))).toMatchObject({ evidence_reference: 'phone-log:1', reason: '電話確認後建立配對', expected_recovery_version: 3 });
  });

  it('requires authenticated session and non-empty evidence before network access', async () => {
    sessionClient.clearSession();
    await expect(clientOverRefundRecoveryClient.previewAdjustment('CASE-1', { recovery_identity: 'recovery:1', adjustment_amount_ntd: 10, evidence_reference: '' })).rejects.toBeInstanceOf(ClientOverRefundRecoveryError);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
