/**
 * File: finance_import_query_adapter.ts
 * Description: 將Finance Import query映射為loaded-scope唯讀view且保留server status字串。
 */
import type { FinanceBankTransaction, FinanceImportBatchSummary, FinanceImportManifest, FinanceImportReviewPage, FinanceImportRunPage } from '../../api/finance_import/finance_import_query_schemas';
import type { FinanceImportBatchPreview } from '../../api/finance_import/finance_import_mutation_client';
import { SINOPAC_PAYOUT_REASON_MESSAGES, TAISHIN_PAYOUT_REASON_MESSAGES } from '../../api/staff_payables/staff_payout_remediation_errors';
import { REFUND_BLOCKERS, SINOPAC_REFUND_BLOCKERS, TAISHIN_SUBSIDY_REFUND_BLOCKERS } from '../../api/finance_import/finance_import_correction_client';

const REVIEW_REASON_LABELS: Readonly<Record<string, string>> = {
  ...REFUND_BLOCKERS,
  sinopac_valid_virtual_account: '已由虛擬帳號定位案件，未留存當次阻擋原因。',
  sinopac_client_receipt_month_no_match: '日期比對未通過。交易日的年月找不到原到期日同月的待收款項。',
  sinopac_client_receipt_transaction_date_missing: '日期比對無法執行。銀行流水缺少交易日。',
  sinopac_client_receipt_multiple_same_month_exact: '期款比對未通過。同月有多筆候選期款，無法唯一選定。',
  sinopac_client_receipt_multiple_month_candidates: '期款比對未通過。同月有多筆候選期款，無法唯一選定。',
  sinopac_client_receipt_no_open_obligation: '案件目前沒有未清的待收款項。',
  client_receipt_underpaid: '本次核對實收低於所選期款應收，請核對合計差額。',
  sinopac_client_receipt_shortfall: '本次核對實收低於所選期款應收，請核對合計差額。',
  client_receipt_overpaid: '本次核對實收高於所選期款應收，請核對合計差額。',
  sinopac_client_receipt_overage: '本次核對實收高於所選期款應收，請核對合計差額。',
  sinopac_virtual_account_case_not_found: '虛擬帳號查無唯一案件，新匯入跳過，不建立流水。',
  sinopac_invalid_or_missing_virtual_account: '銷帳編號缺漏或格式不符，無法確認唯一案件；新匯入跳過，不建立流水。',
  taishin_government_return_memo: '已辨識為政府補助退回款，請選擇原政府期間核對。',
  taishin_outgoing_unrecognized: '備註未辨識到月嫂姓名或可唯一定位案件的六碼；新匯入跳過，不建立流水。',
  taishin_government_memo: '已辨識為新竹市政府補助入款，請選擇核銷期間完成整期核銷。',
  taishin_client_subsidy_case_suffix_in_memo: '已依備註六碼定位客戶補助案件，請核對同案補助待退款。',
  taishin_memo_case_requires_manual_scheme: '已辨識案件，請查看原始備註並人工確認補助方案。',
  sinopac_unique_staff_case_suffix_in_memo: '已由備註六碼定位月嫂款案件，請核對原交易帳號及同案待付款。',
  sinopac_unique_client_refund_case_suffix_in_memo: '已由備註六碼定位客戶退款案件，請核對原交易帳號及同案待退款。',
  sinopac_unique_staff_account_in_transaction_reference: '已由交易參考帳號辨識月嫂，未留存當次阻擋原因。',
  sinopac_unique_client_refund_account_in_transaction_reference: '已由交易參考帳號辨識客戶退款對象，未留存當次阻擋原因。',
  outgoing_staff_payout_name_ambiguous: '月嫂姓名有多個相符對象，無法唯一確認。',
  outgoing_client_refund_name_ambiguous: '客戶姓名有多個相符對象，無法唯一確認。',
  outgoing_staff_payout_month_no_match: '日期比對未通過。交易日的年月找不到預計撥款日同月的待付款項。',
  outgoing_client_refund_month_no_match: '日期比對未通過。交易日的年月找不到預計退款日同月的待退款項。',
  outgoing_staff_payout_amount_mismatch: '出款金額與同月待付款項不符，請核對差額。',
  outgoing_client_refund_amount_mismatch: '出款金額與同月待退款項不符，請核對差額。',
  outgoing_staff_payout_target_ambiguous: '同月有多筆待付款項，無法用出款金額唯一確認。',
  outgoing_staff_payout_multiple_fee_matches: '金額比對未通過。同月有多個待付配對符合手續費條件。',
  outgoing_client_refund_multiple_fee_matches: '同月有多個待退款配對符合金額或手續費條件，無法唯一選定。',
  unique_client_refund_name_and_month_matched: '退款對象與同月款項已辨識，未留存當次阻擋原因。',
  client_refund_disambiguated_by_month_and_amount: '已依月份及金額縮小退款候選，未留存當次阻擋原因。',
  unique_client_refund_name_month_fee_matched: '退款對象、月份及手續費條件已比對，未留存當次阻擋原因。',
  unique_staff_payout_name_and_month_matched: '月嫂姓名與同月款項已辨識，未留存當次阻擋原因。',
  staff_payout_disambiguated_by_month_and_amount: '已依月份及金額縮小月嫂款候選，未留存當次阻擋原因。',
  unique_staff_payout_name_month_fee_matched: '月嫂姓名、月份及手續費條件已比對，未留存當次阻擋原因。',
  outgoing_client_refund_target_ambiguous: '同月有多筆待退款項，無法用出款金額唯一確認。',
  outgoing_staff_payout_no_open_obligation: '姓名已辨識，目前沒有待付款項。',
  outgoing_client_refund_no_open_obligation: '目前沒有可供這筆交易核對的待退款項。',
  due_date_missing: '待核銷款項缺少到期或預計付款日期，無法比對月份。',
  counterparty_identity_type_conflict: '案件、對象或帳戶證據互相衝突，無法確認唯一歸屬。',
  counterparty_account_multiple_matches: '交易帳號對應多位對象，需人工確認。',
  sinopac_staff_account_no_match: '交易參考帳號找不到對應的月嫂。',
  sinopac_staff_account_identity_ambiguous: '交易參考帳號對應多位月嫂，需人工確認。',
  direction_unknown: '無法判定這筆交易是存入或支出。',
  taishin_incoming_not_government: '這筆存入款不符合政府補助的自動辨識條件。',
  unsupported_bank_direction: '這種銀行交易尚無適用的自動配對方式。',
  sinopac_staff_return_requires_matching: '交易帳號對應月嫂，無法辨識為客戶入款；新匯入跳過，不建立流水。',
  staff_bank_account_ambiguous: '帳戶驗證未通過。交易收款帳號缺少，或無法對應唯一有效的月嫂主要帳戶。',
  staff_memo_recipient_unconfirmed: '備註姓名驗證未通過。無法唯一確認收款月嫂，請核對原始銀行備註與人員姓名。',
  cross_staff_allocation_forbidden: '帳戶或對象驗證未通過。交易、收款帳戶與待付款項的月嫂歸屬不一致。',
  outgoing_bank_fact_not_eligible: '銀行出款未通過核銷資格驗證。系統沒有留存更細的拒絕原因。',
};

