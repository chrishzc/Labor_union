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
  absentOrderCancellationCount?: number;
  manualBindings?: ClientBeClassWorkbookReceipt['manual_bindings'];
  requiresRepreview?: boolean;
  payrollIssues?: NonNullable<WorkbookImportResult["notImportedRows"]>;
  notImportedRows: Array<{ sourceRow: number; identifier: string | null; fields: string[]; reasons: string[] }> | null;
}

const REASON_LABELS: Record<string, string> = {
  client_beclass_source_payload_conflict: '同一查詢序號已有不同來源內容',
  client_case_binding_no_client: '姓名與電話找不到可配對的客戶',
  client_case_binding_multiple_clients: '姓名與電話對應多位客戶，無法確定對象',
  client_case_binding_case_not_unique: '客戶沒有唯一可配對案件',
  case_import_candidate_stale: '案件已無法綁定，請重新預覽後再選案',
  blocked_identity: '姓名或身分證字號缺漏／格式錯誤',
  identity_conflict: '身分資料與既有人員衝突，無法確定對象',
  unmatched_case: '找不到對應案件',
  current_conflict: '來源與目前案件資料衝突',
  review_required: '資料未通過匯入檢查',
  failed: '處理失敗',
  historical_payroll_unique_assignment_required: '需要唯一有效的歷史月嫂指派，請核對服務歸屬',
  historical_payroll_obligation_binding_conflict: '原應付與採納指派不一致，請核對月嫂與原款項',
  historical_payroll_original_payment_preserved: '原應付已付款或結清，保留原款項，請核對付款日期',
  historical_payroll_settled_source_required: '歷史帳務完成案缺少可證實的原應付來源',
  historical_payroll_service_basis_missing: '缺少服務天數、每日時數或有效服務結束日',
  payroll_rate_policy_not_found: '找不到可用的月嫂費率快照',
  historical_payroll_nonpositive_amount: '月嫂應付計算結果沒有正金額',
  historical_payroll_funding_conflict: '補助方案與既有帳務來源不一致，請核對款項歸屬',
  historical_service_not_completed: '案件尚未達歷史服務完成狀態',
  historical_case_no_missing: '缺少案件編號',
  historical_client_name_missing: '缺少客戶姓名',
  historical_status_invalid: '訂單狀態空白或格式錯誤',
  historical_staff_not_found: '找不到對應月嫂',
  historical_staff_ambiguous: '月嫂姓名對應多人，無法確定對象',
  historical_calendar_staff_missing: '缺少可採納的月嫂指派',
  historical_calendar_valid_dates_missing: '缺少有效的歷史服務起迄日期',
  historical_calendar_completed_assignment_missing: '缺少已完成的歷史服務指派',
  historical_order_source_schedule_conflict: '與同檔案其他案件的月嫂服務時段重疊',
  historical_order_source_schedule_unconfirmed: '原判定沒有留下具體的時段或服務日阻塞原因。',
  historical_service_time_unconfirmed: '原判定未記錄是服務起訖或跨日標記有問題。',
  historical_service_time_missing: '本列的服務時段儲存格沒有可讀取的值。請檢查是否空白，或公式結果尚未儲存。',
  historical_service_time_column_missing: '原匯入結果未取得可比對的歷史服務時段。標準六欄檔案可直接匯入。',
  historical_service_time_terms_unavailable: '對應訂單的服務開始、結束時間或跨日標記缺漏或無效。請核對訂單的服務時間。',
  historical_service_time_range_invalid: '本列「服務時間」無法解析成有效的開始與結束時間，例如 09:00–13:00(4小時)。',
  historical_service_time_start_invalid: '本列「服務開始時間」不是有效的時間。',
  historical_service_time_end_invalid: '本列「服務結束時間」不是有效的時間。',
  historical_service_time_offset_invalid: '本列「跨日標記」必須為 0（當天）或 1（次日）。',
  historical_service_time_split_incomplete: '本列使用分欄格式，但沒有同時提供「服務開始時間」和「服務結束時間」。',
  historical_service_time_columns_conflict: '本列的服務時間欄位互相矛盾，起訖或跨日標記不一致。',
  historical_service_time_overnight_missing: '本列結束時間早於開始時間。若是跨夜班，請在結束時間前加「次日」，或把「跨日標記」設為 1。',
  historical_service_time_interval_empty: '本列開始與結束時間相同，且沒有跨日，服務區間為零。',
};

const SCHEDULE_CONFLICT_DETAIL_PREFIX = 'historical_order_source_schedule_conflict_detail:';
const SCHEDULE_UNCONFIRMED_DETAIL_PREFIX = 'historical_order_source_schedule_unconfirmed_detail:';

