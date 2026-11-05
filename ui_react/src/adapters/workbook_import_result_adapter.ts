/**
 * File: workbook_import_result_adapter.ts
 * Description: 將各工作簿匯入收據轉為互斥結果筆數與未匯入逐筆明細，格式化跨案件排程衝突說明。
 */
import type { HcmWorkbookReceipt, HcmWorkbookRowOutcome } from '../api/case_import/hcm_workbook_schemas';
import type { ClientBeClassWorkbookReceipt } from '../api/case_import/client_beclass_workbook/schemas';
import type { StaffHistoricalWorkbookReceipt } from '../api/case_import/staff_historical_workbook/schemas';
import type { HistoricalOrderWorkbookReceipt } from '../api/orders/historical_order_workbook/schemas';

export interface WorkbookImportResult {
  sourceCount: number;
  importedCount: number | null;
  duplicateCount: number | null;
  notImportedCount: number | null;
  replayedWorkbook: boolean;
  notImportedRows: Array<{ sourceRow: number; identifier: string | null; fields: string[]; reasons: string[] }> | null;
}

const REASON_LABELS: Record<string, string> = {
  client_beclass_source_payload_conflict: '同一查詢序號已有不同來源內容',
  client_case_binding_no_client: '姓名與電話找不到可配對的客戶',
  client_case_binding_multiple_clients: '姓名與電話對應多位客戶，無法確定對象',
  client_case_binding_case_not_unique: '客戶沒有唯一可配對案件',
  blocked_identity: '姓名或身分證字號缺漏／格式錯誤',
  identity_conflict: '身分資料與既有人員衝突，無法確定對象',
  unmatched_case: '找不到對應案件',
  current_conflict: '來源與目前案件資料衝突',
  review_required: '資料未通過匯入檢查',
  failed: '處理失敗',
  historical_case_no_missing: '缺少案件編號',
  historical_client_name_missing: '缺少客戶姓名',
  historical_status_invalid: '訂單狀態空白或格式錯誤',
  historical_staff_not_found: '找不到對應月嫂',
  historical_staff_ambiguous: '月嫂姓名對應多人，無法確定對象',
  historical_calendar_staff_missing: '缺少可採納的月嫂指派',
  historical_calendar_valid_dates_missing: '缺少有效的歷史服務起迄日期',
  historical_calendar_completed_assignment_missing: '缺少已完成的歷史服務指派',
  historical_order_source_schedule_conflict: '與同檔案其他案件的月嫂服務期間重疊',
};

const SCHEDULE_CONFLICT_DETAIL_PREFIX = 'historical_order_source_schedule_conflict_detail:';

function parseScheduleConflictDetail(code: string): string | null {
  if (!code.startsWith(SCHEDULE_CONFLICT_DETAIL_PREFIX)) return null;
  const payload = code.slice(SCHEDULE_CONFLICT_DETAIL_PREFIX.length);
  const match = /^row=(\d+);staff_id=(\d+);own=([^~;]+)~([^;]+);peer=([^~;]+)~([^;]+);case_no=(.*)$/.exec(payload);
  if (!match) return REASON_LABELS.historical_order_source_schedule_conflict;
  const [, peerRow, staffId, ownStart, ownEnd, peerStart, peerEnd, peerCaseNo] = match;
  return `與 Excel 第 ${peerRow} 列（案件 ${peerCaseNo || '未提供'}，${peerStart}～${peerEnd}）同一月嫂（ID ${staffId}）服務期間（${ownStart}～${ownEnd}）重疊`;
}

