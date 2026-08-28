/**
 * File: staff_overpayment_recovery_client.test.ts
 * Description: 驗證 Staff recovery client 的 strict decode、typed payload、版本與精確調整限制。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { transport } from '../api/shared/transport';
import {
  createStaffOverpaymentRecoveryCommandIdentity,
  staffOverpaymentRecoveryClient,
} from '../api/staff_payables/staff_overpayment_recovery_client';

const envelope = (data: unknown) => ({ success: true, message: 'ok', data, error: null });
const query = {
  staff_id: 7,
  recovery_identity: 'staff-overpayment-recovery:1',
  remaining_amount_ntd: 500,
  status: 'open' as const,
  recovery_version: 3,
  staff_payables_version: 9,
  source_bank_fact_references: ['redacted:source'],
  source_payout_event_references: ['redacted:payout'],
  source_obligation_references: ['redacted:obligation'],
  matchings: [],
};
const matchingPreview = {
  recovery_identity: query.recovery_identity,
  staff_id: 7,
  finance_import_row_identity: 'redacted:incoming',
  recovery_version: 3,
  staff_payables_version: 9,
  preview_fingerprint: 'a'.repeat(64),
};
const adjustmentPreview = {
  recovery_identity: query.recovery_identity,
  recovery_version: 3,
  staff_payables_version: 9,
  adjustment_amount_ntd: 500,
  remaining_before_ntd: 500,
  remaining_after_ntd: 0 as const,
  resulting_status: 'adjusted' as const,
  preview_fingerprint: 'b'.repeat(64),
};

describe('staffOverpaymentRecoveryClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal('crypto', { randomUUID: () => '12345678-1234-4234-8234-123456789abc' });
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('session-token');
  });

  it('uses the owner GET and rejects identity drift or extra response fields', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValueOnce(envelope(query));
    await expect(staffOverpaymentRecoveryClient.query(7, query.recovery_identity)).resolves.toEqual(query);
    expect(get).toHaveBeenCalledWith(
      '/api/v1/staff-payables/overpayment-recoveries/7/staff-overpayment-recovery%3A1',
      expect.objectContaining({ token: 'session-token' }),
    );

    vi.mocked(get).mockResolvedValueOnce(envelope({ ...query, unexpected: true }));
    await expect(staffOverpaymentRecoveryClient.query(7, query.recovery_identity)).rejects.toMatchObject({ code: 'STAFF_RECOVERY_SCHEMA_MISMATCH' });
  });

  it('sends evidence-bound matching Preview and Apply with expected versions', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValueOnce(envelope(matchingPreview));
    const input = { recovery_identity: query.recovery_identity, finance_import_row_id: 11, evidence_reference: '電話紀錄:11' };
    await expect(staffOverpaymentRecoveryClient.previewMatching(input)).resolves.toEqual(matchingPreview);
    expect(post).toHaveBeenCalledWith(
      '/api/v1/staff-payables/overpayment-recoveries/matching/preview',
      input,
      expect.objectContaining({ token: 'session-token' }),
    );

    vi.mocked(post).mockResolvedValueOnce(envelope({
      matching_identity: 'staff-recovery-match:1', matching_version: 1,
      recovery_identity: query.recovery_identity, staff_id: 7,
      finance_import_row_identity: 'redacted:incoming', recovery_version: 4,
      staff_payables_version: 10, evidence_reference: input.evidence_reference,
    }));
    await expect(staffOverpaymentRecoveryClient.applyMatching(
      matchingPreview,
      { ...input, reason: '電話確認已收到退回款。' },
      createStaffOverpaymentRecoveryCommandIdentity('matching-apply'),
    )).resolves.toMatchObject({ matching_identity: 'staff-recovery-match:1' });
    expect(post).toHaveBeenLastCalledWith(
      '/api/v1/staff-payables/overpayment-recoveries/matching/apply',
      expect.objectContaining({ expected_recovery_version: 3, expected_staff_payables_version: 9, evidence_reference: input.evidence_reference }),
      expect.objectContaining({ headers: expect.objectContaining({ 'Idempotency-Key': expect.stringContaining('matching-apply') }) }),
    );
  });

  it('never allows partial Staff adjustment and requires evidence before transport', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValueOnce(envelope(adjustmentPreview));
    await expect(staffOverpaymentRecoveryClient.previewAdjustment({
      recovery_identity: query.recovery_identity, adjustment_amount_ntd: 500, evidence_reference: '電話紀錄:12',
    })).resolves.toEqual(adjustmentPreview);
    await expect(staffOverpaymentRecoveryClient.applyAdjustment(
      adjustmentPreview,
      { recovery_identity: query.recovery_identity, adjustment_amount_ntd: 499, evidence_reference: '電話紀錄:12', reason: '人工確認結清。' },
      createStaffOverpaymentRecoveryCommandIdentity('adjustment-apply'),
    )).rejects.toMatchObject({ code: 'STAFF_RECOVERY_AMOUNT_STALE' });
    expect(post).toHaveBeenCalledTimes(1);

    await expect(staffOverpaymentRecoveryClient.previewAdjustment({
      recovery_identity: query.recovery_identity, adjustment_amount_ntd: 500, evidence_reference: ' ',
    })).rejects.toMatchObject({ code: 'STAFF_RECOVERY_INPUT_INVALID' });
  });

  it('fails closed on non-positive versions and malformed owner Preview', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValueOnce(envelope({ ...adjustmentPreview, adjustment_amount_ntd: 499 }));
    await expect(staffOverpaymentRecoveryClient.previewAdjustment({
      recovery_identity: query.recovery_identity, adjustment_amount_ntd: 500, evidence_reference: 'evidence:13',
    })).rejects.toMatchObject({ code: 'STAFF_RECOVERY_SCHEMA_MISMATCH' });
    expect(post).toHaveBeenCalledTimes(1);
  });
});
