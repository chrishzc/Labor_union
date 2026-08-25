/**
 * File: anomalies_finance_correction_flow.test.tsx
 * Description: 驗證異常 Drawer 僅對註冊 Finance correction action 執行 Preview、Apply 與 receipt re-query。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AnomaliesPage } from '../pages/AnomaliesPage';
import { anomalyQueryClient } from '../api/anomalies/anomaly_query_client';
import { anomalyDetailClient } from '../api/anomalies/anomaly_detail_client';
import { financeImportCorrectionClient } from '../api/finance_import/finance_import_correction_client';
import { VALID_ANOMALY_SUMMARY_1, VALID_IMPORT_WARNING_TASK_HCM } from './fixtures/anomalies/anomaly_query_contract_fixtures';
import { VALID_ANOMALY_DETAIL_VIEW, VALID_ANOMALY_RECOVERY_CONTEXT_VIEW } from './fixtures/anomalies/anomaly_detail_contract_fixtures';

const fingerprint = 'c'.repeat(64);
const correctionRecovery = {
  ...VALID_ANOMALY_RECOVERY_CONTEXT_VIEW,
  available_actions: [{
    action_key: 'classify_client_refund_return', label: '處理客戶退款退匯', owning_domain: 'finance_import',
    form_schema_key: 'finance_import.correction.v1', source_binding_keys: ['finance_import_row_identity', 'source_version'],
    source_bindings: [{ kind: 'identity' as const, key: 'finance_import_row_identity', value: 'finance-import-row:42' }, { kind: 'version' as const, key: 'source_version', value: 7 }],
    required_operator_inputs: ['evidence', 'reason', 'refund_ledger_entry_identity', 'target_obligation_identities'],
    preview_operation: 'PreviewCorrectAndPostClientRefundReturn', apply_operation: 'CorrectAndPostClientRefundReturn',
    required_capability: 'finance_import.correct_and_post', completion_predicate: 'client_refund_return_cleared', action_contract_version: 1, requires_preview: true,
  }],
};

describe('Anomalies Finance Import correction flow', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(anomalyQueryClient, 'queryAnomalies').mockResolvedValue([VALID_ANOMALY_SUMMARY_1]);
    vi.spyOn(anomalyQueryClient, 'queryImportWarningTasks').mockResolvedValue([VALID_IMPORT_WARNING_TASK_HCM]);
    vi.spyOn(anomalyDetailClient, 'queryAnomalyDetail').mockResolvedValue(VALID_ANOMALY_DETAIL_VIEW);
    vi.spyOn(anomalyDetailClient, 'queryAnomalyRecovery').mockResolvedValue(correctionRecovery);
  });

  it('uses the bound action row, keeps generic Resolve locked, and shows only an observed business result as complete', async () => {
    const preview = { candidate: { row_identity: 'finance-import-row:42', batch_identity: 'finance-import-batch:9', classification_type: 'client_refund_return', owning_domain: 'client_finance', bank_amount_ntd: 100, allocations: [{ obligation_identity: 'obligation:SYNTH-19', amount_ntd: 100 }], reason: '核對退匯', evidence: ['receipt:42'], refund_ledger_entry_identity: 'ledger-refund:SYNTH-42', allow_partial_refund_recovery: false, allow_refund_overage_recovery: false, allow_client_receipt_overage: false, candidate_fingerprint: fingerprint }, batch_version: 1, canonical_fact_version: 7, alert_version: 3, preview_fingerprint: fingerprint };
    const accepted = { job_id: 'finance-correction-job-1', status_url: '/api/v1/jobs/finance-correction-job-1', replayed: false };
    const outcome = { job_id: accepted.job_id, status: 'succeeded' as const, attempt_count: 1, max_attempts: 3, result_reference: 'finance_import_correction:finance-import-row:42', receipt: { row_identity: 'finance-import-row:42', batch_identity: 'finance-import-batch:9', resulting_batch_version: 2, classification_event_count: 1, ledger_entry_count: 1, allocation_count: 1, reconciliation_receipt_count: 1, alert_resolved_event_count: 1, preview_fingerprint: fingerprint } };
    const previewSpy = vi.spyOn(financeImportCorrectionClient, 'preview').mockResolvedValue(preview);
    vi.spyOn(financeImportCorrectionClient, 'apply').mockResolvedValue(accepted);
    vi.spyOn(financeImportCorrectionClient, 'queryOutcome').mockResolvedValue(outcome);

    render(<AnomaliesPage />);
    await waitFor(() => expect(screen.getByText('假日排班尚未確認')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /查看處理方式 ➔/ }));
    await waitFor(() => expect(document.querySelector('[data-surface-id="anomalies.finance-correction"]')).not.toBeNull());
    expect(document.querySelector('[data-control-id="anomalies.finance-correction.classification"]')).toBeDisabled();
    fireEvent.change(document.querySelector('[data-control-id="anomalies.finance-correction.reason"]')!, { target: { value: '核對退匯' } });
    fireEvent.change(document.querySelector('[data-control-id="anomalies.finance-correction.evidence"]')!, { target: { value: 'receipt:42' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查更正影響' }));
    await waitFor(() => expect(previewSpy).toHaveBeenCalledWith(expect.objectContaining({ row_identity: 'finance-import-row:42', target_obligation_identities: ['obligation:SYNTH-19'], reason: '核對退匯', evidence: ['receipt:42'] })));
    fireEvent.click(screen.getByRole('button', { name: '確認並提交更正' }));
    await waitFor(() => expect(screen.getByText('帳務更正完成')).toBeInTheDocument());
    expect(screen.queryByText(accepted.job_id)).not.toBeInTheDocument();
    expect(screen.queryByText(/ledger 1|allocation 1|batch v2/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /確認排除異常/ })).toBeDisabled();
  });

  it('queued job 必須保持未完成，直到重新查詢讀到正式結果', async () => {
    const preview = { candidate: { row_identity: 'finance-import-row:42', batch_identity: 'finance-import-batch:9', classification_type: 'client_refund_return', owning_domain: 'client_finance', bank_amount_ntd: 100, allocations: [{ obligation_identity: 'obligation:SYNTH-19', amount_ntd: 100 }], reason: '核對退匯', evidence: ['receipt:42'], refund_ledger_entry_identity: 'ledger-refund:SYNTH-42', allow_partial_refund_recovery: false, allow_refund_overage_recovery: false, allow_client_receipt_overage: false, candidate_fingerprint: fingerprint }, batch_version: 1, canonical_fact_version: 7, alert_version: 3, preview_fingerprint: fingerprint };
    const accepted = { job_id: 'finance-correction-job-queued', status_url: '/api/v1/jobs/finance-correction-job-queued', replayed: false };
    vi.spyOn(financeImportCorrectionClient, 'preview').mockResolvedValue(preview);
    vi.spyOn(financeImportCorrectionClient, 'apply').mockResolvedValue(accepted);
    const outcome = vi.spyOn(financeImportCorrectionClient, 'queryOutcome')
      .mockResolvedValueOnce({ job_id: accepted.job_id, status: 'queued', attempt_count: 0, max_attempts: 3, result_reference: null, receipt: null })
      .mockResolvedValueOnce({ job_id: accepted.job_id, status: 'succeeded', attempt_count: 1, max_attempts: 3, result_reference: 'finance_import_correction:finance-import-row:42', receipt: { row_identity: 'finance-import-row:42', batch_identity: 'finance-import-batch:9', resulting_batch_version: 2, classification_event_count: 1, ledger_entry_count: 1, allocation_count: 1, reconciliation_receipt_count: 1, alert_resolved_event_count: 1, preview_fingerprint: fingerprint } });

    render(<AnomaliesPage />);
    await waitFor(() => expect(screen.getByText('假日排班尚未確認')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /查看處理方式 ➔/ }));
    await waitFor(() => expect(document.querySelector('[data-surface-id="anomalies.finance-correction"]')).not.toBeNull());
    fireEvent.change(document.querySelector('[data-control-id="anomalies.finance-correction.reason"]')!, { target: { value: '核對退匯' } });
    fireEvent.change(document.querySelector('[data-control-id="anomalies.finance-correction.evidence"]')!, { target: { value: 'receipt:42' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查更正影響' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '確認並提交更正' })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: '確認並提交更正' }));

    await waitFor(() => expect(screen.getByRole('button', { name: '重新查詢更正結果' })).toBeInTheDocument());
    expect(screen.queryByText('帳務更正完成')).not.toBeInTheDocument();
    expect(screen.getByText(/帳務更正尚未完成/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新查詢更正結果' }));
    await waitFor(() => expect(screen.getByText('帳務更正完成')).toBeInTheDocument());
    expect(outcome).toHaveBeenCalledTimes(2);
  });

  it('operator 在 Preview 等待期間修改輸入時必須作廢 stale response', async () => {
    const preview = { candidate: { row_identity: 'finance-import-row:42', batch_identity: 'finance-import-batch:9', classification_type: 'client_refund_return', owning_domain: 'client_finance', bank_amount_ntd: 100, allocations: [{ obligation_identity: 'obligation:SYNTH-19', amount_ntd: 100 }], reason: '核對退匯', evidence: ['receipt:42'], refund_ledger_entry_identity: 'ledger-refund:SYNTH-42', allow_partial_refund_recovery: false, allow_refund_overage_recovery: false, allow_client_receipt_overage: false, candidate_fingerprint: fingerprint }, batch_version: 1, canonical_fact_version: 7, alert_version: 3, preview_fingerprint: fingerprint };
    let resolvePreview!: (value: typeof preview) => void;
    const previewPromise = new Promise<typeof preview>((resolve) => { resolvePreview = resolve; });
    vi.spyOn(financeImportCorrectionClient, 'preview').mockReturnValue(previewPromise);

    render(<AnomaliesPage />);
    await waitFor(() => expect(screen.getByText('假日排班尚未確認')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /查看處理方式 ➔/ }));
    await waitFor(() => expect(document.querySelector('[data-surface-id="anomalies.finance-correction"]')).not.toBeNull());
    const reason = document.querySelector('[data-control-id="anomalies.finance-correction.reason"]')!;
    fireEvent.change(reason, { target: { value: '核對退匯' } });
    fireEvent.change(document.querySelector('[data-control-id="anomalies.finance-correction.evidence"]')!, { target: { value: 'receipt:42' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查更正影響' }));
    fireEvent.change(reason, { target: { value: '已更新核對理由' } });
    await act(async () => { resolvePreview(preview); await previewPromise; });

    expect(screen.getByRole('button', { name: '確認並提交更正' })).toBeDisabled();
    expect(screen.queryByText(/更正影響預覽/)).not.toBeInTheDocument();
  });

  it('未知 Finance correction action contract version 必須 fail closed', async () => {
    vi.spyOn(anomalyDetailClient, 'queryAnomalyRecovery').mockResolvedValue({
      ...correctionRecovery,
      available_actions: [{ ...correctionRecovery.available_actions[0], action_contract_version: 2 }],
    });

    render(<AnomaliesPage />);
    await waitFor(() => expect(screen.getByText('假日排班尚未確認')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /查看處理方式 ➔/ }));
    await waitFor(() => expect(screen.getByText(/沒有可直接使用的帳務更正表單/)).toBeInTheDocument());
    expect(document.querySelector('[data-surface-id="anomalies.finance-correction"]')).toBeNull();
  });
});