// Only receipt-owned codes determine guidance; never infer a historical failure from current data.
const HCM_PROBLEMS: Record<string, { field: string; reason: string }> = {
  'hcm_case_import:case_import_case_no_required': {
    field: '查詢序號(案件編號)', reason: '【修正匯入資料】缺少可用的案件編號；請補齊「查詢序號(案件編號)」。',
  },
  hcm_bootstrap_rate_policy_missing: {
    field: '薪資費率政策', reason: '【檢查系統設定】找不到適用的薪資費率政策；請管理員確認案件身分與預計服務日期有適用的費率版本。',
  },
  hcm_bootstrap_rate_policy_not_effective: {
    field: '薪資費率政策生效期間', reason: '【核對資料／系統設定】指定薪資費率政策不適用此案；請先核對預計服務日期，若正確，請管理員確認政策版本、身分及生效期間。',
  },
  hcm_bootstrap_identity_policy_unmapped: {
    field: '身分資格／薪資政策對應', reason: '【檢查系統設定】身分資格尚未對應薪資政策；請管理員確認此身分的政策對應。',
  },
  hcm_bootstrap_planned_start_missing: {
    field: '預計服務日期', reason: '【修正匯入資料】缺少預計服務日期；請補齊有效日期。',
  },
  hcm_bootstrap_deposit_days_exceed_service_days: {
    field: '希望服務天數／訂金天數', reason: '【核對資料／系統設定】訂金天數超過服務天數；請先核對「希望服務天數」，若正確，請管理員確認短天數案件的訂金規則。',
  },
  hcm_bootstrap_deposit_days_identity_mismatch: {
    field: '身分資格／訂金設定', reason: '【核對資料／系統設定】訂金天數不符合身分政策；請先核對身分資格，若正確，請管理員檢查訂金規則。',
  },
  hcm_bootstrap_deposit_due_after_service_start: {
    field: '訂金到期日／服務開始日', reason: '【系統人員處理】訂金到期日晚於服務開始日；請檢查建案時的訂金日期計算，勿為通過檢查而更改正確的服務日期。',
  },
  hcm_bootstrap_payment_start_mismatch: {
    field: '首期繳款日／服務開始日', reason: '【系統人員處理】首期繳款日與服務開始日不一致；請檢查建案時的繳款日期計算。',
  },
  hcm_bootstrap_unexpected_second_payment: {
    field: '第二期繳款設定', reason: '【系統人員處理】尚未結算首期，不能建立第二期繳款日；請檢查建案時的繳款設定。',
  },
  hcm_bootstrap_payroll_policy_identity_mismatch: {
    field: '身分資格／薪資政策', reason: '【核對資料／系統設定】薪資政策與身分資格不符；請先核對身分資格，若正確，請管理員檢查政策對應。',
  },
  hcm_bootstrap_existing_state_conflict: {
    field: '既有案件建檔資料', reason: '【檢查既有資料】既有案件初始化資料不完整或與主檔衝突；請系統人員核對該案件的建檔狀態，勿直接覆寫既有資料。',
  },
  hcm_bootstrap_service_days_invalid: {
    field: '希望服務天數', reason: '【修正匯入資料】服務天數不符合建案規則；請核對「希望服務天數」是否為有效正整數。',
  },
  hcm_bootstrap_service_hours_invalid: {
    field: '服務時間（每日時數）', reason: '【核對資料／系統規則】每日服務時數不符合建案規則；請先核對「服務時間」，若為正確的半小時等服務需求，請系統人員確認建案規則。',
  },
  hcm_bootstrap_rule_blocked: {
    field: '案件建檔規則', reason: '【系統人員查核】案件初始化未通過業務規則，收據未保存更細原因；無法判定應修資料或系統設定，請依案件編號與來源資料序號查核。',
  },
  'hcm_case_import:case_import_bootstrap_blocked': {
    field: '案件建檔設定', reason: '【系統人員查核】案件建檔設定檢查未通過；當時未保存詳細原因，無法判定應修資料或系統設定，請依案件編號與來源資料序號查核。',
  },
  'hcm_case_import:case_import_duplicate': {
    field: '查詢序號(案件編號)／既有案件', reason: '【檢查既有資料】案件編號已存在，無法再次新建；請核對是否重複匯入，不要任意改號重建。',
  },
  'hcm_case_import:case_import_existing_source_conflict': {
    field: '案件編號／來源資料', reason: '【檢查既有資料】同一案件已有不同來源內容；請核對原始匯入紀錄與本次檔案。',
  },
  'hcm_case_import:invalid_case_import_root_facts': {
    field: '案件建檔資料', reason: '【系統人員查核】案件建檔資料未通過內部一致性檢查；收據未保存具體欄位原因，請依案件編號與來源資料序號查核。',
  },
  'hcm_case_import:provisional_registration_not_found': {
    field: '待核准需求關聯', reason: '【檢查既有資料】找不到對應的待核准需求；請核對該筆需求是否仍存在及其案件關聯。',
  },
  'hcm_case_import:provisional_registration_not_submitted': {
    field: '待核准需求狀態', reason: '【檢查既有資料】對應需求尚未提交；請先確認需求狀態。',
  },
  'hcm_case_import:provisional_registration_identity_mismatch': {
    field: '待核准需求身分／關聯', reason: '【檢查既有資料】對應需求的身分或關聯資料不一致，無法安全建案；請核對需求與客戶資料，不要任意修改身分以通過檢查。',
  },
  'hcm_case_import:transaction_failed': {
    field: '系統寫入', reason: '【系統人員處理】案件寫入失敗並已回滾；請檢查資料庫連線與寫入紀錄，此訊息不代表 Excel 欄位填錯。',
  },
};