const CLIENT_INSTALLMENT_LABELS: Readonly<Record<string, string>> = {
  deposit: '訂金', first: '第一期', second: '第二期',
};
const MISSING_REVIEW_REASON = '未留存當次阻擋原因。';
const CURRENT_RECEIPT_REASONS = new Set([
  'sinopac_client_receipt_month_no_match', 'sinopac_client_receipt_no_open_obligation',
  'sinopac_client_receipt_shortfall', 'sinopac_client_receipt_overage',
  'client_receipt_underpaid', 'client_receipt_overpaid', 'due_date_missing',
]);

const RECONCILIATION_UNAVAILABLE_LABELS: Readonly<Record<string, string>> = {
  blocked: '銷帳受阻，請查看阻擋原因。',
  direction_unconfirmed: '交易方向待確認。',
  purpose_unconfirmed: '此款項目前沒有可用的案件核對入口。',
  case_reference_unconfirmed: '備註中的案件線索無法確認或與關聯案件不符。',
  case_unconfirmed: '尚未確認唯一案件。',
  staff_unconfirmed: '案件已定位，尚未確認這筆出款的月嫂。',
  client_unconfirmed: '案件已定位，尚未確認這筆出款的客戶。',
  no_open_items: '本案沒有可供這筆交易核對的未清款項。',
  transaction_date_missing: '銀行流水缺少交易日，無法比對月份。',
  due_date_missing: '本案待核銷款項缺少到期或預計付款日期。',
  no_same_month_items: '本案沒有與銀行交易同月的待核銷款項。',
  items_not_unique: '本案同月有多筆待核銷款項，無法唯一指定。',
  no_eligible_item: '找不到可帶入核對的款項。',
};

