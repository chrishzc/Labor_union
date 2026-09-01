/**
 * File: anomaly_query_contract_fixtures.ts
 * Description: Anomalies list、detail、referral 的測試向量。
 */

import type {
  AnomalySummaryView,
  ImportWarningTaskView,
  AnomalySummariesResponse,
  ImportWarningTasksResponse,
  AnomalyDetailView,
  ImportWarningReferralView,
} from '../../../api/anomalies/anomaly_query_schemas';

// ============================================================================
// 1. Valid Positive Domain Models & Responses
// ============================================================================

export const VALID_ANOMALY_SUMMARY_1: AnomalySummaryView = {
  fingerprint: '8f48483d980d2105151522a36a7f05ee461e78a63574a3f1244d2d6c66cf17f8',
  issue_key: `ci_${'1'.repeat(64)}`,
  definition_code: 'LINE-006',
  source_domain: 'line_integration',
  source_identity: 'case:CASE-102',
  source_version: 2,
  severity: 'blocking',
  predicate_active: true,
  workflow_status: 'open',
  workflow_version: 0,
  display_snapshot: null,
  staff_calendar_navigation: {
    staff_id: 14,
    target_date: '2026-08-20',
  },
};

export const VALID_ANOMALY_SUMMARY_2: AnomalySummaryView = {
  fingerprint: '1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f90123456789abcdef0123456789a',
  issue_key: `ci_${'2'.repeat(64)}`,
  definition_code: 'LINE-006',
  source_domain: 'line_integration',
  source_identity: 'case:CASE-501',
  source_version: 1,
  severity: 'warning',
  predicate_active: true,
  workflow_status: 'claimed',
  workflow_version: 1,
  display_snapshot: null,
  staff_calendar_navigation: null,
};

export const VALID_ANOMALY_SUMMARY_3: AnomalySummaryView = {
  fingerprint: 'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789',
  issue_key: `ci_${'3'.repeat(64)}`,
  definition_code: 'LINE-006',
  source_domain: 'line_integration',
  source_identity: 'case:CASE-88',
  source_version: 3,
  severity: 'warning',
  predicate_active: false,
  workflow_status: 'resolved',
  workflow_version: 2,
  display_snapshot: null,
  staff_calendar_navigation: null,
};

export const VALID_ANOMALIES_QUERY_RESPONSE: AnomalySummariesResponse = {
  success: true,
  message: '成功取得異常摘要',
  data: [
    VALID_ANOMALY_SUMMARY_1,
    VALID_ANOMALY_SUMMARY_2,
    VALID_ANOMALY_SUMMARY_3,
  ],
  error: null,
};

export const VALID_EMPTY_ANOMALIES_QUERY_RESPONSE: AnomalySummariesResponse = {
  success: true,
  message: '查無異常記錄',
  data: [],
  error: null,
};

// ----------------------------------------------------------------------------
// Import Warning Tasks Fixtures
// ----------------------------------------------------------------------------

export const VALID_IMPORT_WARNING_TASK_HCM: ImportWarningTaskView = {
  occurrence_identity: 'import-warning:3a7e4f9b8c0d1e2f3a4b5c6d7e8f9012',
  owning_lane: 'hcm',
  logical_code: 'HCM-FIELD-001',
  field_path: '身分證字號',
  masked_subject: 'A12****789',
  issue_codes: ['hcm_field_missing:身分證字號'],
  tracking_status: 'open',
  tracking_version: 1,
  evidence_reference: 'batch-20260816-01',
  display_message: '缺少身分證字號',
  navigation_action: 'hcm_import_center',
};

export const VALID_IMPORT_WARNING_TASK_BECLASS_CLI: ImportWarningTaskView = {
  occurrence_identity: 'import-warning:beclass-cli-002',
  owning_lane: 'client_beclass',
  logical_code: 'BECLASS-CLI-002',
  field_path: '聯絡電話',
  masked_subject: '0912****78',
  issue_codes: ['beclass_phone_format_invalid'],
  tracking_status: 'awaiting_external_confirmation',
  tracking_version: 2,
  evidence_reference: null,
  display_message: 'BeClass 客戶聯絡電話格式不符',
  navigation_action: 'client_beclass_import_center',
};

export const VALID_IMPORT_WARNING_TASK_HISTORICAL: ImportWarningTaskView = {
  occurrence_identity: 'import-warning:hist-ord-003',
  owning_lane: 'historical_order',
  logical_code: 'HIST-ORD-003',
  field_path: '歷史服務金額',
  masked_subject: 'CASE-2024-999',
  issue_codes: ['hist_amount_mismatch'],
  tracking_status: 'response_recorded',
  tracking_version: 3,
  evidence_reference: 'hist-batch-99',
  display_message: '歷史匯入金額計算差異',
  navigation_action: 'historical_order_import_center',
};