function hcmProblem(code: string): { field: string; reason: string } {
  if (HCM_PROBLEMS[code]) return HCM_PROBLEMS[code];
  const [kind, field] = code.split(':');
  if ((kind === 'hcm_field_missing' || kind === 'hcm_field_invalid') && field) {
    const label = field === 'email' ? '電子郵件' : field;
    return { field: label, reason: `【修正匯入資料】${label}：${kind === 'hcm_field_missing' ? '必填資料缺漏，請補齊' : '資料格式錯誤，請核對格式及內容'}。` };
  }
  return { field: '案件匯入（需查核）', reason: `【系統人員查核】${code === 'review_required' || code === 'failed' ? '當時未保存詳細原因' : '無法辨識此匯入錯誤'}，無法判定應修資料或系統設定；請提供案件編號、來源資料序號及錯誤代碼：${code}。` };
}

function hcmRowProblems(row: HcmWorkbookRowOutcome): { fields: string[]; reasons: string[] } {
  // Detailed bootstrap reasons refine the generic issue; unrelated issues must remain visible.
  const codes = [...(row.reason_codes ?? []), ...row.issue_codes.filter(code =>
    code !== 'hcm_case_import:case_import_bootstrap_blocked' || !row.reason_codes?.some(reason => reason.startsWith('hcm_bootstrap_')))];
  const problems = (codes.length ? codes : [row.outcome]).map(hcmProblem);
  const sourceFields = row.problem_fields.filter(field => field !== 'case_import' && field !== 'hcm_identity')
    .map(field => field === 'email' ? '電子郵件' : field);
  return {
    fields: [...new Set([...sourceFields, ...problems.map(problem => problem.field)])],
    reasons: [...new Set(problems.map(problem => problem.reason))],
  };
}

function reasonLabel(code: string): string {
  const conflictDetail = parseScheduleConflictDetail(code);
  if (conflictDetail !== null) return conflictDetail;
  if (REASON_LABELS[code]) return REASON_LABELS[code];
  const [kind, field] = code.split(':');
  if (kind.endsWith('_field_missing')) return `${field}：必填資料缺漏`;
  if (kind.endsWith('_field_invalid')) return `${field}：資料格式錯誤`;
  return `資料未通過匯入檢查（${code}）`;
}

