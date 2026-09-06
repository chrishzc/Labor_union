from pathlib import Path

PAGE = Path("ui_react/src/pages/FinancePage.tsx")
TEST = Path("ui_react/src/tests/finance_source_review_list.test.tsx")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, got {count}")
    return text.replace(old, new, 1)


text = PAGE.read_text(encoding="utf-8")
text = replace_once(
    text,
    "import { FinanceWorkbookSnapshot, financeImportMutationClient, type FinanceImportBatchOutcome, type FinanceImportBatchPreview, type FinanceImportJobAccepted, type FinanceWorkbookIngestionReceipt } from '../api/finance_import/finance_import_mutation_client';\n",
    "import { FinanceWorkbookSnapshot, financeImportMutationClient, type FinanceImportBatchOutcome, type FinanceImportBatchPreview, type FinanceImportJobAccepted, type FinanceWorkbookIngestionReceipt } from '../api/finance_import/finance_import_mutation_client';\nimport { financeImportQueryClient } from '../api/finance_import/finance_import_query_client';\n",
    "query client import",
)
text = replace_once(
    text,
    "type LoadState<T> = { kind: 'idle' | 'loading' } | { kind: 'ready'; data: T } | { kind: 'empty' } | { kind: 'error'; message: string } | { kind: 'unavailable'; message: string };\n",
    "type LoadState<T> = { kind: 'idle' | 'loading' } | { kind: 'ready'; data: T } | { kind: 'empty' } | { kind: 'error'; message: string } | { kind: 'unavailable'; message: string };\ntype FinanceImportReviewSnapshot = {\n  batchIdentity: string;\n  reviewCount: number;\n  items: Awaited<ReturnType<typeof financeImportQueryClient.listReviewRows>>['items'];\n};\n",
    "review snapshot type",
)
text = replace_once(
    text,
    "  const [batchPreview, setBatchPreview] = useState<LoadState<FinanceImportBatchPreview>>({ kind: 'idle' });\n",
    "  const [batchPreview, setBatchPreview] = useState<LoadState<FinanceImportBatchPreview>>({ kind: 'idle' });\n  const [sourceReview, setSourceReview] = useState<LoadState<FinanceImportReviewSnapshot>>({ kind: 'idle' });\n",
    "review state",
)
anchor = "  const ingestWorkbook = async () => {\n"
loader = """  const loadSourceReview = async (batchIdentity: string) => {
    const request = start('source-review');
    setSourceReview({ kind: 'loading' });
    try {
      const [manifest, page] = await Promise.all([
        financeImportQueryClient.getManifest(batchIdentity, { signal: request.controller.signal }),
        financeImportQueryClient.listReviewRows(batchIdentity, { signal: request.controller.signal }),
      ]);
      if (!current('source-review', request.sequence, request.controller)) return;
      if (page.next_after_row_id !== null || page.items.length !== manifest.review_count) {
        setSourceReview({ kind: 'error', message: '人工確認清單與批次統計不一致，請重新查詢。' });
        return;
      }
      setSourceReview({
        kind: 'ready',
        data: { batchIdentity: manifest.batch_identity, reviewCount: manifest.review_count, items: page.items },
      });
    } catch (error) {
      if (current('source-review', request.sequence, request.controller)) {
        setSourceReview({ kind: 'error', message: financeErrorMessage(error, '人工確認清單載入失敗，請重新查詢。') });
      }
    }
  };

"""
text = replace_once(text, anchor, loader + anchor, "review loader")
text = replace_once(
    text,
    "    setIngestion({ kind: 'loading' }); setBatchPreview({ kind: 'idle' }); setApplyConfirmed(false); setApplyJob({ kind: 'idle' }); setBatchOutcome({ kind: 'idle' });\n",
    "    setIngestion({ kind: 'loading' }); setBatchPreview({ kind: 'idle' }); setSourceReview({ kind: 'idle' }); setApplyConfirmed(false); setApplyJob({ kind: 'idle' }); setBatchOutcome({ kind: 'idle' });\n",
    "ingest reset",
)
text = replace_once(
    text,
    "    setBatchPreview({ kind: 'loading' }); setApplyConfirmed(false); setApplyJob({ kind: 'idle' }); setBatchOutcome({ kind: 'idle' });\n    try { setBatchPreview({ kind: 'ready', data: await financeImportMutationClient.preview(ingestion.data.batch_identity) }); }\n",
    "    setBatchPreview({ kind: 'loading' }); setSourceReview({ kind: 'idle' }); setApplyConfirmed(false); setApplyJob({ kind: 'idle' }); setBatchOutcome({ kind: 'idle' });\n    try {\n      const preview = await financeImportMutationClient.preview(ingestion.data.batch_identity);\n      setBatchPreview({ kind: 'ready', data: preview });\n      await loadSourceReview(preview.batch_identity);\n    }\n",
    "preview review load",
)
text = replace_once(
    text,
    "                  setBatchPreview({ kind: 'idle' });\n                  setApplyJob({ kind: 'idle' });\n",
    "                  setBatchPreview({ kind: 'idle' });\n                  setSourceReview({ kind: 'idle' });\n                  setApplyJob({ kind: 'idle' });\n",
    "file change reset",
)
text = replace_once(
    text,
    "                    <span className=\"finance-kpi-value orange\">{batchPreview.data.counts.manual_review}</span>\n",
    "                    <span className=\"finance-kpi-value orange\">{sourceReview.kind === 'ready' ? sourceReview.data.reviewCount : '—'}</span>\n",
    "manual review KPI",
)
text = replace_once(
    text,
    "                  可自動入帳 {batchPreview.data.counts.ready_dispatch}｜已存在 {batchPreview.data.counts.existing}｜待人工確認 {batchPreview.data.counts.manual_review}｜待業務配對 {batchPreview.data.counts.business_pending}｜阻擋 {batchPreview.data.counts.blocked}。\n",
    "                  可自動入帳 {batchPreview.data.counts.ready_dispatch}｜已存在 {batchPreview.data.counts.existing}｜待人工確認 {sourceReview.kind === 'ready' ? sourceReview.data.reviewCount : '讀取中'}｜待業務配對 {batchPreview.data.counts.business_pending}｜阻擋 {batchPreview.data.counts.blocked}。\n",
    "manual review scope note",
)
review_block_anchor = """                </div>\n\n                {batchPreview.data.apply_allowed && batchPreview.data.counts.ready_dispatch > 0 && (\n"""
review_block = """                </div>

                <StateMessage state={sourceReview} empty="目前沒有待人工確認資料。" />
                {sourceReview.kind === 'ready' && (
                  <div className="finance-detail-block" data-surface-id="finance.finance-import.manual-review" style={{ marginTop: '12px' }}>
                    <div className="finance-meta">
                      <span>批次 <code>{sourceReview.data.batchIdentity}</code>｜待人工確認 {sourceReview.data.reviewCount} 筆</span>
                      <button
                        className="finance-btn-secondary"
                        data-control-id="finance.finance-import.review-reload"
                        onClick={() => void loadSourceReview(sourceReview.data.batchIdentity)}
                      >
                        重新查詢人工確認
                      </button>
                    </div>
                    {sourceReview.data.reviewCount === 0 ? (
                      <div className="finance-state">目前沒有待人工確認資料。</div>
                    ) : (
                      <div className="finance-table-container">
                        <table className="finance-table">
                          <thead>
                            <tr>
                              <th>來源列</th>
                              <th>交易日期</th>
                              <th>方向</th>
                              <th>金額</th>
                              <th>分類</th>
                              <th>處置</th>
                            </tr>
                          </thead>
                          <tbody>
                            {sourceReview.data.items.map((row) => (
                              <tr key={row.row_id}>
                                <td><code>{row.source_sheet}#{row.source_row}</code></td>
                                <td>{row.transaction_date ?? '—'}</td>
                                <td>{row.direction}</td>
                                <td><strong>{row.amount_ntd}</strong></td>
                                <td>{row.classification_type}</td>
                                <td>{row.disposition}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}

                {sourceReview.kind === 'error' && (
                  <button
                    className="finance-btn-secondary"
                    style={{ marginTop: '10px' }}
                    data-control-id="finance.finance-import.review-reload"
                    onClick={() => void loadSourceReview(batchPreview.data.batch_identity)}
                  >
                    重新查詢人工確認
                  </button>
                )}

                {batchPreview.data.apply_allowed && batchPreview.data.counts.ready_dispatch > 0 && (
"""
text = replace_once(text, review_block_anchor, review_block, "review block")
PAGE.write_text(text, encoding="utf-8")

