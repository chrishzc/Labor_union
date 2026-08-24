/**
 * File: finance_import_correction_client.test.ts
 * Description: 驗證帳務異常更正 client 僅接受嚴格 Preview、durable Apply 與 terminal receipt。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { financeImportCorrectionClient, type FinanceImportCorrectionSelection } from '../api/finance_import/finance_import_correction_client';

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
});
