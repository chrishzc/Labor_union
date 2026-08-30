/**
 * File: anomalies_detail_referral_flow.test.tsx
 * Description: 驗證 lazy detail/referral GET、Drawer stale 與 deferred controls。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AnomaliesPage } from '../pages/AnomaliesPage';
import { anomalyQueryClient } from '../api/anomalies/anomaly_query_client';
import { anomalyDetailClient } from '../api/anomalies/anomaly_detail_client';
import { AnomalyDetailError } from '../api/anomalies/anomaly_detail_errors';
import { historicalReviewRemediationClient } from '../api/orders/historical_review_remediation/client';
import {
  VALID_ANOMALY_SUMMARY_1,
  VALID_IMPORT_WARNING_TASK_HCM,
  VALID_IMPORT_WARNING_REFERRAL_VIEW,
} from './fixtures/anomalies/anomaly_query_contract_fixtures';
import {
  VALID_ANOMALY_DETAIL_VIEW,
  VALID_ANOMALY_RECOVERY_CONTEXT_VIEW,
} from './fixtures/anomalies/anomaly_detail_contract_fixtures';

const ALIGNED_DETAIL = {
  ...VALID_ANOMALY_DETAIL_VIEW,
  summary: {
    ...VALID_ANOMALY_DETAIL_VIEW.summary,
    fingerprint: VALID_ANOMALY_SUMMARY_1.fingerprint,
    definition_code: VALID_ANOMALY_SUMMARY_1.definition_code,
    source_domain: VALID_ANOMALY_SUMMARY_1.source_domain,
    source_identity: VALID_ANOMALY_SUMMARY_1.source_identity,
    display_snapshot: {
      ...VALID_ANOMALY_DETAIL_VIEW.summary.display_snapshot,
      definition_code: VALID_ANOMALY_SUMMARY_1.definition_code,
    },
  },
};
const ALIGNED_RECOVERY = {
  ...VALID_ANOMALY_RECOVERY_CONTEXT_VIEW,
  definition_code: VALID_ANOMALY_SUMMARY_1.definition_code,
  subject: {
    ...VALID_ANOMALY_RECOVERY_CONTEXT_VIEW.subject,
    definition_code: VALID_ANOMALY_SUMMARY_1.definition_code,
  },
  details: {
    ...VALID_ANOMALY_RECOVERY_CONTEXT_VIEW.details,
    definition_code: VALID_ANOMALY_SUMMARY_1.definition_code,
  },
};

describe('Anomalies lazy Drawer query flow', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(anomalyQueryClient, 'queryAnomalies').mockResolvedValue([
      VALID_ANOMALY_SUMMARY_1,
    ]);
    vi.spyOn(anomalyQueryClient, 'queryImportWarningTasks').mockResolvedValue([
      VALID_IMPORT_WARNING_TASK_HCM,
    ]);
    vi.spyOn(anomalyDetailClient, 'queryAnomalyDetail').mockResolvedValue(
      ALIGNED_DETAIL
    );
    vi.spyOn(anomalyDetailClient, 'queryAnomalyRecovery').mockResolvedValue(
      ALIGNED_RECOVERY
    );
    vi.spyOn(anomalyQueryClient, 'queryImportWarningReferral').mockResolvedValue(
      VALID_IMPORT_WARNING_REFERRAL_VIEW
    );
    vi.spyOn(historicalReviewRemediationClient, 'query').mockResolvedValue({
      review_identity: 'historical-order-review:fixture',
      masked_case_identity: 'CA****01',
      issues: [{ issue_code: 'historical_status_invalid', field_path: 'status', field_label: '訂單狀態', masked_source_value: '9', masked_current_value: '1', rule: '狀態必須是 0、1 或 2', allowed_values: ['0', '1', '2'], process_blocker: '歷史訂單匯入待確認流程不能完成。' }],
      review_version: 0,
      remediation_version: 0,
      workbook_contract: { contract_key: 'orders.historical-review-correction', contract_version: 1, required_columns: ['case_no', 'client_name', 'status'], single_row_only: true, file_extension: 'xlsx' },
      reason_required: true,
      evidence_required: true,
      completion_condition: '更正來源合法採納，或由具體 successor review 接手原問題。',
      prior_alert_active: true,
    });
  });

  it('does not query detail until anomaly Drawer opens', async () => {
    render(<AnomaliesPage />);
    await waitFor(() => expect(screen.getByText('假日排班尚未確認')).toBeInTheDocument());
    expect(anomalyDetailClient.queryAnomalyDetail).not.toHaveBeenCalled();
    expect(anomalyDetailClient.queryAnomalyRecovery).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /查看處理方式 ➔/ }));
    await waitFor(() => expect(anomalyDetailClient.queryAnomalyDetail).toHaveBeenCalledTimes(1));
    expect(anomalyDetailClient.queryAnomalyRecovery).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/問題詳情/)).toBeInTheDocument();
    await waitFor(() => {
      expect(document.querySelector('[data-surface-id="anomalies.drawer.evidence"]')).toHaveTextContent('1200');
      expect(document.querySelector('[data-surface-id="anomalies.drawer.evidence"]')).not.toHaveTextContent('amount_delta_ntd');
      expect(screen.getByText(/預覽財務投影修復/)).toBeInTheDocument();
    });
  });

  it('queries warning referral lazily and keeps root repair disabled', async () => {
    render(<AnomaliesPage />);
    await waitFor(() => expect(screen.getByText('缺少身分證字號')).toBeInTheDocument());
    expect(anomalyQueryClient.queryImportWarningReferral).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '查看警示詳情' }));
    await waitFor(() => expect(anomalyQueryClient.queryImportWarningReferral).toHaveBeenCalledTimes(1));
    expect(screen.getByText('由負責流程檢查後修正')).toBeInTheDocument();
    expect(screen.getByText(/追蹤狀態不代表來源已修復/)).toBeVisible();
    expect(screen.queryByRole('button', { name: '請依上方轉介流程處理來源資料' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '開啟追蹤狀態變更' })).toBeEnabled();
  });

  it('distinguishes an unavailable owner repair flow from a backend outage', async () => {
    vi.mocked(anomalyQueryClient.queryImportWarningReferral).mockRejectedValue(
      new (await import('../api/anomalies/anomaly_query_errors')).AnomalyValidationError(
        '匯入警示指令無法完成。',
        [],
        'import_warning_referral_unavailable',
      ),
    );
    render(<AnomaliesPage />);
    await waitFor(() => expect(screen.getByText('缺少身分證字號')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '查看警示詳情' }));
    await waitFor(() => expect(screen.getByText('此警示尚未支援來源修復；可更新追蹤狀態，但不會修改來源根事實。')).toBeInTheDocument());
  });

  it('保留成功 detail，並將 recovery 404 限縮為局部錯誤', async () => {
    vi.mocked(anomalyDetailClient.queryAnomalyRecovery).mockRejectedValue(new AnomalyDetailError('NOT_FOUND', '找不到異常 recovery context。'));
    render(<AnomaliesPage />);
    await waitFor(() => expect(screen.getByText('假日排班尚未確認')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /查看處理方式 ➔/ }));
    await waitFor(() => expect(document.querySelector('[data-surface-id="anomalies.drawer.evidence"]')).toHaveTextContent('1200'));
    expect(document.querySelector('[data-surface-id="anomalies.drawer.evidence"]')).not.toHaveTextContent('amount_delta_ntd');
    expect(screen.getByText('目前沒有可用的系統處理方式，請交由對應業務負責人處理。')).toBeInTheDocument();
    expect(screen.queryByText('累計偵測次數')).not.toBeInTheDocument();
    expect(screen.getByText(/系統會自動重新核對異常/)).toBeVisible();
    expect(screen.queryByRole('button', { name: /確認排除異常/ })).not.toBeInTheDocument();
  });

  it('shows historical-order owner remediation without generic or Finance controls', async () => {
    const historicalSummary = {
      ...VALID_ANOMALY_SUMMARY_1,
      fingerprint: 'c'.repeat(64),
      definition_code: 'HISTORICAL-ORDER-001',
      source_domain: 'orders',
      source_identity: 'historical-order-review:fixture',
      severity: 'warning' as const,
    };
    vi.mocked(anomalyQueryClient.queryAnomalies).mockResolvedValue([historicalSummary]);
    vi.mocked(anomalyDetailClient.queryAnomalyDetail).mockResolvedValue({
      ...VALID_ANOMALY_DETAIL_VIEW,
      summary: {
        ...VALID_ANOMALY_DETAIL_VIEW.summary,
        fingerprint: historicalSummary.fingerprint,
        definition_code: historicalSummary.definition_code,
        source_domain: historicalSummary.source_domain,
        source_identity: historicalSummary.source_identity,
        severity: historicalSummary.severity,
      },
      available_actions: [],
    });
    vi.mocked(anomalyDetailClient.queryAnomalyRecovery).mockRejectedValue(
      new AnomalyDetailError('NOT_FOUND', '找不到異常 recovery context。'),
    );

    render(<AnomaliesPage />);
    await waitFor(() => expect(screen.getByText('歷史訂單匯入待人工確認')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '查看處理方式 ➔' }));

    await waitFor(() => expect(screen.getByRole('heading', { name: '歷史訂單欄位衝突更正' })).toBeInTheDocument());
    expect(screen.getByText(/狀態必須是 0、1 或 2/)).toBeInTheDocument();
    expect(screen.queryByText('目前沒有可用的系統處理方式，請交由對應業務負責人處理。')).not.toBeInTheDocument();
    expect(screen.queryByText('目前沒有可用的處理方式。')).not.toBeInTheDocument();
    expect(screen.queryByText('累計偵測次數')).not.toBeInTheDocument();
    expect(screen.queryByText('帳務資料更正')).not.toBeInTheDocument();
    expect(screen.queryByText(/沒有可直接使用的帳務更正表單/)).not.toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="anomalies.finance-correction"]')).toBeNull();
  });

  it('closing Drawer aborts the active request and does not leave a stale Drawer', async () => {
    let resolveDetail: ((value: typeof VALID_ANOMALY_DETAIL_VIEW) => void) | undefined;
    vi.mocked(anomalyDetailClient.queryAnomalyDetail).mockImplementation(
      () => new Promise((resolve) => { resolveDetail = resolve; })
    );
    render(<AnomaliesPage />);
    await waitFor(() => expect(screen.getByText('假日排班尚未確認')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /查看處理方式 ➔/ }));
    expect(screen.getByRole('heading', { name: /假日排班尚未確認/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));
    expect(screen.queryByRole('heading', { name: /假日排班尚未確認/ })).not.toBeInTheDocument();
    resolveDetail?.(VALID_ANOMALY_DETAIL_VIEW);
    await Promise.resolve();
    expect(screen.queryByText(/amount_delta_ntd/)).not.toBeInTheDocument();
  });
});