TEST.write_text(r'''/**
 * File: finance_source_review_list.test.tsx
 * Description: 驗證 Finance Import Preview 的人工確認 KPI、清單與 batch identity 共用 owner readback。
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
    vi.spyOn(financeImportMutationClient, 'preview').mockResolvedValue(PREVIEW);
    vi.spyOn(financeImportMutationClient, 'apply');
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

    expect(await screen.findByText('ROW-REVIEW-222')).toBeInTheDocument();
    const manualReviewKpi = screen.getByText('待人工確認', { selector: '.finance-kpi-label' }).parentElement;
    expect(manualReviewKpi?.querySelector('.finance-kpi-value')?.textContent).toBe('1');
    expect(screen.getByText(/批次/).parentElement).toHaveTextContent(BATCH);
    expect(screen.getByText('Sheet1#3')).toBeInTheDocument();
    expect(financeImportMutationClient.apply).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '重新查詢人工確認' }));
    await waitFor(() => expect(financeImportQueryClient.getManifest).toHaveBeenCalledTimes(2));
    expect(financeImportQueryClient.listReviewRows).toHaveBeenCalledTimes(2);
    expect(manualReviewKpi?.querySelector('.finance-kpi-value')?.textContent).toBe('1');
    expect(screen.getByText('ROW-REVIEW-222')).toBeInTheDocument();
  });
});
''', encoding="utf-8")
