/**
 * File: hcm_import_result_adapter.ts
 * Description: 將 HCM receipt分組為本次新增、問題與replay，並拒絕不守恆或legacy假空結果。
 */
import { HcmImportResultError } from '../../api/case_import/hcm_import_result_errors';
import type { HcmImportResultRecord, HcmImportRowOutcome } from '../../api/case_import/hcm_import_result_schemas';

export interface HcmImportResultViewModel {
  receiptId: number;
  completedAt: string;
  digestShort: string;
  sourceRowCount: number;
  summary: string;
  rowOutcomesAvailable: boolean;
  newOrders: HcmImportRowOutcome[];
  problems: HcmImportRowOutcome[];
  replays: HcmImportRowOutcome[];
}

export function adaptHcmImportResult(record: HcmImportResultRecord): HcmImportResultViewModel {
  const total = record.inserted_count + record.inserted_with_warning_count + record.exact_replay_count + record.review_required_count + record.failed_count;
  if (total !== record.source_row_count) {
    throw new HcmImportResultError('hcm_result_counts_not_conserved', 'HCM 匯入結果計數不守恆。');
  }
  if (record.row_outcomes_available && record.row_outcomes.length !== record.source_row_count) {
    throw new HcmImportResultError('hcm_result_rows_not_conserved', 'HCM 匯入逐列結果不守恆。');
  }
  const rows = record.row_outcomes_available ? record.row_outcomes : [];
  return {
    receiptId: record.receipt_id,
    completedAt: record.completed_at,
    digestShort: `${record.source_content_digest.slice(0, 12)}…`,
    sourceRowCount: record.source_row_count,
    summary: `新增 ${record.inserted_count + record.inserted_with_warning_count}｜問題 ${record.review_required_count + record.inserted_with_warning_count + record.failed_count}｜Replay ${record.exact_replay_count}`,
    rowOutcomesAvailable: record.row_outcomes_available && !record.legacy_summary_only,
    newOrders: rows.filter((row) => row.outcome === 'inserted' || row.outcome === 'inserted_with_warning'),
    problems: rows.filter((row) => row.outcome === 'inserted_with_warning' || row.outcome === 'review_required' || row.outcome === 'failed'),
    replays: rows.filter((row) => row.outcome === 'exact_replay'),
  };
}