function parseScheduleConflictDetail(code: string): string | null {
  const unconfirmed = code.startsWith(SCHEDULE_UNCONFIRMED_DETAIL_PREFIX);
  if (!unconfirmed && !code.startsWith(SCHEDULE_CONFLICT_DETAIL_PREFIX)) return null;
  const payload = code.slice((unconfirmed ? SCHEDULE_UNCONFIRMED_DETAIL_PREFIX : SCHEDULE_CONFLICT_DETAIL_PREFIX).length);
  const match = /^row=(\d+);staff_id=(\d+);own=([^~;]+)~([^;]+);peer=([^~;]+)~([^;]+);case_no=([^;]*)(?:;overlap=([^~;]+)~([^;]+))?(?:;reason=(own_time|peer_time|both_times|service_dates))?$/.exec(payload);
  if (!match) return '原判定沒有可辨識的衝突明細，無法指出具體阻塞原因。';
  const [, peerRow, , , , peerStart, peerEnd, peerCaseNo, overlapStart, overlapEnd, reason] = match;
  if (!unconfirmed && overlapStart && overlapEnd) return `與 Excel 第 ${peerRow} 列（案件 ${peerCaseNo}）重疊 ${overlapStart.slice(0, 16).replace('T', ' ')}～${overlapEnd.slice(0, 16).replace('T', ' ')}。`;
  const peer = `Excel 第 ${peerRow} 列（案件 ${peerCaseNo || '未提供'}，${peerStart}～${peerEnd}）`;
  switch (reason) {
    case 'own_time': return `本列的服務時段無法確認，與 ${peer}的日期有交集，無法比對。`;
    case 'peer_time': return `${peer}的服務時段無法確認，請查看該列原因。`;
    case 'both_times': return `本列與 ${peer}都無法確認服務時段，且日期有交集。`;
    case 'service_dates': return `與 ${peer}的時段可能重疊，但缺少實際服務日資料，無法確認兩班是否在同一時刻出勤。`;
    default: return `原判定只記錄與 ${peer}的日期範圍，沒有留下具體時段或服務日原因。`;
  }
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
  const filtered = issueCodes.filter(code => !(
    (code === 'historical_order_source_schedule_conflict' || code === 'historical_order_source_schedule_unconfirmed')
    && issueCodes.some(detail => detail.startsWith(`${code}_detail:`))
  ));
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
  const summary = result(receipt.source_row_count, receipt.created_count,
    receipt.exact_replay_count + receipt.existing_source_count,
    receipt.review_required_count + receipt.existing_conflict_count, receipt.replayed_workbook,
    receipt.row_issues?.map(row => ({ sourceRow: row.source_row, identifier: row.query_no, fields: row.fields, reasons: row.issue_codes.map(reasonLabel) })) ?? null);
  return {
    ...summary,
    manualBindings: receipt.manual_bindings ?? [],
    requiresRepreview: receipt.row_issues?.some(row => row.issue_codes.includes('case_import_candidate_stale')),
  };
}

export function adaptStaffHistoricalImportResult(receipt: StaffHistoricalWorkbookReceipt): WorkbookImportResult {
  return result(receipt.source_row_count, receipt.created_count + receipt.adopted_existing_count,
    receipt.exact_replay_count, receipt.blocked_identity_count + receipt.identity_conflict_count,
    receipt.replayed_workbook,
    receipt.row_issues?.map(row => ({ sourceRow: row.source_row, identifier: null, fields: row.fields, reasons: row.issue_codes.map(reasonLabel) })) ?? null);
}

export function adaptHistoricalOrderImportResult(receipt: HistoricalOrderWorkbookReceipt): WorkbookImportResult {
  const rows = receipt.row_issues?.map(row => ({ sourceRow: row.source_row, identifier: row.case_no, fields: row.fields, reasons: historicalOrderRowReasons(row.issue_codes) })) ?? null;
  const payrollIssues = receipt.payroll_issues?.map(row => ({
    sourceRow: row.source_row, identifier: row.case_no, fields: row.fields,
    reasons: historicalOrderRowReasons(row.issue_codes),
  }));
  const absentOrderCancellationCount = receipt.absent_order_cancellation_count;
  if (receipt.import_counts) {
    return { ...result(receipt.source_row_count, receipt.import_counts.imported_count,
      receipt.import_counts.duplicate_skipped_count, receipt.import_counts.not_imported_count,
      receipt.replayed_workbook,
      rows), absentOrderCancellationCount, payrollIssues };
  }
  // Old receipts with mixed row replay do not identify which outcomes overlapped.
  if (receipt.replayed_rows > 0) {
    return { sourceCount: receipt.source_row_count, importedCount: null, duplicateCount: null, notImportedCount: null, replayedWorkbook: receipt.replayed_workbook, notImportedRows: null, absentOrderCancellationCount, payrollIssues };
  }
  return { ...result(receipt.source_row_count, receipt.adopted_count, 0,
    receipt.source_row_count - receipt.adopted_count, receipt.replayed_workbook, rows), absentOrderCancellationCount, payrollIssues };
}