function historicalOrderRowReasons(issueCodes: ReadonlyArray<string>): string[] {
  const hasConflictDetail = issueCodes.some(code => code.startsWith(SCHEDULE_CONFLICT_DETAIL_PREFIX));
  const filtered = hasConflictDetail
    ? issueCodes.filter(code => code !== 'historical_order_source_schedule_conflict')
    : issueCodes;
  return [...new Set(filtered.map(reasonLabel))];
}

function result(sourceCount: number, importedCount: number, duplicateCount: number, notImportedCount: number, replayedWorkbook: boolean, notImportedRows: WorkbookImportResult['notImportedRows'] = null): WorkbookImportResult {
  if (![sourceCount, importedCount, duplicateCount, notImportedCount].every(value => Number.isInteger(value) && value >= 0)
    || importedCount + duplicateCount + notImportedCount !== sourceCount
    || (notImportedRows !== null && notImportedRows.length !== notImportedCount)) {
    throw Object.assign(new Error('匯入結果筆數不一致，暫時無法確認結果。'), { retryable: true });
  }
  return { sourceCount, importedCount, duplicateCount, notImportedCount, replayedWorkbook, notImportedRows };
}

export function adaptHcmImportResult(receipt: HcmWorkbookReceipt): WorkbookImportResult {
  return result(receipt.source_row_count,
    receipt.inserted_count + receipt.inserted_with_warning_count + (receipt.email_filled_count ?? 0),
    receipt.exact_replay_count + receipt.skipped_existing_count,
    receipt.review_required_count + receipt.failed_count, receipt.replayed_workbook,
    receipt.row_outcomes_available && !receipt.legacy_summary_only
      ? receipt.row_outcomes.filter(row => row.outcome === 'review_required' || row.outcome === 'failed')
        .map(row => ({ sourceRow: row.source_row, identifier: row.case_no, ...hcmRowProblems(row) }))
      : null);
}

export function adaptClientBeClassImportResult(receipt: ClientBeClassWorkbookReceipt): WorkbookImportResult {
  return result(receipt.source_row_count, receipt.created_count,
    receipt.exact_replay_count + receipt.existing_source_count,
    receipt.review_required_count + receipt.existing_conflict_count, receipt.replayed_workbook,
    receipt.row_issues?.map(row => ({ sourceRow: row.source_row, identifier: row.query_no, fields: row.fields, reasons: row.issue_codes.map(reasonLabel) })) ?? null);
}

export function adaptStaffHistoricalImportResult(receipt: StaffHistoricalWorkbookReceipt): WorkbookImportResult {
  return result(receipt.source_row_count, receipt.created_count + receipt.adopted_existing_count,
    receipt.exact_replay_count, receipt.blocked_identity_count + receipt.identity_conflict_count,
    receipt.replayed_workbook,
    receipt.row_issues?.map(row => ({ sourceRow: row.source_row, identifier: null, fields: row.fields, reasons: row.issue_codes.map(reasonLabel) })) ?? null);
}

export function adaptHistoricalOrderImportResult(receipt: HistoricalOrderWorkbookReceipt): WorkbookImportResult {
  const rows = receipt.row_issues?.map(row => ({ sourceRow: row.source_row, identifier: row.case_no, fields: row.fields, reasons: historicalOrderRowReasons(row.issue_codes) })) ?? null;
  if (receipt.import_counts) {
    return result(receipt.source_row_count, receipt.import_counts.imported_count,
      receipt.import_counts.duplicate_skipped_count, receipt.import_counts.not_imported_count,
      receipt.replayed_workbook,
      rows);
  }
  // Old receipts with mixed row replay do not identify which outcomes overlapped.
  if (receipt.replayed_rows > 0) {
    return { sourceCount: receipt.source_row_count, importedCount: null, duplicateCount: null, notImportedCount: null, replayedWorkbook: receipt.replayed_workbook, notImportedRows: null };
  }
  return result(receipt.source_row_count, receipt.adopted_count, 0,
    receipt.source_row_count - receipt.adopted_count, receipt.replayed_workbook, rows);
}
