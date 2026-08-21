/**
 * File: holiday_contract_fixtures.ts
 * Description: 提供國定假日 strict Query、Preview、Apply 與 receipt 的去敏契約資料。
 */

export const HOLIDAY_QUERY = {
  from_date: '2026-01-01',
  to_date: '2026-12-31',
};

export const HOLIDAY_CALENDAR = {
  planning_horizon: {
    from_date: HOLIDAY_QUERY.from_date,
    to_date: HOLIDAY_QUERY.to_date,
  },
  source_identity: 'scheduling-holiday-source-test',
  calendar_version: 'a'.repeat(64),
  holidays: [
    {
      holiday_date: '2026-02-17',
      holiday_name: '去敏春節假日',
      is_double_pay_default: false,
    },
  ],
};

export const HOLIDAY_DRAFT = {
  action: 'upsert' as const,
  holiday_date: '2026-09-28',
  holiday_name: '去敏教師節假日',
  is_double_pay_default: false,
  from_date: HOLIDAY_QUERY.from_date,
  to_date: HOLIDAY_QUERY.to_date,
};

export const HOLIDAY_PREVIEW_REQUEST = HOLIDAY_DRAFT;

export const HOLIDAY_PREVIEW = {
  command: {
    ...HOLIDAY_DRAFT,
    expected_calendar_version: HOLIDAY_CALENDAR.calendar_version,
  },
  before: null,
  planning_horizon: HOLIDAY_CALENDAR.planning_horizon,
  source_identity: HOLIDAY_CALENDAR.source_identity,
  calendar_version: HOLIDAY_CALENDAR.calendar_version,
  schedule_impact: 'none' as const,
  payroll_impact: 'none' as const,
  preview_fingerprint: 'b'.repeat(64),
};

export const HOLIDAY_APPLY_REQUEST = {
  ...HOLIDAY_DRAFT,
  expected_calendar_version: HOLIDAY_PREVIEW.calendar_version,
  preview_fingerprint: HOLIDAY_PREVIEW.preview_fingerprint,
  reason: '核准國定假日政策測試變更',
};

export const HOLIDAY_RECEIPT = {
  receipt_key: 'scheduling-holiday-test-receipt',
  action: HOLIDAY_APPLY_REQUEST.action,
  holiday_date: HOLIDAY_APPLY_REQUEST.holiday_date,
  changed: true,
  planning_horizon: HOLIDAY_CALENDAR.planning_horizon,
  source_identity: HOLIDAY_CALENDAR.source_identity,
  previous_calendar_version: HOLIDAY_CALENDAR.calendar_version,
  resulting_calendar_version: 'c'.repeat(64),
  preview_fingerprint: HOLIDAY_PREVIEW.preview_fingerprint,
};

export const HOLIDAY_QUERY_RESPONSE = {
  success: true,
  message: '成功取得國定假日列表',
  data: HOLIDAY_CALENDAR,
  error: null,
};

export const HOLIDAY_PREVIEW_RESPONSE = {
  success: true,
  message: '已產生國定假日變更預覽',
  data: HOLIDAY_PREVIEW,
  error: null,
};

export const HOLIDAY_APPLY_RESPONSE = {
  success: true,
  message: '已套用國定假日變更',
  data: HOLIDAY_RECEIPT,
  error: null,
};

export const HOLIDAY_TYPED_CONFLICT_RESPONSE = {
  detail: {
    error: {
      category: 'conflict',
      code: 'stale_preview',
      message: '國定假日 Preview 已過期。',
      field_errors: [],
      domain_blockers: ['calendar_version'],
      retryable: false,
      correlation_id: 'holiday-conflict-correlation',
      current_version: null,
    },
  },
};
