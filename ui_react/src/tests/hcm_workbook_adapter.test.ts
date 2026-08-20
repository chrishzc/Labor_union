/**
 * File: hcm_workbook_adapter.test.ts
 * Description: 驗證 HCM aggregate Adapter 不推導逐列結果，且守恆失敗時拒絕呈現。
 */
import { describe, expect, it } from 'vitest';
import { HcmWorkbookContractError } from '../api/case_import/hcm_workbook_errors';
import {
  adaptHcmWorkbookPreview,
  HCM_WORKBOOK_ROW_DETAIL_UNAVAILABLE,
} from '../adapters/case_import/hcm_workbook_adapter';
import { HCM_WORKBOOK_PREVIEW_FIXTURE } from './fixtures/hcm_workbook_contract_fixtures';

describe('HCM workbook preview adapter', () => {
  it('逐欄映射 server aggregate，並保留逐列資料未開放訊息', () => {
    expect(adaptHcmWorkbookPreview(HCM_WORKBOOK_PREVIEW_FIXTURE)).toEqual({
      sourceContentDigest: HCM_WORKBOOK_PREVIEW_FIXTURE.source_content_digest,
      sourceRowCount: 4,
      readyCount: 2,
      readyWithWarningCount: 1,
      reviewRequiredCount: 1,
      previewFingerprint: HCM_WORKBOOK_PREVIEW_FIXTURE.preview_fingerprint,
      rowDetailUnavailableMessage: HCM_WORKBOOK_ROW_DETAIL_UNAVAILABLE,
    });
  });

  it('aggregate outcome 不守恆時 fail closed，不從計數猜測逐列結果', () => {
    expect(() =>
      adaptHcmWorkbookPreview({
        ...HCM_WORKBOOK_PREVIEW_FIXTURE,
        review_required_count: 0,
      })
    ).toThrow(HcmWorkbookContractError);
  });
});