export const VALID_IMPORT_WARNING_TASK_BECLASS_STF: ImportWarningTaskView = {
  occurrence_identity: 'import-warning:beclass-stf-004',
  owning_lane: 'staff_beclass',
  logical_code: 'BECLASS-STF-004',
  field_path: '服務證號',
  masked_subject: 'STF-****',
  issue_codes: ['beclass_staff_cert_missing'],
  tracking_status: 'reimport_requested',
  tracking_version: 1,
  evidence_reference: null,
  display_message: '月嫂服務證號遺漏需重新匯入',
  navigation_action: 'staff_beclass_import_center',
};

export const VALID_IMPORT_WARNING_TASK_FINANCE: ImportWarningTaskView = {
  occurrence_identity: 'import-warning:fin-005',
  owning_lane: 'finance',
  logical_code: 'FIN-IMP-005',
  field_path: '銀行交易代碼',
  masked_subject: 'TX-****-1234',
  issue_codes: ['fin_bank_tx_unknown'],
  tracking_status: 'closed',
  tracking_version: 4,
  evidence_reference: 'bank-stmt-202608',
  display_message: '銀行流水對帳完成並關閉追蹤',
  navigation_action: 'finance_import_recovery_center',
};

export const VALID_IMPORT_WARNING_TASK_AUTO_RESOLVED: ImportWarningTaskView = {
  occurrence_identity: 'import-warning:auto-006',
  owning_lane: 'hcm',
  logical_code: 'HCM-AUTO-006',
  field_path: '地址欄位',
  masked_subject: '台北市****',
  issue_codes: ['hcm_address_repaired'],
  tracking_status: 'auto_resolved',
  tracking_version: 2,
  evidence_reference: 'auto-repair-job-42',
  display_message: '地址已於後續匯入自動校正修復',
  navigation_action: null,
};

export const VALID_IMPORT_WARNING_TASKS_RESPONSE: ImportWarningTasksResponse = {
  success: true,
  message: '成功取得匯入警示追蹤清單',
  data: [
    VALID_IMPORT_WARNING_TASK_HCM,
    VALID_IMPORT_WARNING_TASK_BECLASS_CLI,
    VALID_IMPORT_WARNING_TASK_HISTORICAL,
    VALID_IMPORT_WARNING_TASK_BECLASS_STF,
    VALID_IMPORT_WARNING_TASK_FINANCE,
    VALID_IMPORT_WARNING_TASK_AUTO_RESOLVED,
  ],
  error: null,
};

export const VALID_EMPTY_IMPORT_WARNING_TASKS_RESPONSE: ImportWarningTasksResponse = {
  success: true,
  message: '目前無未解決匯入警示',
  data: [],
  error: null,
};

export const VALID_ANOMALY_DETAIL_VIEW: AnomalyDetailView = {
  summary: VALID_ANOMALY_SUMMARY_1,
  timeline: [
    {
      action: 'reopen',
      expected_workflow_version: 1,
      resulting_workflow_version: 2,
      actor: 'anomaly-projector',
      reason: 'Root condition is active; workflow reopened.',
      correlation_id: 'anomaly-detail-correlation',
      created_at: '2026-08-17T09:00:00+08:00',
    },
  ],
  available_actions: [],
};

export const VALID_IMPORT_WARNING_REFERRAL_VIEW: ImportWarningReferralView = {
  occurrence_identity: VALID_IMPORT_WARNING_TASK_HCM.occurrence_identity,
  expected_version: VALID_IMPORT_WARNING_TASK_HCM.tracking_version,
  owning_lane: 'hcm',
  logical_code: VALID_IMPORT_WARNING_TASK_HCM.logical_code,
  field_path: VALID_IMPORT_WARNING_TASK_HCM.field_path,
  masked_subject: VALID_IMPORT_WARNING_TASK_HCM.masked_subject,
  display_message: VALID_IMPORT_WARNING_TASK_HCM.display_message,
  navigation_action: 'hcm_import_center',
  action_kind: 'owner_preview_apply',
  target_command: 'preview_hcm_resubmission',
};

// ============================================================================
// 2. Negative & Adversarial Malformed Test Vectors
// ============================================================================

/**
 * 異常資料缺少必要欄位 (fingerprint)
 */
export const INVALID_ANOMALY_MISSING_FINGERPRINT = {
  definition_code: 'SCHEDULE-001',
  source_domain: 'scheduling',
  source_identity: 'assignment:102',
  source_version: 2,
  severity: 'blocking',
  predicate_active: true,
  workflow_status: 'open',
  workflow_version: 0,
};

/**
 * 異常資料 fingerprint 長度或格式不合法 (非 64 位十六進位)
 */
export const INVALID_ANOMALY_INVALID_FINGERPRINT = {
  fingerprint: 'not-a-valid-sha256-hex',
  definition_code: 'SCHEDULE-001',
  source_domain: 'scheduling',
  source_identity: 'assignment:102',
  source_version: 2,
  severity: 'blocking',
  predicate_active: true,
  workflow_status: 'open',
  workflow_version: 0,
};

