/**
 * File: finance_import_query_adapter.ts
 * Description: 將Finance Import query映射為loaded-scope唯讀view且保留server status字串。
 */
import type { FinanceImportBatchSummary, FinanceImportManifest, FinanceImportReviewPage, FinanceImportRunPage } from '../../api/finance_import/finance_import_query_schemas';
const FINANCE_IMPORT_BLOCKER_LABELS: Readonly<Record<string, string>> = {
  batch_not_completed: '檔案尚未完成解析',
  occurrence_count_mismatch: '讀取筆數與可核對筆數不一致',
  fingerprint_collision: '存在可能重複的銀行交易',
  formal_reference_conflict: '正式參考資料互相衝突',
};
export function financeImportBlockerMessage(codes: readonly string[]): string {
  if (codes.length === 0) return '預覽未通過，請重新檢查。';
  const labels = codes.map((code) => FINANCE_IMPORT_BLOCKER_LABELS[code] ?? '預覽資料仍有待確認項目');
  return [...new Set(labels)].join('、');
}
export function adaptFinanceImportBatch(source: FinanceImportBatchSummary) { return { id: source.batch_id, identity: source.batch_identity, formatId: source.format_id, sourceFile: source.source_file ?? '—', rowCount: source.row_count, status: source.status, version: source.batch_version, architectureReady: source.architecture_ready, createdAt: source.created_at }; }
export function adaptFinanceImportManifest(source: FinanceImportManifest) { return { identity: source.batch_identity, sheetName: source.sheet_name, status: source.status, version: source.batch_version, digest: `${source.source_content_digest.slice(0, 12)}…`, sourceRows: source.source_row_count, canonicalRows: source.canonical_row_count, reviewCount: source.review_count, occurrenceCount: source.occurrence_count, completedAt: source.completed_at ?? '—' }; }
export function adaptFinanceImportReviewPage(source: FinanceImportReviewPage) {
  return {
    items: source.items.map((item) => ({
      id: item.row_id,
      identity: item.row_identity,
      transactionDate: item.transaction_date ?? '—',
      direction: item.direction,
      amount: `NT$ ${item.amount_ntd.toLocaleString()}`,
      classificationType: item.classification_type,
      disposition: item.disposition,
      reconciliationStatus: item.reconciliation_status,
      sourceSheet: item.source_sheet,
      sourceRow: item.source_row,
      occurrenceCount: item.occurrence_count,
      availableActions: item.available_actions,
      createdAt: item.created_at,
    })),
    nextAfterRowId: source.next_after_row_id,
  };
}
export function adaptFinanceImportRunPage(source: FinanceImportRunPage) {
  return {
    items: source.items.map((item) => ({
      id: item.run_id,
      batchIdentity: item.batch_identity,
      classifierVersion: item.classifier_version,
      planFingerprint: `${item.plan_fingerprint.slice(0, 12)}…`,
      selectedCount: item.selected_count,
      changedCount: item.changed_count,
      dispatchCount: item.dispatch_count,
      reconciledCount: item.reconciled_count,
      pendingCount: item.pending_count,
      status: item.status,
      createdAt: item.created_at,
      completedAt: item.completed_at,
    })),
    nextBeforeRunId: source.next_before_run_id,
  };
}
