/**
 * File: finance_import_query_adapter.ts
 * Description: 將Finance Import query映射為loaded-scope唯讀view且保留server status字串。
 */
import type { FinanceImportBatchSummary, FinanceImportManifest, FinanceImportReviewPage, FinanceImportRunPage } from '../../api/finance_import/finance_import_query_schemas';
import type { FinanceImportBatchPreview } from '../../api/finance_import/finance_import_mutation_client';

const REVIEW_REASON_LABELS: Readonly<Record<string, string>> = {
  suspected_duplicate_business_match: '多筆銀行交易對應到同一筆待收款，需確認是否重複入款。',
  sinopac_valid_virtual_account: '銷帳編號格式可辨識，但尚未唯一配對到金額相符的待收款項，請確認案件與入款金額。',
  sinopac_invalid_or_missing_virtual_account: '銷帳編號缺漏或格式不符，無法自動定位案件。',
  client_receipt_heuristic_ambiguous: '姓名、帳號與金額符合多位客戶，無法唯一確認對象。',
  counterparty_account_missing: '銀行資料缺少交易對象帳號。',
  counterparty_account_invalid: '交易對象帳號格式不符。',
  counterparty_identity_type_conflict: '交易帳號同時對應不同類型的收付款對象。',
  counterparty_account_multiple_matches: '交易帳號對應多位對象，需人工確認。',
  counterparty_account_no_match: '交易帳號找不到對應的收付款對象。',
  sinopac_staff_account_no_match: '交易參考帳號找不到對應的月嫂。',
  sinopac_staff_account_identity_ambiguous: '交易參考帳號對應多位月嫂，需人工確認。',
  direction_unknown: '無法判定這筆交易是存入或支出。',
  taishin_incoming_not_government: '這筆存入款不符合政府補助的自動辨識條件。',
  unsupported_bank_direction: '這種銀行交易尚無適用的自動配對方式。',
  sinopac_staff_return_requires_matching: '這筆月嫂退回款需要確認對應的原付款。',
  subsidy_advance_not_due: '補助退款尚未符合政府入款或工會代墊條件，暫時無法核銷。',
};

export function financeImportReviewReason(
  row: FinanceImportReviewPage['items'][number],
  preview?: FinanceImportBatchPreview['rows'][number],
  postingStopped = false,
): string {
  if (preview?.fingerprint_collision) return '存在可能重複的銀行交易，需先核對原始資料。';
  if (preview?.formal_reference_conflict) return '正式參考資料互相衝突，需先確認正確來源。';
  if (preview?.integrity_violations.length) return `來源資料未通過完整性檢查：${financeImportBlockerMessage(preview.integrity_violations)}。`;
  if (postingStopped && preview?.disposition === 'create') return '此筆符合自動入帳條件，但本次匯入有錯誤，尚未執行入帳。';
  if (row.available_actions.includes('review_suspected_duplicate_business_match')) return REVIEW_REASON_LABELS.suspected_duplicate_business_match;
  const reasons = (preview?.evidence ?? []).flatMap(code => REVIEW_REASON_LABELS[code] ? [REVIEW_REASON_LABELS[code]] : []);
  if (reasons.length) return [...new Set(reasons)].join(' ');
  if (row.disposition === 'business_pending') {
    const target = ({ staff_payout: '月嫂及待付款項', client_refund: '案件及待退款項', government_subsidy: '政府補助待核銷款項', client_subsidy_return: '補助退款項', client_refund_return: '客戶退款退回款項' } as Record<string, string>)[row.classification_type] ?? '案件及待收款項';
    return `尚未確認可自動核銷的${target}，請人工選擇正確對象與款項後核對金額。`;
  }
  if (row.disposition === 'blocked') return '這筆交易未通過入帳檢查，請核對來源資料後重新查詢。';
  return '現有銀行資料不足以自動確認收付款用途或對象，需人工核對。';
}

export function financeImportDispositionLabel(disposition: string): string {
  return ({ manual_review: '待人工核對', business_pending: '待指定款項', blocked: '入帳受阻' } as Record<string, string>)[disposition] ?? '待確認';
}
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
