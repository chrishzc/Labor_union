/**
 * File: hcm_workbook_contract_fixtures.ts
 * Description: 提供去敏 HCM Preview 成功信封與嚴格 decoder 的最小測試資料。
 */
export const HCM_WORKBOOK_PREVIEW_FIXTURE = {
  source_content_digest:
    '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
  source_row_count: 4,
  ready_count: 2,
  ready_with_warning_count: 1,
  review_required_count: 1,
  preview_fingerprint:
    'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789',
};

export const HCM_WORKBOOK_PREVIEW_ENVELOPE_FIXTURE = {
  success: true,
  message: 'HCM workbook Preview 已完成',
  data: HCM_WORKBOOK_PREVIEW_FIXTURE,
  error: null,
};
