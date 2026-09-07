/**
 * File: finance_source_review_list.test.tsx
 * Description: 驗證 Finance Import Preview 的人工確認 KPI、清單與 batch identity 共用 owner readback。
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { financeImportMutationClient, type FinanceImportBatchPreview } from '../api/finance_import/finance_import_mutation_client';
import { financeImportQueryClient } from '../api/finance_import/finance_import_query_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { FinancePage } from '../pages/FinancePage';

const BATCH = 'BATCH-REVIEW-222';
const PREVIEW: FinanceImportBatchPreview = {
  batch_identity: BATCH,
  batch_version: 7,
  source_content_digest: 'a'.repeat(64),
  classifier_version: 'v1',
  fingerprint_version: 'v1',
  counts: {
    source_rows: 2,
    canonical_created: 1,
    duplicate_occurrences: 0,
    ready_dispatch: 1,
    existing: 0,
    manual_review: 0,
    business_pending: 0,
    blocked: 0,
  },
  dispatch_summaries: [],
  rows: [],
  blocking_codes: [],
  apply_allowed: true,
  preview_fingerprint: 'b'.repeat(64),
};

const MANIFEST = {
  batch_id: 222,
  batch_identity: BATCH,
  format_id: 'fixture',
  source_file: 'finance.xlsx',
  sheet_name: 'Sheet1',
  header_row: 1,
  source_row_count: 2,
  status: 'previewed',
  batch_version: 7,
  source_content_digest: 'a'.repeat(64),
  classifier_version: 'v1',
  fingerprint_version: 'v1',
  canonical_row_count: 1,
  occurrence_count: 2,
  review_count: 1,
  dispatch_event_count: 0,
  reconciliation_receipt_count: 0,
  created_at: '2026-09-07T00:00:00+08:00',
  completed_at: null,
};

const REVIEW_PAGE = {
  batch_identity: BATCH,
  source_reviews: [] as { review_id: number; review_identity: string; source_sheet: string; source_row: number; issue_codes: string[]; created_at: string }[],
  next_after_source_review_id: null as number | null,
  items: [{
    row_id: 301,
    row_identity: 'ROW-REVIEW-222',
    transaction_date: '2026-09-01',
    direction: 'credit',
    amount_ntd: 5000,
    classification_type: 'client_receipt',
    disposition: 'manual_review',
    reconciliation_status: 'unmatched',
    source_sheet: 'Sheet1',
    source_row: 3,
    occurrence_count: 1,
    available_actions: [],
    created_at: '2026-09-07T00:00:00+08:00',
  }],
  next_after_row_id: null,
};

async function showPreview() {
  render(<FinancePage />);
  fireEvent.click(screen.getByRole('button', { name: '銀行流水匯入' }));
  fireEvent.change(screen.getByLabelText('選擇銀行流水工作簿'), { target: { files: [new File(['finance-review'], 'finance.xlsx')] } });
  fireEvent.click(screen.getByRole('button', { name: '上傳檔案' }));
  await waitFor(() => expect(screen.getByRole('button', { name: '預覽匯入結果' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: '預覽匯入結果' }));
  await screen.findByText('可自動入帳', { selector: '.finance-kpi-label' });
}
function reviewCount() {
  return screen.getByText('待人工確認', { selector: '.finance-kpi-label' }).parentElement?.querySelector('.finance-kpi-value')?.textContent;
}

describe('Finance source-review owner readback', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.setSession('finance-review-test-session', {
      id: 7,
      username: 'finance-review',
      display_name: 'Finance Review',
      role: 'admin',
    });
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({ items: [], next_cursor: null, etag: 'c'.repeat(64) });
    vi.spyOn(financeImportMutationClient, 'ingest').mockResolvedValue({
      batch_identity: BATCH,
      source_content_digest: 'a'.repeat(64),
      source_row_count: 2,
      canonical_created_count: 1,
      duplicate_occurrence_count: 0,
      source_warning_count: 1,
      source_warning_created_count: 1,
      replayed: false,
    });
    vi.spyOn(financeImportMutationClient, 'preview').mockResolvedValue(structuredClone(PREVIEW));
    vi.spyOn(financeImportMutationClient, 'apply').mockResolvedValue({ job_id: 'review-job', status_url: '/api/v1/jobs/review-job', replayed: false });
    vi.spyOn(financeImportMutationClient, 'queryBatchOutcome').mockResolvedValue({ job_id: 'review-job', status: 'succeeded', attempt_count: 1, max_attempts: 1, result_reference: 'finance_import_batch:fixture', receipt: { batch_identity: BATCH, resulting_batch_version: 8, preview_fingerprint: PREVIEW.preview_fingerprint, reconciled_count: 1, existing_count: 0, pending_count: 1 } });
    vi.spyOn(financeImportQueryClient, 'getManifest').mockResolvedValue(MANIFEST);
    vi.spyOn(financeImportQueryClient, 'listReviewRows').mockResolvedValue(REVIEW_PAGE);
  });

  afterEach(() => {
    cleanup();
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('settles manual-review KPI and list from the same batch owner fact and supports a consistent re-query', async () => {
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行流水匯入' }));

    const file = new File(['finance-review'], 'finance.xlsx');
    fireEvent.change(screen.getByLabelText('選擇銀行流水工作簿'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: '上傳檔案' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '預覽匯入結果' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '預覽匯入結果' }));

    expect(await screen.findByText(BATCH)).toBeInTheDocument();
    const manualReviewKpi = screen.getByText('待人工確認', { selector: '.finance-kpi-label' }).parentElement;
    expect(manualReviewKpi?.querySelector('.finance-kpi-value')?.textContent).toBe('1');
    expect(screen.getByText(/批次/).parentElement).toHaveTextContent(BATCH);
    expect(screen.getByText('Sheet1#3')).toBeInTheDocument();
    expect(financeImportMutationClient.apply).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '重新查詢人工確認' }));
    await waitFor(() => expect(financeImportQueryClient.getManifest).toHaveBeenCalledTimes(2));
    expect(financeImportQueryClient.listReviewRows).toHaveBeenCalledTimes(2);
    expect(manualReviewKpi?.querySelector('.finance-kpi-value')?.textContent).toBe('1');
    expect(screen.getByText('Sheet1#3')).toBeInTheDocument();
  });

  it('paginates a full review page instead of treating its cursor as an inconsistency', async () => {
    const rows = Array.from({ length: 51 }, (_, i) => ({ ...REVIEW_PAGE.items[0], row_id: i + 1, row_identity: `row-${i + 1}`, source_row: i + 1 }));
    vi.mocked(financeImportQueryClient.getManifest).mockResolvedValue({ ...MANIFEST, review_count: 51 });
    vi.mocked(financeImportQueryClient.listReviewRows)
      .mockResolvedValueOnce({ ...REVIEW_PAGE, items: rows.slice(0, 50), next_after_row_id: 50 })
      .mockResolvedValueOnce({ ...REVIEW_PAGE, items: rows.slice(50) });
    await showPreview();
    await waitFor(() => expect(reviewCount()).toBe('51'));
    expect(screen.getByText('Sheet1#51')).toBeInTheDocument();
    expect(financeImportQueryClient.listReviewRows).toHaveBeenLastCalledWith(BATCH, expect.objectContaining({ afterRowId: 50 }));
  });

  it('shows source-only review identity and reason without inventing bank fields or counting business pending as manual', async () => {
    vi.mocked(financeImportQueryClient.getManifest).mockResolvedValue({ ...MANIFEST, review_count: 2 });
    vi.mocked(financeImportQueryClient.listReviewRows).mockResolvedValue({
      ...REVIEW_PAGE,
      items: [{ ...REVIEW_PAGE.items[0], disposition: 'business_pending' }],
      source_reviews: [{ review_id: 11, review_identity: 'source-review-11', source_sheet: '交易明細', source_row: 4, issue_codes: ['invalid:transaction_amount'], created_at: MANIFEST.created_at }],
    });
    await showPreview();
    await waitFor(() => expect(reviewCount()).toBe('1'));
    expect(screen.getByText('交易明細#4')).toBeInTheDocument();
    expect(screen.getByText('invalid:transaction_amount')).toBeInTheDocument();
    expect(screen.queryByText('Sheet1#3')).not.toBeInTheDocument();
    expect(financeImportMutationClient.apply).not.toHaveBeenCalled();
  });

  it.each(['blocked', 'no-ready-rows'] as const)('enforces %s at the Apply handler even when the rendered button is stale', async (policy) => {
    const preview = structuredClone(PREVIEW);
    vi.mocked(financeImportMutationClient.preview).mockResolvedValue(preview);
    await showPreview();
    await waitFor(() => expect(reviewCount()).toBe('1'));
    fireEvent.click(screen.getByRole('checkbox'));
    if (policy === 'blocked') preview.apply_allowed = false;
    else preview.counts.ready_dispatch = 0;
    fireEvent.click(screen.getByRole('button', { name: '確認匯入' }));
    expect(financeImportMutationClient.apply).not.toHaveBeenCalled();
  });

  it('refreshes owner review after terminal Apply and keeps its source row visible', async () => {
    await showPreview();
    await waitFor(() => expect(reviewCount()).toBe('1'));
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '確認匯入' }));
    await screen.findByText('匯入完成：核銷 1、既有 0、待處理 1');
    await waitFor(() => expect(financeImportQueryClient.listReviewRows).toHaveBeenCalledTimes(2));
    expect(reviewCount()).toBe('1');
    expect(screen.getByText('Sheet1#3')).toBeInTheDocument();
  });

  it('does not restore an old preview after another workbook is selected', async () => {
    let resolve!: (value: FinanceImportBatchPreview) => void;
    vi.mocked(financeImportMutationClient.preview).mockReturnValue(new Promise((done) => { resolve = done; }));
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '銀行流水匯入' }));
    const input = screen.getByLabelText('選擇銀行流水工作簿');
    fireEvent.change(input, { target: { files: [new File(['first'], 'first.xlsx')] } });
    fireEvent.click(screen.getByRole('button', { name: '上傳檔案' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '預覽匯入結果' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '預覽匯入結果' }));
    fireEvent.change(input, { target: { files: [new File(['second'], 'second.xlsx')] } });
    await act(async () => { resolve(PREVIEW); });
    expect(screen.queryByText('可自動入帳', { selector: '.finance-kpi-label' })).not.toBeInTheDocument();
    expect(financeImportQueryClient.listReviewRows).not.toHaveBeenCalled();
  });
});
