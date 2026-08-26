/**
 * File: anomalies_warning_transition_flow.test.tsx
 * Description: 驗證 Import Warning Preview、Apply、receipt 觀察與未明結果狀態機。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AnomaliesPage } from '../pages/AnomaliesPage';
import { anomalyQueryClient } from '../api/anomalies/anomaly_query_client';
import { anomalyDetailClient } from '../api/anomalies/anomaly_detail_client';
import {
  importWarningTransitionClient,
} from '../api/import_warning/import_warning_transition_client';
import { ImportWarningTransitionError } from '../api/import_warning/import_warning_transition_errors';
import type {
  WarningTransitionPreview,
  WarningTransitionReceipt,
} from '../api/import_warning/import_warning_transition_schemas';
import {
  VALID_IMPORT_WARNING_REFERRAL_VIEW,
  VALID_IMPORT_WARNING_TASK_HCM,
} from './fixtures/anomalies/anomaly_query_contract_fixtures';

const WARNING_ID = VALID_IMPORT_WARNING_TASK_HCM.occurrence_identity;
const RECEIPT_ID = 'b'.repeat(64);

const PREVIEW: WarningTransitionPreview = {
  occurrence_identity: WARNING_ID,
  expected_version: VALID_IMPORT_WARNING_TASK_HCM.tracking_version,
  resulting_status: 'awaiting_external_confirmation',
  resulting_version: VALID_IMPORT_WARNING_TASK_HCM.tracking_version + 1,
};

const RECEIPT: WarningTransitionReceipt = {
  occurrence_identity: WARNING_ID,
  before_status: 'open',
  after_status: 'awaiting_external_confirmation',
  resulting_version: VALID_IMPORT_WARNING_TASK_HCM.tracking_version + 1,
  receipt_identity: RECEIPT_ID,
  correlation_id: 'warning-flow-correlation-001',
  replayed: false,
};

function control(id: string): HTMLElement {
  const element = document.querySelector(`[data-control-id="${id}"]`);
  if (!(element instanceof HTMLElement)) throw new Error(`missing control: ${id}`);
  return element;
}

async function openWarningTransition(): Promise<void> {
  await waitFor(() => expect(screen.getByText('缺少身分證字號')).toBeInTheDocument());
  fireEvent.click(screen.getByRole('button', { name: '查看警示詳情' }));
  await waitFor(() => expect(anomalyQueryClient.queryImportWarningReferral).toHaveBeenCalledTimes(1));
  fireEvent.click(control('anomalies.import-warning.transition.open'));
}

async function enterReason(): Promise<void> {
  fireEvent.change(control('anomalies.import-warning.transition.reason'), {
    target: { value: 'source_confirmation_required' },
  });
}

function preparePage(): void {
  vi.spyOn(anomalyQueryClient, 'queryAnomalies').mockResolvedValue([]);
  vi.spyOn(anomalyQueryClient, 'queryImportWarningTasks').mockResolvedValue([
    VALID_IMPORT_WARNING_TASK_HCM,
  ]);
  vi.spyOn(anomalyQueryClient, 'queryImportWarningReferral').mockResolvedValue(
    VALID_IMPORT_WARNING_REFERRAL_VIEW,
  );
  vi.spyOn(anomalyDetailClient, 'queryAnomalyDetail').mockRejectedValue(new Error('not used'));
  vi.spyOn(anomalyDetailClient, 'queryAnomalyRecovery').mockRejectedValue(new Error('not used'));
  vi.spyOn(importWarningTransitionClient, 'preview').mockResolvedValue(PREVIEW);
  vi.spyOn(importWarningTransitionClient, 'apply').mockResolvedValue(RECEIPT);
  vi.spyOn(importWarningTransitionClient, 'queryReceipt').mockResolvedValue(RECEIPT);
}

describe('Anomalies Import Warning transition flow', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    preparePage();
  });

  it('runs Preview → Apply → authenticated receipt GET and renders observed state', async () => {
    render(<AnomaliesPage />);
    await openWarningTransition();

    for (const id of [
      'anomalies.import-warning.transition.action',
      'anomalies.import-warning.transition.reason',
      'anomalies.import-warning.transition.preview',
      'anomalies.import-warning.transition.apply',
    ]) {
      expect(control(id)).toBeInTheDocument();
    }
    expect(document.querySelector('[data-control-id="anomalies.import-warning.transition.open"]')).toBeNull();
    expect(control('anomalies.import-warning.transition.preview')).toHaveAttribute('aria-describedby', 'anomalies-warning-preview-reason');
    expect(screen.getByText('請先填寫處理說明，再檢查狀態變更影響。')).toBeInTheDocument();
    expect(control('anomalies.import-warning.transition.apply')).toHaveAttribute('aria-describedby', 'anomalies-warning-apply-reason');

    await enterReason();
    fireEvent.click(control('anomalies.import-warning.transition.preview'));
    await waitFor(() => expect(screen.getByText('狀態變更影響（尚未套用）')).toBeInTheDocument());

    fireEvent.click(control('anomalies.import-warning.transition.apply'));
    await waitFor(() => expect(screen.getByText(/已確認追蹤狀態變更完成/)).toBeInTheDocument());

    expect(importWarningTransitionClient.preview).toHaveBeenCalledTimes(1);
    expect(importWarningTransitionClient.apply).toHaveBeenCalledTimes(1);
    expect(importWarningTransitionClient.queryReceipt).toHaveBeenCalledTimes(1);
    expect(importWarningTransitionClient.queryReceipt).toHaveBeenCalledWith(
      RECEIPT_ID,
      expect.objectContaining({ correlationId: expect.any(String) }),
    );
    expect(screen.queryByText('來源已修復')).not.toBeInTheDocument();
  });

  it('invalidates Preview when the edited reason changes', async () => {
    render(<AnomaliesPage />);
    await openWarningTransition();
    await enterReason();
    fireEvent.click(control('anomalies.import-warning.transition.preview'));
    await waitFor(() => expect(screen.getByText('狀態變更影響（尚未套用）')).toBeInTheDocument());

    fireEvent.change(control('anomalies.import-warning.transition.reason'), {
      target: { value: 'changed_reason' },
    });

    expect(screen.queryByText('狀態變更影響（尚未套用）')).not.toBeInTheDocument();
    expect(control('anomalies.import-warning.transition.apply')).toBeDisabled();
    expect(importWarningTransitionClient.apply).not.toHaveBeenCalled();
  });

  it('keeps the exact payload and idempotency key for outcome_unknown retry', async () => {
    const apply = vi.mocked(importWarningTransitionClient.apply);
    apply
      .mockRejectedValueOnce(new ImportWarningTransitionError(
        'IMPORT_WARNING_OUTCOME_UNKNOWN',
        'Apply 結果未明',
        { outcomeUnknown: true, retryable: true },
      ))
      .mockResolvedValueOnce(RECEIPT);

    render(<AnomaliesPage />);
    await openWarningTransition();
    await enterReason();
    fireEvent.click(control('anomalies.import-warning.transition.preview'));
    await waitFor(() => expect(screen.getByText('狀態變更影響（尚未套用）')).toBeInTheDocument());
    fireEvent.click(control('anomalies.import-warning.transition.apply'));

    await waitFor(() => expect(screen.getByText(/變更結果尚未確認；系統已保留本次提交內容/)).toBeInTheDocument());
    expect(control('anomalies.import-warning.transition.retry')).toBeInTheDocument();
    expect(control('anomalies.import-warning.transition.action')).toBeDisabled();
    expect(control('anomalies.import-warning.transition.reason')).toBeDisabled();
    expect(document.querySelector('.drawer-close-btn')).toHaveProperty('disabled', true);

    fireEvent.click(control('anomalies.import-warning.transition.retry'));
    await waitFor(() => expect(screen.getByText(/已確認追蹤狀態變更完成/)).toBeInTheDocument());

    expect(apply).toHaveBeenCalledTimes(2);
    expect(apply.mock.calls[1]?.[0]).toBe(apply.mock.calls[0]?.[0]);
    expect(apply.mock.calls[1]?.[1]).toEqual(apply.mock.calls[0]?.[1]);
    expect(apply.mock.calls[1]?.[2].idempotencyKey).toBe(apply.mock.calls[0]?.[2].idempotencyKey);
  });

  it('keeps receipt after observation_failed and observe retry performs GET only', async () => {
    const queryReceipt = vi.mocked(importWarningTransitionClient.queryReceipt);
    queryReceipt
      .mockRejectedValueOnce(new Error('receipt observation unavailable'))
      .mockResolvedValueOnce(RECEIPT);

    render(<AnomaliesPage />);
    await openWarningTransition();
    await enterReason();
    fireEvent.click(control('anomalies.import-warning.transition.preview'));
    await waitFor(() => expect(screen.getByText('狀態變更影響（尚未套用）')).toBeInTheDocument());
    fireEvent.click(control('anomalies.import-warning.transition.apply'));

    await waitFor(() => expect(screen.getByText(/狀態變更已受理，但結果查詢失敗/)).toBeInTheDocument());
    expect(screen.queryByText(RECEIPT_ID)).not.toBeInTheDocument();
    expect(control('anomalies.import-warning.transition.observe')).toBeInTheDocument();
    expect(importWarningTransitionClient.apply).toHaveBeenCalledTimes(1);

    fireEvent.click(control('anomalies.import-warning.transition.observe'));
    await waitFor(() => expect(screen.getByText(/已確認追蹤狀態變更完成/)).toBeInTheDocument());
    expect(importWarningTransitionClient.apply).toHaveBeenCalledTimes(1);
    expect(queryReceipt).toHaveBeenCalledTimes(2);
  });

  it('does not Apply after a stale 409 Preview error', async () => {
    vi.mocked(importWarningTransitionClient.preview).mockRejectedValueOnce(
      new ImportWarningTransitionError('IMPORT_WARNING_STALE', '版本已變更', { status: 409 }),
    );

    render(<AnomaliesPage />);
    await openWarningTransition();
    await enterReason();
    fireEvent.click(control('anomalies.import-warning.transition.preview'));

    await waitFor(() => expect(screen.getByText(/資料已更新；系統已重新查詢清單/)).toBeInTheDocument());
    expect(importWarningTransitionClient.apply).not.toHaveBeenCalled();
    expect(screen.queryByText('狀態變更影響（尚未套用）')).not.toBeInTheDocument();
  });
});
