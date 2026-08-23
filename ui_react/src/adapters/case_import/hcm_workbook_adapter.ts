/**
 * File: hcm_workbook_adapter.ts
 * Description: 將 HCM Preview aggregate 轉為顯示模型，並拒絕不守恆的伺服器計數。
 */
import { HcmWorkbookContractError } from '../../api/case_import/hcm_workbook_errors';
import type { HcmWorkbookPreview } from '../../api/case_import/hcm_workbook_schemas';

export const HCM_WORKBOOK_ROW_DETAIL_UNAVAILABLE =
  'Preview 顯示批次統計；逐列結果會在匯入完成後列出。';

export interface HcmWorkbookPreviewModel {
  sourceContentDigest: string;
  sourceRowCount: number;
  readyCount: number;
  readyWithWarningCount: number;
  reviewRequiredCount: number;
  previewFingerprint: string;
  rowDetailUnavailableMessage: string;
}

export function adaptHcmWorkbookPreview(
  preview: HcmWorkbookPreview
): HcmWorkbookPreviewModel {
  const total =
    preview.ready_count +
    preview.ready_with_warning_count +
    preview.review_required_count;
  if (total !== preview.source_row_count) {
    throw new HcmWorkbookContractError(
      'hcm_preview_row_outcomes_not_conserved',
      'HCM Preview aggregate 計數不守恆，預覽已拒絕。'
    );
  }
  return {
    sourceContentDigest: preview.source_content_digest,
    sourceRowCount: preview.source_row_count,
    readyCount: preview.ready_count,
    readyWithWarningCount: preview.ready_with_warning_count,
    reviewRequiredCount: preview.review_required_count,
    previewFingerprint: preview.preview_fingerprint,
    rowDetailUnavailableMessage: HCM_WORKBOOK_ROW_DETAIL_UNAVAILABLE,
  };
}
