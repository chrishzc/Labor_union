/**
 * File: government_overpayment_recovery_client.test.ts
 * Description: 驗證 Government 溢撥 client 的 strict contract、分支與 command identity。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { governmentOverpaymentRecoveryClient } from '../api/government_subsidy/government_overpayment_recovery_client';

function response(data: unknown, status = 200): Response {
  return new Response(JSON.stringify({ success: true, message: 'ok', data, error: null }), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

const identity = 'government-overpayment:bank:11';
const query = {
  overpayment_identity: identity,
  payer_identity: 'hccg',
  remaining_amount_ntd: 900,
  status: 'pending_review',
  overpayment_version: 2,
  source_bank_fact_reference: 'finance-import-row:11',
  source_transaction_reference: 'government-subsidy-transaction:8',
  offset_targets: [{ claim_item_id: 31, claim_batch_id: 4, batch_version: 7, outstanding_amount_ntd: 900, payer_identity: 'hccg' }],
  return_recipient: {
    ready: true,
    blockers: [],
    agency_identity: 'hccg',
    agency_name: '新竹市政府',
    bank_code: '822',
    account_display: '******1234',
    account_fingerprint: 'a'.repeat(64),
    effective_date: '2026-08-01',
  },
  blockers: [],
  available_actions: ['offset', 'return'],
};

const preview = {
  overpayment_identity: identity,
  overpayment_version: 2,
  remaining_before_ntd: 900,
  disposition_amount_ntd: 900,
  remaining_after_ntd: 0,
  resulting_status: 'offset_applied',
  disposition_kind: 'offset',
  preview_fingerprint: 'b'.repeat(64),
};

const receipt = {
  overpayment_identity: identity,
  remaining_after_ntd: 0,
  status: 'offset_applied',
  preview_fingerprint: 'b'.repeat(64),
  payable_identity: null,
};

function setSession(): void {
  sessionClient.setSession('government-token', {
    id: 7,
    username: 'government-admin',
    display_name: 'Government test admin',
    role: 'operator',
    linked_line_user_id: null,
    capabilities: [],
    is_root: false,
    access_control_version: 1,
  });
}

describe('Government overpayment recovery client', () => {
  beforeEach(() => { vi.restoreAllMocks(); setSession(); });
  afterEach(() => { sessionClient.clearSession(); vi.restoreAllMocks(); });

  it('只使用 owner Query、finite disposition Preview／Apply 與 stable command headers', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(query))
      .mockResolvedValueOnce(response(preview))
      .mockResolvedValueOnce(response(receipt));
    globalThis.fetch = fetchMock;
    const previewRequest = {
      overpayment_identity: identity,
      disposition: 'offset' as const,
      targets: [{ claim_item_id: 31, amount_ntd: 900 }],
      due_date: null,
      evidence_reference: 'phone-call:case-11',
    };
    await expect(governmentOverpaymentRecoveryClient.query(identity)).resolves.toMatchObject({ overpayment_version: 2 });
    await expect(governmentOverpaymentRecoveryClient.preview(previewRequest)).resolves.toEqual(preview);
    await expect(governmentOverpaymentRecoveryClient.apply({
      ...previewRequest,
      expected_overpayment_version: 2,
      preview_fingerprint: preview.preview_fingerprint,
      reason: '人工核對後抵扣',
    }, { idempotencyKey: 'gov-overpayment-command-11', correlationId: 'gov-overpayment-correlation-11' })).resolves.toEqual(receipt);
    expect(fetchMock.mock.calls.map((call) => [call[1]?.method, call[0]])).toEqual([
      ['GET', `/api/v1/government-subsidy/overpayments/${encodeURIComponent(identity)}`],
      ['POST', '/api/v1/government-subsidy/overpayments/disposition/preview'],
      ['POST', '/api/v1/government-subsidy/overpayments/disposition/apply'],
    ]);
    const applyHeaders = new Headers(fetchMock.mock.calls[2][1]?.headers);
    expect(applyHeaders.get('Authorization')).toBe('Bearer government-token');
    expect(applyHeaders.get('Idempotency-Key')).toBe('gov-overpayment-command-11');
    expect(applyHeaders.get('X-Correlation-ID')).toBe('gov-overpayment-correlation-11');
    expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body))).toMatchObject({
      expected_overpayment_version: 2,
      preview_fingerprint: 'b'.repeat(64),
      reason: '人工核對後抵扣',
      evidence_reference: 'phone-call:case-11',
    });
  });

  it('offset／return 輸入不符合有限分支時在送出前 fail closed', async () => {
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock;
    await expect(governmentOverpaymentRecoveryClient.preview({
      overpayment_identity: identity,
      disposition: 'offset',
      targets: [],
      due_date: null,
      evidence_reference: 'evidence:11',
    })).rejects.toMatchObject({ code: 'GOVERNMENT_OVERPAYMENT_OFFSET_INPUT_INVALID' });
    await expect(governmentOverpaymentRecoveryClient.preview({
      overpayment_identity: identity,
      disposition: 'return',
      targets: [{ claim_item_id: 31, amount_ntd: 900 }],
      due_date: '2026-08-30',
      evidence_reference: 'evidence:11',
    })).rejects.toMatchObject({ code: 'GOVERNMENT_OVERPAYMENT_RETURN_INPUT_INVALID' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('owner response 多出欄位或 status／remaining 矛盾時拒絕，不由 UI 猜完成', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({ ...query, extra: 'not-allowed' }));
    await expect(governmentOverpaymentRecoveryClient.query(identity)).rejects.toMatchObject({ code: 'GOVERNMENT_OVERPAYMENT_SCHEMA_MISMATCH' });
    globalThis.fetch = vi.fn().mockResolvedValue(response({ ...query, remaining_amount_ntd: 0 }));
    await expect(governmentOverpaymentRecoveryClient.query(identity)).rejects.toMatchObject({ code: 'GOVERNMENT_OVERPAYMENT_SCHEMA_MISMATCH' });
  });
});