/**
 * 異常資料嚴重度枚舉不合法 (例如使用了前端 mock 的 CRITICAL 而非 canonical 'blocking')
 */
export const INVALID_ANOMALY_INVALID_SEVERITY = {
  fingerprint: '8f48483d980d2105151522a36a7f05ee461e78a63574a3f1244d2d6c66cf17f8',
  definition_code: 'SCHEDULE-001',
  source_domain: 'scheduling',
  source_identity: 'assignment:102',
  source_version: 2,
  severity: 'CRITICAL', // 不合法，應為 'warning' 或 'blocking'
  predicate_active: true,
  workflow_status: 'open',
  workflow_version: 0,
};

/**
 * 異常資料狀態枚舉不合法
 */
export const INVALID_ANOMALY_INVALID_STATUS = {
  fingerprint: '8f48483d980d2105151522a36a7f05ee461e78a63574a3f1244d2d6c66cf17f8',
  definition_code: 'SCHEDULE-001',
  source_domain: 'scheduling',
  source_identity: 'assignment:102',
  source_version: 2,
  severity: 'blocking',
  predicate_active: true,
  workflow_status: 'in_progress', // 不合法，應為 'open' | 'claimed' | 'resolved'
  workflow_version: 0,
};

/**
 * 異常資料包含額外未宣告欄位 (違反 .strict())
 */
export const INVALID_ANOMALY_EXTRA_UNKNOWN_FIELD = {
  ...VALID_ANOMALY_SUMMARY_1,
  unauthorized_extra_field: 'injected_payload',
};

/**
 * 異常資料包含負數版本號
 */
export const INVALID_ANOMALY_NEGATIVE_VERSION = {
  ...VALID_ANOMALY_SUMMARY_1,
  source_version: -1,
};

/**
 * 異常資料之導航目標日期格式不合法
 */
export const INVALID_ANOMALY_INVALID_NAV_DATE = {
  ...VALID_ANOMALY_SUMMARY_1,
  staff_calendar_navigation: {
    staff_id: 14,
    target_date: '2026/08/20', // 不合法，應為 YYYY-MM-DD
  },
};

/**
 * 匯入警示任務缺少 occurrence_identity
 */
export const INVALID_TASK_MISSING_IDENTITY = {
  owning_lane: 'hcm',
  logical_code: 'HCM-FIELD-001',
  field_path: '身分證字號',
  masked_subject: 'A12****789',
  issue_codes: ['hcm_field_missing'],
  tracking_status: 'open',
  tracking_version: 1,
  display_message: '缺少身分證字號',
};

/**
 * 匯入警示任務狀態枚舉不合法
 */
export const INVALID_TASK_INVALID_STATUS = {
  ...VALID_IMPORT_WARNING_TASK_HCM,
  tracking_status: 'pending_review', // 不合法
};

/**
 * 匯入警示任務版本號為 0 (必須 ge 1)
 */
export const INVALID_TASK_ZERO_VERSION = {
  ...VALID_IMPORT_WARNING_TASK_HCM,
  tracking_version: 0,
};

/**
 * 匯入警示任務訊息為空字串 (min_length 1)
 */
export const INVALID_TASK_EMPTY_MESSAGE = {
  ...VALID_IMPORT_WARNING_TASK_HCM,
  display_message: '',
};

/**
 * 匯入警示任務訊息超過 200 字元
 */
export const INVALID_TASK_OVERLONG_MESSAGE = {
  ...VALID_IMPORT_WARNING_TASK_HCM,
  display_message: 'A'.repeat(201),
};

/**
 * 匯入警示任務導航動作不合法
 */
export const INVALID_TASK_INVALID_NAV_ACTION = {
  ...VALID_IMPORT_WARNING_TASK_HCM,
  navigation_action: 'unknown_admin_center',
};

/**
 * 匯入警示任務包含額外未宣告欄位 (違反 .strict())
 */
export const INVALID_TASK_EXTRA_FIELD = {
  ...VALID_IMPORT_WARNING_TASK_HCM,
  injected_key: 12345,
};

/**
 * 信封格式損毀：非物件型態
 */
export const CORRUPTED_ENVELOPE_PRIMITIVE = 'not-a-json-object';

/**
 * 信封格式損毀：success 為 false 且帶有業務錯誤訊息
 */
export const CORRUPTED_ENVELOPE_BUSINESS_ERROR = {
  success: false,
  message: '後端權限檢驗失敗',
  data: [],
  error: 'PERMISSION_DENIED',
};

/**
 * 信封包含額外未宣告欄位 (違反 .strict())
 */
export const CORRUPTED_ENVELOPE_EXTRA_FIELD = {
  success: true,
  message: '成功',
  data: [],
  error: null,
  leak_token: 'secret_leak',
};
