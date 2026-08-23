/**
 * File: import_warning_transition_contract_fixtures.ts
 * Description: 提供匯入警示 transition Preview、Apply receipt 與錯誤契約測試向量。
 */

export const VALID_WARNING_TRANSITION_REQUEST = {
  expected_version: 7,
  target_status: 'awaiting_external_confirmation',
  reason_code: 'source_confirmation_required',
  note: '等待來源端確認欄位內容。',
  evidence_reference: 'evidence:warning-transition-001',
} as const;

export const VALID_WARNING_TRANSITION_PREVIEW = {
  occurrence_identity: 'import-warning:fixture-001',
  expected_version: 7,
  resulting_status: 'awaiting_external_confirmation',
  resulting_version: 8,
} as const;

export const VALID_WARNING_TRANSITION_RECEIPT = {
  occurrence_identity: 'import-warning:fixture-001',
  before_status: 'open',
  after_status: 'awaiting_external_confirmation',
  resulting_version: 8,
  receipt_identity: 'a'.repeat(64),
  correlation_id: 'phase3d-w-r-correlation-001',
  replayed: false,
} as const;

export const VALID_WARNING_TRANSITION_RECEIPT_REPLAY = {
  ...VALID_WARNING_TRANSITION_RECEIPT,
  replayed: true,
} as const;

export const VALID_WARNING_TRANSITION_PREVIEW_RESPONSE = {
  success: true,
  message: '匯入警示狀態已預覽',
  data: VALID_WARNING_TRANSITION_PREVIEW,
} as const;

export const VALID_WARNING_TRANSITION_RECEIPT_RESPONSE = {
  success: true,
  message: '匯入警示狀態已更新',
  data: VALID_WARNING_TRANSITION_RECEIPT,
} as const;

export const VALID_WARNING_TRANSITION_RECEIPT_LOOKUP_RESPONSE = {
  success: true,
  message: '成功取得匯入警示 transition receipt',
  data: VALID_WARNING_TRANSITION_RECEIPT_REPLAY,
} as const;

export const INVALID_WARNING_TRANSITION_PREVIEW_EXTRA_FIELD = {
  ...VALID_WARNING_TRANSITION_PREVIEW_RESPONSE,
  data: { ...VALID_WARNING_TRANSITION_PREVIEW, derived_label: '不要推導' },
} as const;

export const INVALID_WARNING_TRANSITION_RECEIPT_IDENTITY = {
  ...VALID_WARNING_TRANSITION_RECEIPT_RESPONSE,
  data: { ...VALID_WARNING_TRANSITION_RECEIPT, receipt_identity: 'A'.repeat(64) },
} as const;
