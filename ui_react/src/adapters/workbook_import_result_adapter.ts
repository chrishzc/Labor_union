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
}

function result(sourceCount: number, importedCount: number, duplicateCount: number, notImportedCount: number, replayedWorkbook: boolean): WorkbookImportResult {
  if (![sourceCount, importedCount, duplicateCount, notImportedCount].every(value => Number.isInteger(value) && value >= 0)
    || importedCount + duplicateCount + notImportedCount !== sourceCount) {
    throw Object.assign(new Error('匯入結果筆數不一致，暫時無法確認結果。'), { retryable: true });
  }
  return { sourceCount, importedCount, duplicateCount, notImportedCount, replayedWorkbook };
}

export function adaptHcmImportResult(receipt: HcmWorkbookReceipt): WorkbookImportResult {
  return result(receipt.source_row_count,
    receipt.inserted_count + receipt.inserted_with_warning_count + (receipt.email_filled_count ?? 0),
    receipt.exact_replay_count + receipt.skipped_existing_count,
    receipt.review_required_count + receipt.failed_count, receipt.replayed_workbook);
}

export function adaptClientBeClassImportResult(receipt: ClientBeClassWorkbookReceipt): WorkbookImportResult {
  return result(receipt.source_row_count, receipt.created_count,
    receipt.exact_replay_count + receipt.existing_source_count,
    receipt.review_required_count + receipt.existing_conflict_count, receipt.replayed_workbook);
}

export function adaptStaffHistoricalImportResult(receipt: StaffHistoricalWorkbookReceipt): WorkbookImportResult {
  return result(receipt.source_row_count, receipt.created_count + receipt.adopted_existing_count,
    receipt.exact_replay_count, receipt.blocked_identity_count + receipt.identity_conflict_count,
    receipt.replayed_workbook);
}

export function adaptHistoricalOrderImportResult(receipt: HistoricalOrderWorkbookReceipt): WorkbookImportResult {
  if (receipt.import_counts) {
    return result(receipt.source_row_count, receipt.import_counts.imported_count,
      receipt.import_counts.duplicate_skipped_count, receipt.import_counts.not_imported_count,
      receipt.replayed_workbook);
  }
  // Old receipts with mixed row replay do not identify which outcomes overlapped.
  if (receipt.replayed_rows > 0) {
    return { sourceCount: receipt.source_row_count, importedCount: null, duplicateCount: null, notImportedCount: null, replayedWorkbook: receipt.replayed_workbook };
  }
  return result(receipt.source_row_count, receipt.adopted_count, 0,
    receipt.source_row_count - receipt.adopted_count, receipt.replayed_workbook);
}
