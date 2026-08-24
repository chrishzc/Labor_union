/**
 * File: finance_import_mutation_client.test.ts
 * Description: 驗證銀行流水 React client 的安全入庫、durable Apply 及 terminal receipt strict contract。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { FinanceWorkbookSnapshot, financeImportMutationClient } from '../api/finance_import/finance_import_mutation_client';

const digest = 'a'.repeat(64);
const fingerprint = 'b'.repeat(64);
const response = (data: object) => new Response(JSON.stringify({ success: true, message: 'ok', data, error: null }), { status: 200, headers: { 'content-type': 'application/json' } });

describe('Finance Import mutation client', () => {
  beforeEach(() => sessionClient.setSession('finance-mutation-token', { id: 7, username: 'finance', display_name: 'Finance', role: 'admin' }));
  afterEach(() => { sessionClient.clearSession(); vi.restoreAllMocks(); });

  it('keeps workbook digest, command identity, accepted replay and terminal receipt typed', async () => {
    const snapshot = await FinanceWorkbookSnapshot.fromFile(new File(['bank'], 'bank.xlsx'));
    const ingestion = { batch_identity: 'finance-import-batch:9', source_content_digest: snapshot.sha256, source_row_count: 1, canonical_created_count: 1, duplicate_occurrence_count: 0, source_warning_count: 0, source_warning_created_count: 0, replayed: false };
    const preview = { batch_identity: ingestion.batch_identity, batch_version: 1, source_content_digest: snapshot.sha256, classifier_version: 'v1', fingerprint_version: 'v1', counts: { source_rows: 1, canonical_created: 1, duplicate_occurrences: 0, ready_dispatch: 1, existing: 0, manual_review: 0, business_pending: 0, blocked: 0 }, dispatch_summaries: [], rows: [], blocking_codes: [], apply_allowed: true, preview_fingerprint: fingerprint };
    const accepted = { job_id: 'job-finance-1', status_url: '/api/v1/jobs/job-finance-1', replayed: true };
    const outcome = { job_id: accepted.job_id, status: 'succeeded', attempt_count: 1, max_attempts: 3, result_reference: 'finance_import_batch:finance-import-batch:9', receipt: { batch_identity: ingestion.batch_identity, resulting_batch_version: 2, preview_fingerprint: fingerprint, reconciled_count: 1, existing_count: 0, pending_count: 0 } };
    globalThis.fetch = vi.fn().mockResolvedValueOnce(response(ingestion)).mockResolvedValueOnce(response(preview)).mockResolvedValueOnce(response(accepted)).mockResolvedValueOnce(response(outcome));

    await expect(financeImportMutationClient.ingest(snapshot, { idempotencyKey: 'ingest-1', correlationId: 'ingest-correlation' })).resolves.toEqual(ingestion);
    const plan = await financeImportMutationClient.preview(ingestion.batch_identity);
    await expect(financeImportMutationClient.apply(plan, '核對完成', { idempotencyKey: 'apply-1', correlationId: 'apply-correlation' })).resolves.toEqual(accepted);
    await expect(financeImportMutationClient.queryBatchOutcome(accepted.job_id)).resolves.toEqual(outcome);
    const [uploadPath, uploadOptions] = vi.mocked(globalThis.fetch).mock.calls[0] ?? [];
    expect(uploadPath).toBe('/api/v1/finance-import/workbooks/ingest');
    expect((uploadOptions?.body as FormData).get('workbook')).toBeInstanceOf(File);
    const [, applyOptions] = vi.mocked(globalThis.fetch).mock.calls[2] ?? [];
    expect(new Headers(applyOptions?.headers).get('Idempotency-Key')).toBe('apply-1');
  });

  it('rejects raw or incomplete terminal receipt payloads', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({ job_id: 'job-finance-1', status: 'succeeded', attempt_count: 1, max_attempts: 3, result_reference: 'safe:1', receipt: { batch_identity: 'finance-import-batch:9', resulting_batch_version: 2, preview_fingerprint: digest, reconciled_count: 1, existing_count: 0, pending_count: 0, raw_bank_account: 'unsafe' } }));
    await expect(financeImportMutationClient.queryBatchOutcome('job-finance-1')).rejects.toThrow();
  });
});
