/**
 * File: finance_import_query_adapter.ts
 * Description: 將Finance Import query映射為loaded-scope唯讀view且保留server status字串。
 */
import type { FinanceImportBatchSummary, FinanceImportManifest, FinanceImportReviewPage, FinanceImportRunPage } from '../../api/finance_import/finance_import_query_schemas';
import type { FinanceImportBatchPreview } from '../../api/finance_import/finance_import_mutation_client';

const REVIEW_REASON_LABELS: Readonly<Record<string, string>> = {
  suspected_duplicate_business_match: '多筆銀行交易對應到同一筆待收款，需確認是否重複入款。',
  sinopac_valid_virtual_account: '已由虛擬帳號定位案件。待收款項尚未唯一確認，沒有留存更詳細的核銷結果。',
  sinopac_client_receipt_month_no_match: '日期比對未通過。交易日的年月找不到原到期日同月的待收款項。',
  sinopac_client_receipt_no_open_obligation: '案件目前沒有未清的待收款項。',
  sinopac_client_receipt_shortfall: '入款金額低於同月待收款項，請核對差額。',
  sinopac_client_receipt_overage: '入款金額高於同月待收款項，請核對差額。',
  sinopac_virtual_account_case_not_found: '虛擬帳號查無對應案件，請確認案件編號。',
  sinopac_invalid_or_missing_virtual_account: '銷帳編號缺漏或格式不符，無法自動定位案件。',
  taishin_government_memo: '已辨識為新竹市政府補助入款，請選擇核銷期間完成整期核銷。',
  taishin_unique_staff_case_suffix_in_memo: '已從備註辨識案件，但沒有符合自動核銷條件的月嫂姓名配對。',
  taishin_unique_client_refund_case_suffix_in_memo: '已從備註辨識案件，但沒有符合自動核銷條件的客戶姓名配對。',
  sinopac_unique_staff_case_suffix_in_memo: '已從備註辨識案件，但沒有符合自動核銷條件的月嫂姓名配對。',
  sinopac_unique_client_refund_case_suffix_in_memo: '已從備註辨識案件，但沒有符合自動核銷條件的客戶姓名配對。',
  taishin_unique_staff_account: '已從帳號辨識月嫂，但沒有符合自動核銷條件的月嫂姓名配對。',
  sinopac_unique_staff_account_in_transaction_reference: '已從帳號辨識月嫂，但沒有符合自動核銷條件的月嫂姓名配對。',
  taishin_unique_client_refund_account: '已從帳號辨識客戶，但沒有符合自動核銷條件的客戶姓名配對。',
  sinopac_unique_client_refund_account_in_transaction_reference: '已從帳號辨識客戶，但沒有符合自動核銷條件的客戶姓名配對。',
  taishin_unique_client_subsidy_return_account: '已從帳號辨識客戶，但沒有符合自動核銷條件的客戶姓名配對。',
  outgoing_staff_payout_name_ambiguous: '月嫂姓名有多個相符對象，無法唯一確認。',
  outgoing_client_refund_name_ambiguous: '客戶姓名有多個相符對象，無法唯一確認。',
  outgoing_staff_payout_month_no_match: '日期比對未通過。交易日的年月找不到預計撥款日同月的待付款項。',
  taishin_client_refund_month_no_match: '日期比對未通過。交易日的年月找不到預計退款日同月的待退款項。',
  outgoing_staff_payout_amount_mismatch: '出款金額與同月待付款項不符，請核對差額。',
  taishin_client_refund_amount_mismatch: '出款金額與同月待退款項不符，請核對差額。',
  outgoing_staff_payout_target_ambiguous: '同月有多筆待付款項，無法用出款金額唯一確認。',
  outgoing_client_refund_target_ambiguous: '同月有多筆待退款項，無法用出款金額唯一確認。',
  outgoing_staff_payout_no_open_obligation: '姓名已辨識，目前沒有待付款項。',
  taishin_client_refund_no_open_obligation: '姓名已辨識，目前沒有待退款項。',
  client_receipt_heuristic_ambiguous: '姓名、帳號與金額符合多位客戶，無法唯一確認對象。',
  counterparty_account_missing: '銀行資料缺少交易對象帳號。',
  counterparty_account_invalid: '交易對象帳號格式不符。',
  counterparty_identity_type_conflict: '姓名、帳號或案件線索指向不同收付款對象。',
  counterparty_account_multiple_matches: '交易帳號對應多位對象，需人工確認。',
  counterparty_account_no_match: '交易帳號找不到對應的收付款對象。',
  sinopac_staff_account_no_match: '交易參考帳號找不到對應的月嫂。',
  sinopac_staff_account_identity_ambiguous: '交易參考帳號對應多位月嫂，需人工確認。',
  direction_unknown: '無法判定這筆交易是存入或支出。',
  taishin_incoming_not_government: '這筆存入款不符合政府補助的自動辨識條件。',
  unsupported_bank_direction: '這種銀行交易尚無適用的自動配對方式。',
  sinopac_staff_return_requires_matching: '這筆月嫂退回款需要確認對應的原付款。',
  subsidy_advance_not_due: '補助退款尚未符合政府入款或工會代墊條件，暫時無法核銷。',
  staff_bank_account_ambiguous: '帳戶驗證未通過。交易收款帳號缺少，或無法對應唯一有效的月嫂主要帳戶。',
  cross_staff_allocation_forbidden: '帳戶或對象驗證未通過。交易、收款帳戶與待付款項的月嫂歸屬不一致。',
  client_refund_recipient_account_ambiguous: '帳戶驗證未通過。待退款項沒有唯一的退款收款帳戶。',
  client_refund_recipient_account_mismatch: '帳戶驗證未通過。銀行出款的收款帳號缺少，或與待退款項的收款帳戶不符。',
  bank_fact_not_eligible: '銀行流水未通過核銷資格驗證。系統沒有留存更細的拒絕原因。',
  outgoing_bank_fact_not_eligible: '銀行出款未通過核銷資格驗證。系統沒有留存更細的拒絕原因。',
  stale_preview: '核銷前資料已變更，當次自動核銷未完成。',
};