export function bankReconciliationUnavailableReason(row: FinanceBankTransaction): string {
  return RECONCILIATION_UNAVAILABLE_LABELS[row.reconciliation_unavailable_reason ?? ''] ?? '對應款項待確認';
}

type ReviewDisposition = Pick<FinanceImportReviewPage['items'][number], 'classification_type' | 'direction' | 'available_actions' | 'disposition'>;
type ReviewRow = ReviewDisposition & Partial<Pick<FinanceBankTransaction,
  'bank' | 'review_reason' | 'dispatch_reason' | 'transaction_date' | 'recorded_client_receipt_review' | 'recorded_pending_reason'>>;
type ReviewResult = { reasonCode: string | null; message: string };

function resolveFinanceImportReview(
  row: ReviewRow,
  preview?: FinanceImportBatchPreview['rows'][number],
  postingStopped?: 'preview_blocked' | 'apply_failed',
): ReviewResult {
  const reasonLabel = (code: string) => {
    if ((row.bank === 'taishin' || row.bank === undefined) && row.classification_type === 'client_subsidy_return') {
      if (code === 'bank_fact_not_eligible') return MISSING_REVIEW_REASON;
      if (['refund_requires_exact_settlement','allocation_exceeds_obligation'].includes(code)) return TAISHIN_SUBSIDY_REFUND_BLOCKERS.outgoing_client_refund_amount_mismatch;
      return TAISHIN_SUBSIDY_REFUND_BLOCKERS[code] ?? MISSING_REVIEW_REASON;
    }
    if (row.bank === 'sinopac' && row.classification_type === 'client_refund') {
      if (code === 'outgoing_client_refund_target_ambiguous') return '舊紀錄僅保留退款目標不明的原因，未留存實際是金額不符或有多個有效配對。';
      if (['outgoing_client_refund_name_ambiguous', 'counterparty_identity_type_conflict'].includes(code)) return '舊紀錄僅保留對象辨識診斷，未留存當次核銷阻擋原因。';
      if (code === 'bank_fact_not_eligible') return MISSING_REVIEW_REASON;
      if (['refund_requires_exact_settlement', 'allocation_exceeds_obligation'].includes(code)) return SINOPAC_REFUND_BLOCKERS.outgoing_client_refund_amount_mismatch;
      if (SINOPAC_REFUND_BLOCKERS[code]) return SINOPAC_REFUND_BLOCKERS[code];
    }
    if (row.classification_type === 'client_receipt') {
      if (code === 'bank_transaction_date_missing' || code === 'sinopac_client_receipt_transaction_date_missing') return '原銀行流水缺少交易日，無法核銷客戶入款。';
      if (code === 'bank_currency_not_twd') return '原銀行流水幣別不是新臺幣，無法核銷客戶入款。';
      if (code === 'due_date_missing') return '待收期款缺少原到期日，無法完成月份配對；請人工選款核對。';
      if (code === 'bank_fact_not_eligible' || code === 'client_refund_recipient_snapshot_missing') return MISSING_REVIEW_REASON;
    }
    if (row.bank === 'sinopac' && ['staff_payout','staff_salary'].includes(row.classification_type)) {
      if (code === 'outgoing_bank_fact_not_eligible') return MISSING_REVIEW_REASON;
      if (code === 'outgoing_staff_payout_name_ambiguous') return '舊紀錄僅保留姓名辨識不唯一的診斷，未留存當次核銷阻擋原因。';
      if (SINOPAC_PAYOUT_REASON_MESSAGES[code]) return SINOPAC_PAYOUT_REASON_MESSAGES[code];
    }
    if (row.bank === 'taishin' && ['staff_payout','staff_salary'].includes(row.classification_type)) {
      if (code === 'outgoing_bank_fact_not_eligible') return MISSING_REVIEW_REASON;
      if (TAISHIN_PAYOUT_REASON_MESSAGES[code]) return TAISHIN_PAYOUT_REASON_MESSAGES[code];
    }
    return REVIEW_REASON_LABELS[code];
  };
  const describe = (code: string, fallback = MISSING_REVIEW_REASON): ReviewResult => {
    const message = reasonLabel(code);
    return { reasonCode: message && message !== MISSING_REVIEW_REASON ? code : null, message: message ?? fallback };
  };
  const receiptOperationOnly = row.classification_type === 'client_receipt'
    && (row.dispatch_reason === 'bank_fact_not_eligible' || row.dispatch_reason === 'client_refund_recipient_snapshot_missing');
  const staffOperationOnly = row.bank === 'sinopac' && ['staff_payout','staff_salary'].includes(row.classification_type)
    && ['staff_payout_difference_mode_invalid','outgoing_bank_fact_not_eligible'].includes(row.dispatch_reason ?? '');
  const refundOperationOnly = row.bank === 'sinopac' && row.classification_type === 'client_refund'
    && ['bank_fact_not_eligible', 'stale_preview'].includes(row.dispatch_reason ?? '');
  const taishinStaffOperationOnly = row.bank === 'taishin' && ['staff_payout','staff_salary'].includes(row.classification_type)
    && ['outgoing_bank_fact_not_eligible','staff_payout_difference_mode_invalid','staff_payable_candidate_stale'].includes(row.dispatch_reason ?? '');
  const taishinSubsidyOperationOnly = (row.bank === 'taishin' || row.bank === undefined) && row.classification_type === 'client_subsidy_return'
    && ['bank_fact_not_eligible','stale_preview'].includes(row.dispatch_reason ?? '');
  if (row.dispatch_reason && !receiptOperationOnly && !staffOperationOnly && !refundOperationOnly && !taishinStaffOperationOnly && !taishinSubsidyOperationOnly) return describe(row.dispatch_reason, `正式核銷檢查未通過。${MISSING_REVIEW_REASON}`);
  const pendingReason = row.recorded_pending_reason ?? (preview?.disposition === 'business_pending' ? preview.pending_reason : null);
  if (pendingReason) return describe(pendingReason);
  const review = row.recorded_client_receipt_review ?? (preview?.disposition === 'business_pending' ? preview.client_receipt_review : null);
  if (review) {
    const { reason, candidates } = review;
    const result = describe(reason);
    if (!candidates.length) return result;
    const installments = candidates.map(({ obligation_type, due_date }) =>
      `${CLIENT_INSTALLMENT_LABELS[obligation_type] ?? '其他應收款'}（到期日 ${due_date ?? '未設定'}）`);
    return { ...result, message: `${result.message} 候選期款：${installments.join('、')}。` };
  }
  if (preview?.fingerprint_collision) return { reasonCode: 'fingerprint_collision', message: '存在可能重複的銀行交易，需先核對原始資料。' };
  if (preview?.formal_reference_conflict) return { reasonCode: 'formal_reference_conflict', message: '正式參考資料互相衝突，需先確認正確來源。' };
  if (preview?.integrity_violations.length) return { reasonCode: 'integrity_violations', message: `來源資料未通過完整性檢查：${financeImportBlockerMessage(preview.integrity_violations)}。` };
  if (postingStopped && preview?.disposition === 'create') {
    return { reasonCode: null, message: postingStopped === 'preview_blocked'
      ? '流水已保存。批次預覽有阻擋，尚未執行自動核銷。'
      : `流水已保存。當次批次核銷未完成。${MISSING_REVIEW_REASON}` };
  }
  const reviewReason = row.review_reason ?? '';
  if (row.classification_type === 'client_receipt' && CURRENT_RECEIPT_REASONS.has(reviewReason)) {
    return { reasonCode: null, message: `${MISSING_REVIEW_REASON} 依目前期款檢查，${reasonLabel(reviewReason)}` };
  }
  const reasons = [...(preview?.evidence ?? []), reviewReason].flatMap(code => reasonLabel(code) ? [reasonLabel(code)] : []);
  if (reasons.length) return { reasonCode: null, message: [...new Set(reasons)].join(' ') };
  if (row.disposition === 'business_pending' && row.classification_type === 'government_subsidy') {
    return { reasonCode: null, message: '已辨識為新竹市政府補助款，請選擇核銷期間完成整期核銷。' };
  }
  if (row.transaction_date === null) return { reasonCode: null, message: `${MISSING_REVIEW_REASON} 原銀行流水缺少交易日。` };
  return { reasonCode: null, message: MISSING_REVIEW_REASON };
}

