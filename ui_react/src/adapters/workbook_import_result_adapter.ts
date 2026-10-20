import type { HcmWorkbookReceipt } from '../api/case_import/hcm_workbook_schemas';
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
  'hcm_case_import:case_import_case_no_required': '缺少可用的案件編號',
  hcm_bootstrap_rate_policy_missing: '找不到適用的薪資費率政策',
  hcm_bootstrap_rate_policy_not_effective: '薪資費率政策尚未生效',
  hcm_bootstrap_identity_policy_unmapped: '身分資格尚未對應薪資政策',
  hcm_bootstrap_planned_start_missing: '缺少預計服務日期',
  hcm_bootstrap_deposit_days_exceed_service_days: '訂金天數超過服務天數',
  hcm_bootstrap_deposit_days_identity_mismatch: '訂金天數不符合身分政策',
  hcm_bootstrap_deposit_due_after_service_start: '訂金到期日晚於服務開始日',
  hcm_bootstrap_payment_start_mismatch: '首期繳款日與服務開始日不一致',
  hcm_bootstrap_unexpected_second_payment: '尚未結算首期，不能建立第二期繳款日',
  hcm_bootstrap_payroll_policy_identity_mismatch: '薪資政策與身分資格不符',
  hcm_bootstrap_existing_state_conflict: '既有案件初始化資料不完整或與主檔衝突',
  hcm_bootstrap_service_days_invalid: '服務天數不符合建案規則',
  hcm_bootstrap_service_hours_invalid: '每日服務時數不符合建案規則',
  hcm_bootstrap_rule_blocked: '案件初始化未通過業務規則',
};

function reasonLabel(code: string): string {
  if (REASON_LABELS[code]) return REASON_LABELS[code];
  const [kind, field] = code.split(':');
  if (kind.endsWith('_field_missing')) return `${field}：必填資料缺漏`;
  if (kind.endsWith('_field_invalid')) return `${field}：資料格式錯誤`;
  return `資料未通過匯入檢查（${code}）`;
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
        .map(row => ({ sourceRow: row.source_row, identifier: row.case_no, fields: row.problem_fields,
          reasons: (row.reason_codes?.length ? row.reason_codes : row.issue_codes.length ? row.issue_codes : [row.outcome]).map(reasonLabel) }))
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
  const rows = receipt.row_issues?.map(row => ({ sourceRow: row.source_row, identifier: row.case_no, fields: row.fields, reasons: row.issue_codes.map(reasonLabel) })) ?? null;
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
