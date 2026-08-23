/**
 * File: staff_historical_workbook_adapter.ts
 * Description: 將Staff Historical Preview aggregate轉成顯示模型並拒絕不守恆計數。
 */
import { StaffHistoricalWorkbookContractError } from '../../api/case_import/staff_historical_workbook/errors';
import type { StaffHistoricalWorkbookPreview } from '../../api/case_import/staff_historical_workbook/schemas';

export interface StaffHistoricalWorkbookPreviewModel {
  sourceContentDigest: string;
  sourceRowCount: number;
  createdCount: number;
  adoptedExistingCount: number;
  blockedIdentityCount: number;
  identityConflictCount: number;
  reviewRequiredCount: number;
  previewFingerprint: string;
}

export function adaptStaffHistoricalWorkbookPreview(
  preview: StaffHistoricalWorkbookPreview
): StaffHistoricalWorkbookPreviewModel {
  const total = preview.created_count + preview.adopted_existing_count + preview.blocked_identity_count + preview.identity_conflict_count;
  if (total !== preview.source_row_count) {
    throw new StaffHistoricalWorkbookContractError('staff_historical_row_outcomes_not_conserved', 'Staff Historical Preview aggregate計數不守恆。');
  }
  return {
    sourceContentDigest: preview.source_content_digest,
    sourceRowCount: preview.source_row_count,
    createdCount: preview.created_count,
    adoptedExistingCount: preview.adopted_existing_count,
    blockedIdentityCount: preview.blocked_identity_count,
    identityConflictCount: preview.identity_conflict_count,
    reviewRequiredCount: preview.review_required_count,
    previewFingerprint: preview.preview_fingerprint,
  };
}
