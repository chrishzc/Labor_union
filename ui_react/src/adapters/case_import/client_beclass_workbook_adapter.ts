/**
 * File: client_beclass_workbook_adapter.ts
 * Description: 將Client BeClass Preview aggregate轉成顯示模型並拒絕不守恆計數。
 */
import { ClientBeClassWorkbookContractError } from '../../api/case_import/client_beclass_workbook/errors';
import type { ClientBeClassWorkbookPreview } from '../../api/case_import/client_beclass_workbook/schemas';

export interface ClientBeClassWorkbookPreviewModel {
  sourceContentDigest: string;
  sheetIdentity: string;
  sourceRowCount: number;
  createCount: number;
  reviewRequiredCount: number;
  existingConflictCount: number;
  existingSourceCount: number;
  previewFingerprint: string;
}

export function adaptClientBeClassWorkbookPreview(
  preview: ClientBeClassWorkbookPreview
): ClientBeClassWorkbookPreviewModel {
  const total = preview.create_count + preview.review_required_count + preview.existing_conflict_count + preview.existing_source_count;
  if (total !== preview.source_row_count) {
    throw new ClientBeClassWorkbookContractError('client_beclass_row_outcomes_not_conserved', '客戶 BeClass Preview aggregate計數不守恆。');
  }
  return {
    sourceContentDigest: preview.source_content_digest,
    sheetIdentity: preview.sheet_identity,
    sourceRowCount: preview.source_row_count,
    createCount: preview.create_count,
    reviewRequiredCount: preview.review_required_count,
    existingConflictCount: preview.existing_conflict_count,
    existingSourceCount: preview.existing_source_count,
    previewFingerprint: preview.preview_fingerprint,
  };
}
