/**
 * File: data_import_case_workbooks_preview_flow.test.tsx
 * Description: 驗證三個Case Workbook安全Apply鎖、冪等重試、負向receipt與控制狀態說明。
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { clientBeClassWorkbookPreviewClient } from '../api/case_import/client_beclass_workbook/client';
import { ClientBeClassWorkbookApplyError } from '../api/case_import/client_beclass_workbook/errors';
import { hcmImportResultClient } from '../api/case_import/hcm_import_result_client';
import { staffHistoricalWorkbookPreviewClient } from '../api/case_import/staff_historical_workbook/client';
import { historicalOrderWorkbookPreviewClient } from '../api/orders/historical_order_workbook/client';
import { historicalReviewRemediationClient } from '../api/orders/historical_review_remediation/client';
import type { HistoricalReviewContext } from '../api/orders/historical_review_remediation/schemas';
import { DataImportPage } from '../pages/DataImportPage';

const digest = 'a'.repeat(64);
const identity = 'b'.repeat(64);
const fingerprint = 'c'.repeat(64);
const historicalResultCounts = { not_adopted: 1, matching_pending_deposit: 1, historical_unserved: 1, historical_in_service: 1, historical_service_completed: 0 };
const historicalResultCountsOne = { not_adopted: 0, matching_pending_deposit: 0, historical_unserved: 1, historical_in_service: 0, historical_service_completed: 0 };

function workbook(contents: string, name = 'import.xlsx'): File {
  return new File([contents], name, { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
}

const historicalReviewContext: HistoricalReviewContext = {
  review_identity: 'historical-order-review:one',
  masked_case_identity: 'CA****01',
  issues: [],
  review_version: 0,
  remediation_version: 0,
  workbook_contract: {
    contract_key: 'orders.historical-review-correction',
    contract_version: 1,
    required_columns: ['case_no', 'client_name', 'status'],
    single_row_only: true as const,
    file_extension: 'xlsx',
  },
  reason_required: true,
  evidence_required: true,
  completion_condition: '更正來源合法採納。',
  prior_alert_active: true,
};

describe('Data Import case workbook Preview flows', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(hcmImportResultClient, 'query').mockResolvedValue({ items: [], next_cursor: null });
    vi.spyOn(clientBeClassWorkbookPreviewClient, 'preview').mockResolvedValue({ source_content_digest: digest, sheet_identity: identity, source_row_count: 4, create_count: 1, review_required_count: 1, existing_conflict_count: 1, existing_source_count: 1, preview_fingerprint: fingerprint });
    vi.spyOn(clientBeClassWorkbookPreviewClient, 'apply').mockResolvedValue({ source_content_digest: digest, source_row_count: 4, created_count: 1, exact_replay_count: 0, review_required_count: 1, existing_conflict_count: 1, existing_source_count: 1, replayed_workbook: false });
    vi.spyOn(staffHistoricalWorkbookPreviewClient, 'preview').mockResolvedValue({ source_content_digest: digest, source_row_count: 4, created_count: 1, adopted_existing_count: 1, blocked_identity_count: 1, identity_conflict_count: 1, review_required_count: 1, preview_fingerprint: fingerprint });
    vi.spyOn(staffHistoricalWorkbookPreviewClient, 'apply').mockResolvedValue({ source_content_digest: digest, source_row_count: 4, created_count: 1, adopted_existing_count: 1, blocked_identity_count: 1, identity_conflict_count: 1, review_required_count: 1, preview_fingerprint: fingerprint, exact_replay_count: 0, replayed_workbook: false });
    vi.spyOn(historicalOrderWorkbookPreviewClient, 'preview').mockResolvedValue({ source_content_digest: digest, sheet_identity: identity, source_row_count: 4, adopted_count: 2, unmatched_case_count: 1, review_required_count: 1, current_conflict_count: 1, assignment_candidate_count: 1, evidence_only_pairing_count: 1, status_counts: { cancelled_0: 1, deposit_paid_1: 1, discussion_2: 1, invalid_or_blank: 1 }, result_counts: historicalResultCounts, preview_fingerprint: fingerprint });
    vi.spyOn(historicalOrderWorkbookPreviewClient, 'apply').mockResolvedValue({ source_content_digest: digest, source_row_count: 4, adopted_count: 2, unmatched_case_count: 1, review_required_count: 1, current_conflict_count: 0, assignments_created: 1, replayed_rows: 0, replayed_workbook: false, status_counts: { cancelled_0: 1, deposit_paid_1: 1, discussion_2: 1, invalid_or_blank: 1 }, result_counts: historicalResultCounts, review_references: [] });
  });

  it('三張卡可獨立完成Preview、確認與Apply', async () => {
    render(<DataImportPage />);
    await waitFor(() => expect(hcmImportResultClient.query).toHaveBeenCalledTimes(1));

    const cases = [
      ['選擇客戶 BeClass Workbook', 'imports.client-beclass.preview', 'imports.client-beclass.preview-result'],
      ['選擇月嫂歷史 Workbook', 'imports.staff-historical.preview', 'imports.staff-historical.preview-result'],
      ['選擇歷史訂單 Workbook', 'imports.historic-orders.preview', 'imports.historic-orders.preview-result'],
    ] as const;
    for (const [label, controlId, surfaceId] of cases) {
      fireEvent.change(screen.getByLabelText(label), { target: { files: [workbook(label)] } });
      fireEvent.click(document.querySelector(`[data-control-id="${controlId}"]`) as HTMLButtonElement);
      await waitFor(() => expect(document.querySelector(`[data-surface-id="${surfaceId}"]`)).toBeInTheDocument());
      expect(within(document.querySelector(`[data-surface-id="${surfaceId}"]`) as HTMLElement).queryByText(fingerprint)).not.toBeInTheDocument();
      const card = document.querySelector(`[data-surface-id="imports.${controlId.split('.')[1]}.workbench"]`) as HTMLElement;
      const applyButton = document.querySelector(`[data-control-id="imports.${controlId.split('.')[1]}.apply"]`) as HTMLButtonElement;
      expect(applyButton).toBeDisabled();
      expect(within(card).getByText('請先勾選已核對檔案名稱與預覽筆數。')).toBeInTheDocument();
      fireEvent.click(within(card).getByLabelText('我已核對檔案名稱與預覽筆數'));
      expect(applyButton).toBeEnabled();
      expect(within(card).getByText('可以開始匯入；完成後會顯示結果。')).toBeInTheDocument();
      fireEvent.click(applyButton);
      await waitFor(() => expect(within(card).getByText('匯入完成，有資料需要檢查')).toBeInTheDocument());
    }

    expect(clientBeClassWorkbookPreviewClient.preview).toHaveBeenCalledTimes(1);
    expect(staffHistoricalWorkbookPreviewClient.preview).toHaveBeenCalledTimes(1);
    expect(historicalOrderWorkbookPreviewClient.preview).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(clientBeClassWorkbookPreviewClient.apply).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(staffHistoricalWorkbookPreviewClient.apply).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(historicalOrderWorkbookPreviewClient.apply).toHaveBeenCalledTimes(1));
    expect(screen.getAllByText('匯入完成，有資料需要檢查')).toHaveLength(3);
    expect(screen.getByText(/身分阻擋 1 筆、身分衝突 1 筆、需檢查 1 筆/)).toBeInTheDocument();
    expect(screen.getByText(/不採用 1 筆、配對中未付訂金 1 筆、已付訂金未服務 1 筆、歷史服務中 1 筆、歷史服務完成 0 筆/)).toBeInTheDocument();
    const historicalCard = document.querySelector('[data-surface-id="imports.historic-orders.workbench"]') as HTMLElement;
    for (const label of ['不採用', '配對中未付訂金', '已付訂金未服務', '歷史服務中', '歷史服務完成']) {
      expect(within(historicalCard).getByText(label)).toBeInTheDocument();
    }
    for (const id of ['client-beclass', 'staff-historical', 'historic-orders']) {
      const card = document.querySelector(`[data-surface-id="imports.${id}.workbench"]`) as HTMLElement;
      expect(document.querySelector(`[data-control-id="imports.${id}.apply"]`)).toBeDisabled();
      expect(within(card).getByText('匯入已完成，結果顯示於下方。')).toBeInTheDocument();
    }
  });

  it('Apply待定時鎖定換檔與頁內導覽，並以同一冪等識別安全重試', async () => {
    let rejectFirstApply: ((reason: unknown) => void) | undefined;
    vi.mocked(clientBeClassWorkbookPreviewClient.apply)
      .mockReturnValueOnce(new Promise((_, reject) => { rejectFirstApply = reject; }))
      .mockResolvedValueOnce({ source_content_digest: digest, source_row_count: 1, created_count: 1, exact_replay_count: 0, review_required_count: 0, existing_conflict_count: 0, existing_source_count: 0, replayed_workbook: false });
    render(<DataImportPage />);
    const input = screen.getByLabelText('選擇客戶 BeClass Workbook');
    const previewButton = document.querySelector('[data-control-id="imports.client-beclass.preview"]') as HTMLButtonElement;
    fireEvent.change(input, { target: { files: [workbook('pending')] } });
    fireEvent.click(previewButton);
    await waitFor(() => expect(clientBeClassWorkbookPreviewClient.preview).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByLabelText('我已核對檔案名稱與預覽筆數'));
    const applyButton = document.querySelector('[data-control-id="imports.client-beclass.apply"]') as HTMLButtonElement;
    fireEvent.click(applyButton);
    await waitFor(() => expect(clientBeClassWorkbookPreviewClient.apply).toHaveBeenCalledTimes(1));

    expect(input).toBeDisabled();
    expect(previewButton).toBeDisabled();
    expect(screen.getByText(/目前已鎖定換檔、預覽、站內導覽與重新整理/)).toBeInTheDocument();
    const navigation = document.createElement('button');
    navigation.className = 'sidebar-nav-item';
    const navigate = vi.fn();
    navigation.addEventListener('click', navigate);
    document.body.appendChild(navigation);
    fireEvent.click(navigation);
    expect(navigate).not.toHaveBeenCalled();
    navigation.remove();
    const unloadEvent = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(unloadEvent);
    expect(unloadEvent.defaultPrevented).toBe(true);

    rejectFirstApply?.(new ClientBeClassWorkbookApplyError('client_beclass_apply_timeout', '套用逾時，請重試。', true));
    await waitFor(() => expect(screen.getByText(/匯入結果尚未確認/)).toBeInTheDocument());
    expect(input).toBeDisabled();
    expect(previewButton).toBeDisabled();
    expect(applyButton).toBeEnabled();
    expect(applyButton).toHaveTextContent('查詢這次匯入結果');
    fireEvent.click(applyButton);
    await waitFor(() => expect(clientBeClassWorkbookPreviewClient.apply).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByText('匯入完成')).toBeInTheDocument());

    const firstOptions = vi.mocked(clientBeClassWorkbookPreviewClient.apply).mock.calls[0]?.[2];
    const secondOptions = vi.mocked(clientBeClassWorkbookPreviewClient.apply).mock.calls[1]?.[2];
    expect(firstOptions?.idempotencyKey).toBe(secondOptions?.idempotencyKey);
    expect(firstOptions?.signal).toBeUndefined();
    expect(secondOptions?.signal).toBeUndefined();
  });

  it('三類整份工作簿replay先標示未新增，原receipt統計僅供追溯', async () => {
    vi.mocked(clientBeClassWorkbookPreviewClient.apply).mockResolvedValueOnce({ source_content_digest: digest, source_row_count: 1, created_count: 1, exact_replay_count: 0, review_required_count: 0, existing_conflict_count: 0, existing_source_count: 0, replayed_workbook: true });
    vi.mocked(staffHistoricalWorkbookPreviewClient.apply).mockResolvedValueOnce({ source_content_digest: digest, source_row_count: 1, created_count: 1, adopted_existing_count: 0, blocked_identity_count: 0, identity_conflict_count: 0, review_required_count: 0, preview_fingerprint: fingerprint, exact_replay_count: 0, replayed_workbook: true });
    vi.mocked(historicalOrderWorkbookPreviewClient.apply).mockResolvedValueOnce({ source_content_digest: digest, source_row_count: 1, adopted_count: 1, unmatched_case_count: 0, review_required_count: 0, current_conflict_count: 0, assignments_created: 1, replayed_rows: 0, replayed_workbook: true, status_counts: { cancelled_0: 0, deposit_paid_1: 1, discussion_2: 0, invalid_or_blank: 0 }, result_counts: historicalResultCountsOne, review_references: [] });
    render(<DataImportPage />);

    const cases = [
      ['選擇客戶 BeClass Workbook', 'client-beclass'],
      ['選擇月嫂歷史 Workbook', 'staff-historical'],
      ['選擇歷史訂單 Workbook', 'historic-orders'],
    ] as const;
    for (const [label, id] of cases) {
      const card = document.querySelector(`[data-surface-id="imports.${id}.workbench"]`) as HTMLElement;
      fireEvent.change(screen.getByLabelText(label), { target: { files: [workbook(label)] } });
      fireEvent.click(document.querySelector(`[data-control-id="imports.${id}.preview"]`) as HTMLButtonElement);
      await waitFor(() => expect(within(card).getByText('預覽結果')).toBeInTheDocument());
      expect(within(card).queryByText(fingerprint)).not.toBeInTheDocument();
      fireEvent.click(within(card).getByLabelText('我已核對檔案名稱與預覽筆數'));
      fireEvent.click(document.querySelector(`[data-control-id="imports.${id}.apply"]`) as HTMLButtonElement);
      await waitFor(() => expect(within(card).getByText('這份工作簿已處理過，未重複匯入')).toBeInTheDocument());
      expect(within(card).getByText(/以下為上次處理結果/)).toBeInTheDocument();
    }
  });

  it('四類工作簿在尚未選檔時都說明Preview與Apply的下一步', async () => {
    render(<DataImportPage />);
    await waitFor(() => expect(hcmImportResultClient.query).toHaveBeenCalledTimes(1));

    for (const id of ['hcm-current', 'client-beclass', 'staff-historical', 'historic-orders']) {
      const workbench = document.querySelector(`[data-surface-id="imports.${id}.workbench"]`) as HTMLElement;
      expect(within(workbench).getByText('請先選擇 .xlsx 工作簿。')).toBeInTheDocument();
      expect(within(workbench).getByText('預覽成功後才能確認匯入。')).toBeInTheDocument();
    }
  });

  it('歷史訂單 receipt 直接開啟既有單列 review 更正，不導向異常中心', async () => {
    vi.mocked(historicalOrderWorkbookPreviewClient.apply).mockResolvedValueOnce({
      source_content_digest: digest,
      source_row_count: 1,
      adopted_count: 1,
      unmatched_case_count: 0,
      review_required_count: 1,
      current_conflict_count: 0,
      assignments_created: 0,
      replayed_rows: 0,
      replayed_workbook: false,
      status_counts: { cancelled_0: 0, deposit_paid_1: 1, discussion_2: 0, invalid_or_blank: 0 },
      result_counts: historicalResultCountsOne,
      review_references: ['historical-order-review:one'],
    });
    vi.spyOn(historicalReviewRemediationClient, 'query').mockResolvedValue(historicalReviewContext);
    render(<DataImportPage />);
    const card = document.querySelector('[data-surface-id="imports.historic-orders.workbench"]') as HTMLElement;
    fireEvent.change(screen.getByLabelText('選擇歷史訂單 Workbook'), { target: { files: [workbook('historical')] } });
    fireEvent.click(document.querySelector('[data-control-id="imports.historic-orders.preview"]') as HTMLButtonElement);
    await waitFor(() => expect(within(card).getByText('預覽結果')).toBeInTheDocument());
    fireEvent.click(within(card).getByLabelText('我已核對檔案名稱與預覽筆數'));
    fireEvent.click(document.querySelector('[data-control-id="imports.historic-orders.apply"]') as HTMLButtonElement);
    const remediation = await screen.findByRole('button', { name: '🛠️ 處理歷史訂單待確認 1' });
    fireEvent.click(remediation);

    await waitFor(() => expect(historicalReviewRemediationClient.query).toHaveBeenCalledWith('historical-order-review:one'));
    expect(await screen.findByText('歷史訂單欄位衝突更正')).toBeInTheDocument();
    expect(window.location.hash).not.toBe('#anomalies');
  });

  it('同檔名不同bytes會清除舊Preview並產生不同snapshot digest', async () => {
    render(<DataImportPage />);
    const input = screen.getByLabelText('選擇客戶 BeClass Workbook');
    const button = document.querySelector('[data-control-id="imports.client-beclass.preview"]') as HTMLButtonElement;
    fireEvent.change(input, { target: { files: [workbook('first')] } });
    fireEvent.click(button);
    await waitFor(() => expect(clientBeClassWorkbookPreviewClient.preview).toHaveBeenCalledTimes(1));
    fireEvent.change(input, { target: { files: [workbook('second')] } });
    expect(document.querySelector('[data-surface-id="imports.client-beclass.preview-result"]')).not.toBeInTheDocument();
    fireEvent.click(button);
    await waitFor(() => expect(clientBeClassWorkbookPreviewClient.preview).toHaveBeenCalledTimes(2));
    const first = vi.mocked(clientBeClassWorkbookPreviewClient.preview).mock.calls[0]?.[0];
    const second = vi.mocked(clientBeClassWorkbookPreviewClient.preview).mock.calls[1]?.[0];
    expect(first?.sha256).not.toBe(second?.sha256);
  });
});