export function financeImportReviewReason(
  row: ReviewRow,
  preview?: FinanceImportBatchPreview['rows'][number],
  postingStopped?: 'preview_blocked' | 'apply_failed',
): string {
  return resolveFinanceImportReview(row, preview, postingStopped).message;
}

export function financeBankReviewPresentation(
  row: ReviewRow,
  preview?: FinanceImportBatchPreview['rows'][number],
  postingStopped?: 'preview_blocked' | 'apply_failed',
): { label: string; reason: string; nextStep: string } {
  const { reasonCode, message: reason } = resolveFinanceImportReview(row, preview, postingStopped);
  if (row.classification_type === 'non_business_review' && reasonCode === null
      && row.review_reason === 'taishin_memo_case_requires_manual_scheme') {
    return {label: '待人工確認方案', reason: '已依備註六碼辨識案件，款項用途尚未確認。', nextStep: '請點案件編號，查看原始備註並設定補助方案。'};
  }
  if (reasonCode && [
    'client_receipt_underpaid', 'client_receipt_overpaid',
    'sinopac_client_receipt_shortfall', 'sinopac_client_receipt_overage',
    'staff_payout_amount_mismatch', 'outgoing_staff_payout_amount_mismatch',
    'outgoing_client_refund_amount_mismatch', 'refund_requires_exact_settlement', 'allocation_exceeds_obligation',
  ].includes(reasonCode)) {
    return { label: '金額不符', reason, nextStep: '金額不符，請核對金額並選擇處理方式。' };
  }
  if (reasonCode && [
    'sinopac_client_receipt_multiple_month_candidates', 'sinopac_client_receipt_multiple_same_month_exact',
    'outgoing_staff_payout_multiple_fee_matches', 'outgoing_client_refund_multiple_fee_matches',
  ].includes(reasonCode)) {
    return { label: '有多個候選款項', reason, nextStep: '有多個候選款項，請選擇本次核銷款項。' };
  }
  const nextSteps: Readonly<Record<string, string>> = {
    bank_transaction_date_missing: '請查核並補正原銀行流水交易日後重新核對。',
    sinopac_client_receipt_transaction_date_missing: '請查核並補正原銀行流水交易日後重新核對。',
    due_date_missing: '請核對款項日期；確認對應款項後，可進入核對人工選款。',
    bank_currency_not_twd: '請查核原銀行流水幣別及來源資料後重新核對。',
  };
  return {
    label: '待核對', reason,
    nextStep: reasonCode
      ? nextSteps[reasonCode] ?? '請依上述原因核對資料，再選擇對應款項及處理方式。'
      : row.classification_type === 'government_subsidy'
        ? '請選擇原政府期間核對。'
        : '未留存當次未核銷原因，請進入核對確認。',
  };
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
