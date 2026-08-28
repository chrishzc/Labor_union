/**
 * File: anomalies_finance_correction_flow.test.tsx
 * Description: 驗證異常 Drawer 僅對註冊 Finance correction action 執行 Preview、Apply 與 exact terminal oracle。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AnomaliesPage } from '../pages/AnomaliesPage';
import { anomalyQueryClient } from '../api/anomalies/anomaly_query_client';
import { anomalyDetailClient } from '../api/anomalies/anomaly_detail_client';
import { financeImportCorrectionClient, type FinanceImportCorrectionSelection } from '../api/finance_import/finance_import_correction_client';
import { VALID_ANOMALY_SUMMARY_1, VALID_IMPORT_WARNING_TASK_HCM } from './fixtures/anomalies/anomaly_query_contract_fixtures';
import { VALID_ANOMALY_DETAIL_VIEW, VALID_ANOMALY_RECOVERY_CONTEXT_VIEW } from './fixtures/anomalies/anomaly_detail_contract_fixtures';

const fingerprint = 'c'.repeat(64);
const selectedFingerprint = VALID_ANOMALY_SUMMARY_1.fingerprint;
const selectedDetail = {
  ...VALID_ANOMALY_DETAIL_VIEW,
  summary: { ...VALID_ANOMALY_DETAIL_VIEW.summary, fingerprint: selectedFingerprint },
};
const correctionRecovery = {
  ...VALID_ANOMALY_RECOVERY_CONTEXT_VIEW,
  fingerprint: selectedFingerprint,
  available_actions: [{
    action_key: 'classify_client_refund_return', label: '處理客戶退款退匯', owning_domain: 'finance_import',
    form_schema_key: 'finance_import.correction.v1', source_binding_keys: ['finance_import_row_identity', 'source_version'],
    source_bindings: [{ kind: 'identity' as const, key: 'finance_import_row_identity', value: 'finance-import-row:42' }, { kind: 'version' as const, key: 'source_version', value: 7 }],
    required_operator_inputs: ['evidence', 'reason', 'refund_ledger_entry_identity', 'target_obligation_identities'],
    preview_operation: 'PreviewCorrectAndPostClientRefundReturn', apply_operation: 'CorrectAndPostClientRefundReturn',
    required_capability: 'finance_import.correct_and_post', completion_predicate: 'client_refund_return_cleared', action_contract_version: 1, requires_preview: true,
  }],
};
const manualCorrectionClassifications = [
  'client_receipt', 'client_refund', 'client_refund_return',
  'client_subsidy_return', 'government_subsidy', 'staff_payout',
] as const;
const genericCorrectionRecovery = {
  ...correctionRecovery,
  available_actions: [{
    ...correctionRecovery.available_actions[0],
    action_key: 'classify_and_post_bank_row', label: '分類並正式入帳銀行流水',
    required_operator_inputs: ['classification_type', 'evidence', 'reason', 'target_obligation_identities'],
    preview_operation: 'PreviewCorrectAndPostFinanceImportRow', apply_operation: 'CorrectAndPostFinanceImportRow',
    completion_predicate: 'finance_import_manual_review_cleared',
  }],
};

const correctionPreview = {
  candidate: { row_identity: 'finance-import-row:42', batch_identity: 'finance-import-batch:9', classification_type: 'client_refund_return', owning_domain: 'client_finance', bank_amount_ntd: 100, allocations: [{ obligation_identity: 'obligation:SYNTH-19', amount_ntd: 100 }], reason: '核對退匯', evidence: ['receipt:42'], refund_ledger_entry_identity: 'ledger-refund:SYNTH-42', allow_partial_refund_recovery: false, allow_refund_overage_recovery: false, allow_client_receipt_overage: false, candidate_fingerprint: fingerprint },
  batch_version: 1, canonical_fact_version: 7, alert_version: 3, preview_fingerprint: fingerprint,
};
const accepted = { job_id: 'finance-correction-job-1', status_url: '/api/v1/jobs/finance-correction-job-1', replayed: false };
const succeededOutcome = {
  job_id: accepted.job_id, status: 'succeeded' as const, attempt_count: 1, max_attempts: 3,
  result_reference: 'finance_import_correction:finance-import-row:42',
  receipt: { row_identity: 'finance-import-row:42', batch_identity: 'finance-import-batch:9', resulting_batch_version: 2, classification_event_count: 1, ledger_entry_count: 1, allocation_count: 1, reconciliation_receipt_count: 1, alert_resolved_event_count: 1, preview_fingerprint: fingerprint },
};

function terminalDetail(predicateActive: boolean, detailFingerprint = selectedFingerprint) {
  return { ...selectedDetail, summary: { ...selectedDetail.summary, fingerprint: detailFingerprint, predicate_active: predicateActive } };
}

async function openAndPreview(classification?: FinanceImportCorrectionSelection['classification_type']) {
  render(<AnomaliesPage />);
  await waitFor(() => expect(screen.getByText('假日排班尚未確認')).toBeInTheDocument());
  fireEvent.click(screen.getByRole('button', { name: /查看處理方式 ➔/ }));
  await waitFor(() => expect(document.querySelector('[data-surface-id="anomalies.finance-correction"]')).not.toBeNull());
  if (classification) fireEvent.change(document.querySelector('[data-control-id="anomalies.finance-correction.classification"]')!, { target: { value: classification } });
  fireEvent.change(document.querySelector('[data-control-id="anomalies.finance-correction.reason"]')!, { target: { value: '核對退匯' } });
  fireEvent.change(document.querySelector('[data-control-id="anomalies.finance-correction.evidence"]')!, { target: { value: 'receipt:42' } });
  fireEvent.click(screen.getByRole('button', { name: '檢查更正影響' }));
  await waitFor(() => expect(screen.getByRole('button', { name: '確認並提交更正' })).not.toBeDisabled());
}

describe('Anomalies Finance Import correction flow', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(anomalyQueryClient, 'queryAnomalies').mockResolvedValue([VALID_ANOMALY_SUMMARY_1]);
    vi.spyOn(anomalyQueryClient, 'queryImportWarningTasks').mockResolvedValue([VALID_IMPORT_WARNING_TASK_HCM]);
    vi.spyOn(anomalyDetailClient, 'queryAnomalyDetail').mockResolvedValue(selectedDetail);
    vi.spyOn(anomalyDetailClient, 'queryAnomalyRecovery').mockResolvedValue(correctionRecovery);
  });

  it('receipt-only 或 predicate=true 只保持未完成，且 exact query 才是解除 oracle', async () => {
    const apply = vi.spyOn(financeImportCorrectionClient, 'apply').mockResolvedValue(accepted);
    vi.spyOn(financeImportCorrectionClient, 'preview').mockResolvedValue(correctionPreview);
    vi.spyOn(financeImportCorrectionClient, 'queryOutcome').mockResolvedValue(succeededOutcome);

    await openAndPreview();
    expect(document.querySelector('[data-control-id="anomalies.finance-correction.classification"]')).toBeDisabled();
    expect(document.querySelector('[data-control-id="anomalies.finance-correction.classification"]')).toHaveAttribute('aria-describedby', 'anomalies-correction-classification-reason');
    fireEvent.click(screen.getByRole('button', { name: '確認並提交更正' }));

    await waitFor(() => expect(screen.getByText('帳務更正已提交，來源異常仍待核對；根因條件仍成立，請以同一 job/root 重新查詢。')).toBeInTheDocument());
    expect(screen.queryByText('帳務更正完成')).not.toBeInTheDocument();
    expect(anomalyDetailClient.queryAnomalyDetail).toHaveBeenLastCalledWith({ fingerprint: selectedFingerprint });
    expect(anomalyQueryClient.queryAnomalies).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledTimes(1);
  });

  it('只有 exact detail predicate=false 且 active list refresh 成功才顯示完成', async () => {
    vi.mocked(anomalyDetailClient.queryAnomalyDetail).mockReset().mockResolvedValueOnce(selectedDetail).mockResolvedValueOnce(terminalDetail(false));
    const query = vi.mocked(anomalyQueryClient.queryAnomalies);
    query.mockReset().mockResolvedValueOnce([VALID_ANOMALY_SUMMARY_1]).mockResolvedValueOnce([]);
    vi.spyOn(financeImportCorrectionClient, 'preview').mockResolvedValue(correctionPreview);
    vi.spyOn(financeImportCorrectionClient, 'apply').mockResolvedValue(accepted);
    vi.spyOn(financeImportCorrectionClient, 'queryOutcome').mockResolvedValue(succeededOutcome);

    await openAndPreview();
    fireEvent.click(screen.getByRole('button', { name: '確認並提交更正' }));

    await waitFor(() => expect(screen.getByText('帳務更正完成')).toBeInTheDocument());
    expect(screen.queryByText('帳務更正已提交，來源異常仍待核對；根因條件仍成立，請以同一 job/root 重新查詢。')).not.toBeInTheDocument();
    expect(anomalyDetailClient.queryAnomalyDetail).toHaveBeenLastCalledWith({ fingerprint: selectedFingerprint });
    expect(query).toHaveBeenCalledTimes(2);
  });

  it('exact detail query failure 保持未完成，重查同一 job 且不重送 Apply', async () => {
    const detailQuery = vi.mocked(anomalyDetailClient.queryAnomalyDetail);
    detailQuery.mockReset().mockResolvedValueOnce(selectedDetail).mockRejectedValueOnce(new Error('exact anomaly detail unavailable')).mockResolvedValueOnce(terminalDetail(false));
    const query = vi.mocked(anomalyQueryClient.queryAnomalies);
    query.mockReset().mockResolvedValueOnce([VALID_ANOMALY_SUMMARY_1]).mockResolvedValueOnce([]);
    const apply = vi.spyOn(financeImportCorrectionClient, 'apply').mockResolvedValue(accepted);
    vi.spyOn(financeImportCorrectionClient, 'preview').mockResolvedValue(correctionPreview);
    const outcomeQuery = vi.spyOn(financeImportCorrectionClient, 'queryOutcome').mockResolvedValue(succeededOutcome);

    await openAndPreview();
    fireEvent.click(screen.getByRole('button', { name: '確認並提交更正' }));
    await waitFor(() => expect(screen.getByText('exact anomaly detail unavailable')).toBeInTheDocument());
    expect(screen.queryByText('帳務更正完成')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新查詢更正結果' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '重新查詢更正結果' }));
    await waitFor(() => expect(screen.getByText('帳務更正完成')).toBeInTheDocument());
    expect(outcomeQuery).toHaveBeenCalledTimes(2);
    expect(outcomeQuery).toHaveBeenNthCalledWith(2, accepted.job_id);
    expect(apply).toHaveBeenCalledTimes(1);
  });

  it('exact detail identity mismatch fail closed，保留同 job 重查入口', async () => {
    const detailQuery = vi.mocked(anomalyDetailClient.queryAnomalyDetail);
    detailQuery.mockReset().mockResolvedValueOnce(selectedDetail).mockResolvedValueOnce(terminalDetail(false, 'd'.repeat(64))).mockResolvedValueOnce(terminalDetail(false, 'd'.repeat(64)));
    const apply = vi.spyOn(financeImportCorrectionClient, 'apply').mockResolvedValue(accepted);
    vi.spyOn(financeImportCorrectionClient, 'preview').mockResolvedValue(correctionPreview);
    vi.spyOn(financeImportCorrectionClient, 'queryOutcome').mockResolvedValue(succeededOutcome);

    await openAndPreview();
    fireEvent.click(screen.getByRole('button', { name: '確認並提交更正' }));

    await waitFor(() => expect(screen.getByText('異常詳情與原 fingerprint 不一致，已停止完成判定；請以同一 job/root 重新查詢。')).toBeInTheDocument());
    expect(screen.queryByText('帳務更正完成')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新查詢更正結果' })).toBeInTheDocument();
    expect(anomalyQueryClient.queryAnomalies).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: '重新查詢更正結果' }));
    await waitFor(() => expect(screen.getByText('異常詳情與原 fingerprint 不一致，已停止完成判定；請以同一 job/root 重新查詢。')).toBeInTheDocument());
    expect(apply).toHaveBeenCalledTimes(1);
  });

  it('active list refresh failure fail closed，重查同一 job 後仍不重送 Apply', async () => {
    const detailQuery = vi.mocked(anomalyDetailClient.queryAnomalyDetail);
    detailQuery.mockReset().mockResolvedValueOnce(selectedDetail).mockResolvedValueOnce(terminalDetail(false)).mockResolvedValueOnce(terminalDetail(false));
    const query = vi.mocked(anomalyQueryClient.queryAnomalies);
    query.mockReset().mockResolvedValueOnce([VALID_ANOMALY_SUMMARY_1]).mockRejectedValueOnce(new Error('active list unavailable')).mockResolvedValueOnce([]);
    const apply = vi.spyOn(financeImportCorrectionClient, 'apply').mockResolvedValue(accepted);
    vi.spyOn(financeImportCorrectionClient, 'preview').mockResolvedValue(correctionPreview);
    const outcomeQuery = vi.spyOn(financeImportCorrectionClient, 'queryOutcome').mockResolvedValue(succeededOutcome);

    await openAndPreview();
    fireEvent.click(screen.getByRole('button', { name: '確認並提交更正' }));
    await waitFor(() => expect(screen.getByText('帳務更正已提交，來源異常仍待核對；最新異常清單查詢失敗，請以同一 job/root 重新查詢。')).toBeInTheDocument());
    expect(screen.queryByText('帳務更正完成')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新查詢更正結果' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '重新查詢更正結果' }));
    await waitFor(() => expect(screen.getByText('帳務更正完成')).toBeInTheDocument());
    expect(outcomeQuery).toHaveBeenCalledTimes(2);
    expect(apply).toHaveBeenCalledTimes(1);
  });

  it('queued outcome 必須保持未完成，直到同一 job re-query 取得 exact inactive detail', async () => {
    vi.mocked(anomalyDetailClient.queryAnomalyDetail).mockReset().mockResolvedValueOnce(selectedDetail).mockResolvedValueOnce(terminalDetail(false));
    const query = vi.mocked(anomalyQueryClient.queryAnomalies);
    query.mockReset().mockResolvedValueOnce([VALID_ANOMALY_SUMMARY_1]).mockResolvedValueOnce([]);
    vi.spyOn(financeImportCorrectionClient, 'preview').mockResolvedValue(correctionPreview);
    vi.spyOn(financeImportCorrectionClient, 'apply').mockResolvedValue(accepted);
    const outcomeQuery = vi.spyOn(financeImportCorrectionClient, 'queryOutcome')
      .mockResolvedValueOnce({ job_id: accepted.job_id, status: 'queued', attempt_count: 0, max_attempts: 3, result_reference: null, receipt: null })
      .mockResolvedValueOnce(succeededOutcome);

    await openAndPreview();
    fireEvent.click(screen.getByRole('button', { name: '確認並提交更正' }));
    await waitFor(() => expect(screen.getByText(/帳務更正尚未完成/)).toBeInTheDocument());
    expect(screen.queryByText('帳務更正完成')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新查詢更正結果' }));
    await waitFor(() => expect(screen.getByText('帳務更正完成')).toBeInTheDocument());
    expect(outcomeQuery).toHaveBeenCalledTimes(2);
  });

  it.each(['unknown', 'stale'] as const)('%s outcome fail closed 且不重送 Apply', async (status) => {
    const apply = vi.spyOn(financeImportCorrectionClient, 'apply').mockResolvedValue(accepted);
    vi.spyOn(financeImportCorrectionClient, 'preview').mockResolvedValue(correctionPreview);
    const outcomeQuery = vi.spyOn(financeImportCorrectionClient, 'queryOutcome').mockResolvedValue({ job_id: accepted.job_id, status, attempt_count: 0, max_attempts: 3, result_reference: null, receipt: null } as never);

    await openAndPreview();
    fireEvent.click(screen.getByRole('button', { name: '確認並提交更正' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '重新查詢更正結果' })).toBeInTheDocument());
    expect(screen.queryByText('帳務更正完成')).not.toBeInTheDocument();
    expect(outcomeQuery).toHaveBeenCalledWith(accepted.job_id);
    expect(apply).toHaveBeenCalledTimes(1);
  });

  it('operator 在 Preview 等待期間修改輸入時必須作廢 stale response', async () => {
    let resolvePreview!: (value: typeof correctionPreview) => void;
    const previewPromise = new Promise<typeof correctionPreview>((resolve) => { resolvePreview = resolve; });
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
    await act(async () => { resolvePreview(correctionPreview); await previewPromise; });

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

  it.each(manualCorrectionClassifications)('generic dispatcher preserves registered classification %s', async (classification) => {
    vi.mocked(anomalyDetailClient.queryAnomalyRecovery).mockResolvedValue(genericCorrectionRecovery);
    const preview = vi.spyOn(financeImportCorrectionClient, 'preview').mockImplementation(async (selection) => ({
      ...correctionPreview,
      candidate: { ...correctionPreview.candidate, classification_type: selection.classification_type },
    }));

    await openAndPreview(classification);

    const select = document.querySelector('[data-control-id="anomalies.finance-correction.classification"]') as HTMLSelectElement;
    expect(Array.from(select.options, (option) => option.value)).toEqual(manualCorrectionClassifications);
    expect(preview).toHaveBeenCalledWith(expect.objectContaining({ classification_type: classification }));
  });
});
