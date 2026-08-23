/**
 * File: historical_order_workbook_adapter.ts
 * Description: 投影Historical Orders Preview，依互斥terminal結果守恆並保留review overlay。
 */
import { HistoricalOrderWorkbookContractError } from '../../api/orders/historical_order_workbook/errors';
import type { HistoricalOrderWorkbookPreview } from '../../api/orders/historical_order_workbook/schemas';

export interface HistoricalOrderWorkbookPreviewModel {
  sourceContentDigest: string;
  sheetIdentity: string;
  sourceRowCount: number;
  adoptedCount: number;
  unmatchedCaseCount: number;
  reviewRequiredCount: number;
  currentConflictCount: number;
  assignmentCandidateCount: number;
  evidenceOnlyPairingCount: number;
  previewFingerprint: string;
}

export function adaptHistoricalOrderWorkbookPreview(
  preview: HistoricalOrderWorkbookPreview
): HistoricalOrderWorkbookPreviewModel {
  const primaryTotal = preview.adopted_count + preview.unmatched_case_count + preview.current_conflict_count;
  if (primaryTotal !== preview.source_row_count) {
    throw new HistoricalOrderWorkbookContractError('historical_order_row_outcomes_not_conserved', 'Historical Orders Preview主要結果計數不守恆。');
  }
  if (preview.assignment_candidate_count + preview.evidence_only_pairing_count > preview.adopted_count) {
    throw new HistoricalOrderWorkbookContractError('historical_order_pairing_counts_exceed_adopted', 'Historical Orders配對分類超過已認領筆數。');
  }
  return {
    sourceContentDigest: preview.source_content_digest,
    sheetIdentity: preview.sheet_identity,
    sourceRowCount: preview.source_row_count,
    adoptedCount: preview.adopted_count,
    unmatchedCaseCount: preview.unmatched_case_count,
    reviewRequiredCount: preview.review_required_count,
    currentConflictCount: preview.current_conflict_count,
    assignmentCandidateCount: preview.assignment_candidate_count,
    evidenceOnlyPairingCount: preview.evidence_only_pairing_count,
    previewFingerprint: preview.preview_fingerprint,
  };
}