type ReviewDisposition = Pick<FinanceImportReviewPage['items'][number], 'classification_type' | 'direction' | 'available_actions' | 'disposition'>;

export function financeImportSkipsUnidentifiedOutgoing(
  row: Pick<ReviewDisposition, 'classification_type' | 'direction'>,
  preview?: FinanceImportBatchPreview['rows'][number],
): boolean {
  return row.classification_type === 'non_business_review' && row.direction === 'outgoing'
    && !!preview?.evidence.some(code => ['counterparty_account_missing', 'counterparty_account_invalid',
      'counterparty_account_no_match', 'sinopac_staff_account_no_match'].includes(code));
}

export function financeImportReviewReason(
  row: ReviewDisposition & { review_reason?: string | null; dispatch_reason?: string | null; transaction_date?: string | null },
  preview?: FinanceImportBatchPreview['rows'][number],
  postingStopped?: 'preview_blocked' | 'apply_failed',
): string {
  if (row.dispatch_reason) return REVIEW_REASON_LABELS[row.dispatch_reason] ?? '正式核銷檢查未通過。';
  if (preview?.fingerprint_collision) return '存在可能重複的銀行交易，需先核對原始資料。';
  if (preview?.formal_reference_conflict) return '正式參考資料互相衝突，需先確認正確來源。';
  if (preview?.integrity_violations.length) return `來源資料未通過完整性檢查：${financeImportBlockerMessage(preview.integrity_violations)}。`;
  if (row.transaction_date === null) return '日期比對無法執行。銀行流水缺少交易日。';
  if (financeImportSkipsUnidentifiedOutgoing(row, preview)) return '無法辨識收款對象，已略過銷帳；只保留原始銀行紀錄，不指定案件或月嫂。';
  if (postingStopped && preview?.disposition === 'create') {
    return postingStopped === 'preview_blocked'
      ? '流水已保存。批次預覽有阻擋，尚未執行自動核銷。'
      : '流水已保存。當次核銷工作未完成，這筆交易沒有留存逐筆拒絕原因。';
  }
  if (row.available_actions.includes('review_suspected_duplicate_business_match')) return REVIEW_REASON_LABELS.suspected_duplicate_business_match;
  const reasons = [...(preview?.evidence ?? []), row.review_reason ?? ''].flatMap(code => REVIEW_REASON_LABELS[code] ? [REVIEW_REASON_LABELS[code]] : []);
  if (reasons.length) return [...new Set(reasons)].join(' ');
  if (row.disposition === 'business_pending' && row.classification_type === 'government_subsidy') {
    return '已辨識為新竹市政府補助款，請選擇核銷期間完成整期核銷。';
  }
  if (row.disposition === 'blocked') return '這筆交易未通過銷帳檢查，沒有留存更詳細的原因。';
  return '這筆交易尚未核銷，沒有留存更詳細的原因。';
}

export function financeImportDispositionLabel(disposition: string): string {
  return ({ manual_review: '待人工核對', business_pending: '待指定款項', blocked: '銷帳受阻' } as Record<string, string>)[disposition] ?? '待確認';
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
