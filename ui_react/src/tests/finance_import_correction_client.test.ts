/**
 * File: finance_import_correction_client.test.ts
 * Description: 驗證帳務異常更正 client 僅接受嚴格 Preview、durable Apply 與 terminal receipt。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { financeImportCorrectionClient, financeRefundBlockerMessage, type FinanceImportCorrectionSelection } from '../api/finance_import/finance_import_correction_client';

const fingerprint = 'a'.repeat(64);
const response = (data: object) => new Response(JSON.stringify({ success: true, message: 'ok', data, error: null }), { status: 200, headers: { 'content-type': 'application/json' } });
const selection: FinanceImportCorrectionSelection = {
  row_identity: 'finance-import-row:9', classification_type: 'client_refund_return', target_obligation_identities: ['client-obligation:1'],
  refund_ledger_entry_identity: 'client-ledger-entry:3', allow_partial_refund_recovery: false, allow_refund_overage_recovery: false,
  allow_client_receipt_overage: false, reason: '核對退匯', evidence: ['receipt:9'],
};

describe('Finance Import correction client', () => {
  beforeEach(() => sessionClient.setSession('finance-correction-token', { id: 7, username: 'finance', display_name: 'Finance', role: 'admin' }));
  afterEach(() => { sessionClient.clearSession(); vi.restoreAllMocks(); });

  it.each([0, 30, 100])('decodes the owner-derived refund fee and zero balance: %s', async fee => {
    const payload = { candidate: { row_identity: 'finance-import-row:9', batch_identity: 'finance-import-batch:9', classification_type: 'client_refund', owning_domain: 'client_finance', bank_amount_ntd: 12000-fee,
      allocations: [{ obligation_identity: 'client-obligation:1', amount_ntd: 12000 }], reason: '', evidence: ['synthetic'], refund_ledger_entry_identity: null,
      allow_partial_refund_recovery: false, allow_refund_overage_recovery: false, allow_client_receipt_overage: false, candidate_fingerprint: fingerprint,
      refund_summary: { transfer_fee_ntd: fee, remaining_ntd: 0 } }, batch_version: 0, canonical_fact_version: 0, alert_version: 0, preview_fingerprint: fingerprint };
    globalThis.fetch = vi.fn().mockResolvedValue(response(payload));
    const result = await financeImportCorrectionClient.preview({ ...selection, classification_type: 'client_refund', refund_ledger_entry_identity: null });
    expect(result.candidate.refund_summary).toEqual({ transfer_fee_ntd: fee, remaining_ntd: 0 });
    for (const refund_summary of [{ transfer_fee_ntd: 101, remaining_ntd: 0 }, { transfer_fee_ntd: 0, remaining_ntd: -1 }, { transfer_fee_ntd: 30, remaining_ntd: 0, raw_account: 'private' }]) {
      globalThis.fetch = vi.fn().mockResolvedValue(response({ ...payload, candidate: { ...payload.candidate, refund_summary } }));
      await expect(financeImportCorrectionClient.preview({ ...selection, classification_type: 'client_refund', refund_ledger_entry_identity: null })).rejects.toThrow();
    }
  });

  it.each(['client_refund_recipient_account_ambiguous', 'client_refund_recipient_account_mismatch', 'client_refund_source_account_missing', 'outgoing_client_refund_no_open_obligation', 'due_date_missing', 'bank_transaction_date_missing', 'bank_currency_not_twd', 'subsidy_advance_not_due', 'client_subsidy_memo_case_mismatch', 'client_subsidy_memo_staff_matched', 'refund_requires_exact_settlement', 'allocation_exceeds_obligation'])(
    'uses the same safe reason for a rejected preview and failed job: %s', async code => {
      const blocked = () => new Response(JSON.stringify({ detail: { error: {
        category: 'domain_blocked', code, message: 'Finance Import correction cannot be posted.', correlation_id: 'synthetic',
        field_errors: [], domain_blockers: [code], retryable: false, current_version: null,
      } } }), { status: 409, headers: { 'content-type': 'application/json' } });
      globalThis.fetch = vi.fn().mockResolvedValueOnce(blocked()).mockResolvedValueOnce(blocked())
        .mockResolvedValueOnce(response({ job_id: 'failed-refund', status: 'failed', attempt_count: 1, max_attempts: 3,
          result_reference: null, receipt: null, failure_code: code }));
      const selected = { ...selection, classification_type: code.startsWith('subsidy_') || code.startsWith('client_subsidy_') ? 'client_subsidy_return' as const : 'client_refund' as const, refund_ledger_entry_identity: null };
      const error = await financeImportCorrectionClient.preview(selected).catch(value => value);
      const applyError = await financeImportCorrectionClient.apply({ batch_version: 0, canonical_fact_version: 0, alert_version: 0, preview_fingerprint: fingerprint } as never,
        selected, { idempotencyKey: 'blocked', correlationId: 'synthetic' }).catch(value => value);
      const outcome = await financeImportCorrectionClient.queryOutcome('failed-refund');
      expect(error.code).toBe(code);
      expect(error.message).toBe(financeRefundBlockerMessage(outcome.failure_code, selected.classification_type));
      expect(applyError.code).toBe(code);
      expect(applyError.message).toBe(error.message);
      expect(error.message).not.toContain('Finance Import');
    },
  );

  it('keeps Preview versions, durable Apply command identity, and typed terminal receipt', async () => {
    const preview = { candidate: { row_identity: selection.row_identity, batch_identity: 'finance-import-batch:9', classification_type: selection.classification_type, owning_domain: 'client_finance', bank_amount_ntd: 100, allocations: [{ obligation_identity: 'client-obligation:1', amount_ntd: 100 }], reason: selection.reason, evidence: selection.evidence, refund_ledger_entry_identity: selection.refund_ledger_entry_identity, allow_partial_refund_recovery: false, allow_refund_overage_recovery: false, allow_client_receipt_overage: false, candidate_fingerprint: fingerprint }, batch_version: 1, canonical_fact_version: 4, alert_version: 2, preview_fingerprint: fingerprint };
    const accepted = { job_id: 'job-correction-1', status_url: '/api/v1/jobs/job-correction-1', replayed: false };
    const outcome = { job_id: accepted.job_id, status: 'succeeded', attempt_count: 1, max_attempts: 3, result_reference: 'finance_import_correction:finance-import-row:9', receipt: { row_identity: selection.row_identity, batch_identity: 'finance-import-batch:9', resulting_batch_version: 2, classification_event_count: 1, ledger_entry_count: 1, allocation_count: 1, reconciliation_receipt_count: 1, alert_resolved_event_count: 1, preview_fingerprint: fingerprint } };
    globalThis.fetch = vi.fn().mockResolvedValueOnce(response(preview)).mockResolvedValueOnce(response(accepted)).mockResolvedValueOnce(response(outcome));

    const receivedPreview = await financeImportCorrectionClient.preview(selection);
    await expect(financeImportCorrectionClient.apply(receivedPreview, selection, { idempotencyKey: 'correction-apply-1', correlationId: 'correction-correlation' })).resolves.toEqual(accepted);
    await expect(financeImportCorrectionClient.queryOutcome(accepted.job_id)).resolves.toEqual(outcome);
    const [path, options] = vi.mocked(globalThis.fetch).mock.calls[1] ?? [];
    expect(path).toBe('/api/v1/finance-import/corrections/apply');
    expect(new Headers(options?.headers).get('Idempotency-Key')).toBe('correction-apply-1');
  });

  it('fails closed when a terminal receipt includes undeclared data', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({ job_id: 'job-correction-1', status: 'succeeded', attempt_count: 1, max_attempts: 3, result_reference: 'safe:1', receipt: { row_identity: selection.row_identity, batch_identity: 'finance-import-batch:9', resulting_batch_version: 2, classification_event_count: 1, ledger_entry_count: 1, allocation_count: 1, reconciliation_receipt_count: 1, alert_resolved_event_count: 1, preview_fingerprint: fingerprint, raw_bank_account: 'unsafe' } }));
    await expect(financeImportCorrectionClient.queryOutcome('job-correction-1')).rejects.toThrow();
  });

  it('accepts zero legacy alert events but rejects negative counts', async () => {
    const receipt = { row_identity: selection.row_identity, batch_identity: 'finance-import-batch:9', resulting_batch_version: 2, classification_event_count: 1, ledger_entry_count: 1, allocation_count: 1, reconciliation_receipt_count: 1, alert_resolved_event_count: 0, preview_fingerprint: fingerprint };
    globalThis.fetch = vi.fn().mockResolvedValue(response({ job_id: 'job-correction-1', status: 'succeeded', attempt_count: 1, max_attempts: 3, result_reference: 'safe:1', receipt }));
    await expect(financeImportCorrectionClient.queryOutcome('job-correction-1')).resolves.toMatchObject({ receipt });

    globalThis.fetch = vi.fn().mockResolvedValue(response({ job_id: 'job-correction-1', status: 'succeeded', attempt_count: 1, max_attempts: 3, result_reference: 'safe:1', receipt: { ...receipt, alert_resolved_event_count: -1 } }));
    await expect(financeImportCorrectionClient.queryOutcome('job-correction-1')).rejects.toThrow();
  });
});
