/**
 * File: staff_payout_remediation_errors.ts
 * Description: PAYOUT-001 工作台的 typed transport、schema、owner 與終態錯誤。
 */
import {
  ApiAbortError,
  ApiDecodeError,
  ApiError,
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
  extractErrorMessage,
} from '../shared/typed_errors';

export class StaffPayoutRemediationError extends ApiError {
  public readonly name = 'StaffPayoutRemediationError';
  public readonly code: string;
  public readonly retryable: boolean;
  public readonly status?: number;
  constructor(
    code: string,
    message: string,
    retryable = false,
    status?: number,
  ) { super(message); this.code = code; this.retryable = retryable; this.status = status; }
}

const PAYOUT_BLOCKER_MESSAGES: Readonly<Record<string, string>> = {
  staff_subsidy_split_selection_invalid: '請一次選擇同一案件的一筆月嫂應付及一筆永豐出款，再確認補助方案一。',
  staff_subsidy_split_plan_conflict: '本案已有不同補助方案，請先回案件帳務確認原方案及已成立的收付款。',
  staff_subsidy_split_amount_missing: '本案正式補助金額尚未確認，不能由銀行差額推算；請先補齊補助金額來源。',
  staff_subsidy_split_amount_conflict: '本案月嫂總應付、補助額或既有分配互相矛盾，無法核銷自備款；免自備案件請核對台新補助款。',
  staff_subsidy_split_refund_conflict: '本案已有客戶補助退款，請先確認既有退款與補助方案。',
  staff_subsidy_split_service_end_missing: '本案缺少正式服務結束日，無法確認補助款撥款日期，請先確認服務資料。',
  staff_bank_account_ambiguous: '銀行流水缺少收款帳號，或無法對應唯一有效的月嫂主要帳戶，請核對原流水與月嫂帳戶。',
  staff_memo_recipient_unconfirmed: '銀行備註中的月嫂姓名無法唯一確認，請核對原始備註與月嫂姓名。',
  cross_staff_allocation_forbidden: '銀行流水、收款帳戶與待付款項的月嫂歸屬不一致，請核對付款對象。',
  bank_transaction_date_missing: '原銀行流水缺少交易日，無法核銷月嫂付款，請先查核來源資料。',
  bank_currency_not_twd: '原銀行流水幣別不是新臺幣，無法核銷月嫂付款，請先查核來源資料。',
  outgoing_bank_fact_not_eligible: '原銀行出款未通過核銷資格檢查，原操作未留存更細的拒絕原因，請查核原流水。',
};

export const SINOPAC_PAYOUT_REASON_MESSAGES: Readonly<Record<string,string>> = {
  bank_transaction_date_missing: PAYOUT_BLOCKER_MESSAGES.bank_transaction_date_missing,
  bank_currency_not_twd: PAYOUT_BLOCKER_MESSAGES.bank_currency_not_twd,
  staff_payout_amount_mismatch: '銀行實付與本次待付合計不符合足額或100元內手續費條件，請核對差額；不足額或超付須選對應方式處理。',
  outgoing_staff_payout_amount_mismatch: '銀行實付與本次待付合計不符合足額或100元內手續費條件，請核對差額；不足額或超付須選對應方式處理。',
  outgoing_staff_payout_target_ambiguous: '舊紀錄未留存當次符合金額的候選數量，請核對款項與合計。',
  outgoing_staff_payout_multiple_fee_matches: '有多個單筆或合併付款集合符合金額及手續費條件，無法唯一選定，請人工選款。',
  outgoing_staff_payout_no_open_obligation: '已確認案件及月嫂，目前沒有未清待付款項。',
  due_date_missing: '待付款項缺少原預計撥款日，無法完成月份配對，請回本案核對。',
  staff_obligation_not_exactly_settled: '所選應付款狀態或本次分配不符合核銷條件，請重新查核目前款項與餘額；這不代表禁止部分付款。',
  staff_payout_difference_mode_invalid: '選取的不足額或超付方式與實際金額關係不符，請重新選擇核銷方式。',
};

export const TAISHIN_PAYOUT_REASON_MESSAGES: Readonly<Record<string,string>> = {
  ...SINOPAC_PAYOUT_REASON_MESSAGES,
  bank_transaction_date_missing: '原銀行流水缺少交易日，無法核銷台新月嫂補助付款。',
  bank_currency_not_twd: '原銀行流水幣別不是新臺幣，無法核銷台新月嫂補助付款。',
  outgoing_staff_payout_month_no_match: '交易日與預計撥款日都有值，但找不到同年月的未清待付款；請人工選款核對。',
  staff_memo_recipient_unconfirmed: '原銀行備註的月嫂姓名無法唯一確認，請查核原始備註與月嫂名冊；不以六碼或帳號代替月嫂姓名。',
  cross_staff_allocation_forbidden: '原銀行備註確認的月嫂與所選應付款月嫂不同，請核對付款對象及款項。',
  outgoing_staff_payout_name_ambiguous: '紀錄只保留月嫂姓名不唯一的辨識診斷，未留存當次核銷阻擋細節。',
  staff_bank_account_ambiguous: '紀錄只留有帳戶檢查原因；現行台新月嫂補助核銷不要求帳號，請重新核對原始備註姓名及款項。',
  staff_payable_not_found: '所選應付款已不存在或無法讀取，請重新查詢目前款項。',
  invalid_staff_payout_intent: '核銷的流水或款項選取不完整，請重新查詢並選款。',
};

export function staffPayoutBlockerMessage(code?: string | null, sourceBank?: string): string | undefined {
  if (code && ['staff_installment_funding_ambiguous', 'staff_installment_funding_unconfirmed', 'staff_installment_funding_conflict'].includes(code)) {
    if (sourceBank === 'sinopac') return '自備款與補助款分配待確認；若本案為方案一，可選「補助方案一：核銷自備款，補助款保留待付」預覽。金額或原付款來源仍有衝突時，須先核對來源，不以補助待付款當作手續費。';
    return '自備款與補助款的付款來源或已核銷分配無法確認，請分銀行核對正式分期及原付款；不以補助待付款當作手續費。';
  }
  const bankReasons = sourceBank === 'sinopac' ? SINOPAC_PAYOUT_REASON_MESSAGES : sourceBank === 'taishin' ? TAISHIN_PAYOUT_REASON_MESSAGES : {};
  return code ? bankReasons[code] ?? PAYOUT_BLOCKER_MESSAGES[code] : undefined;
}

export function mapStaffPayoutRemediationError(error: unknown): StaffPayoutRemediationError {
  if (error instanceof StaffPayoutRemediationError) return error;
  if (error instanceof ApiAbortError) return new StaffPayoutRemediationError('STAFF_PAYOUT_ABORTED', error.message);
  if (error instanceof ApiTimeoutError) return new StaffPayoutRemediationError('STAFF_PAYOUT_TIMEOUT', error.message, true);
  if (error instanceof ApiNetworkError) return new StaffPayoutRemediationError('STAFF_PAYOUT_NETWORK', error.message, true);
  if (error instanceof ApiDecodeError) return new StaffPayoutRemediationError('STAFF_PAYOUT_SCHEMA_MISMATCH', error.message);
  if (error instanceof ApiHttpError) return new StaffPayoutRemediationError(error.code, error.message, error.retryable, error.status);
  return new StaffPayoutRemediationError('STAFF_PAYOUT_UNKNOWN', extractErrorMessage(error));
}
