/**
 * File: staff_case_preference_summary_contract_fixtures.ts
 * Description: 月嫂名冊接案偏好 strict contract 測試資料。
 */
import type {
  StaffCasePreferenceSummary,
  StaffCasePreferenceSummaryResponse,
} from '../../../api/staff_case_preference_summary/staff_case_preference_summary_schemas';

export const STAFF_CASE_PREFERENCE_SUMMARY: StaffCasePreferenceSummary = {
  staff_id: 11,
  service_regions: {
    values: ['北區', '新竹縣'],
    other_detail: '偏遠地區需先確認交通',
    other_detail_status: 'ready',
  },
  service_periods: {
    values: [],
    other_detail: null,
    other_detail_status: 'not_recorded',
  },
  rest_schedule: {
    values: ['週休1日'],
    other_detail: null,
    other_detail_status: 'not_recorded',
  },
  baby_counts: {
    values: ['雙胞胎'],
    other_detail: null,
    other_detail_status: 'not_recorded',
  },
  holiday_availability: {
    values: ['中秋節'],
    other_detail: null,
    other_detail_status: 'not_recorded',
  },
  transportation: {
    values: ['機車'],
    other_detail: null,
    other_detail_status: 'source_not_ready',
  },
};

export const STAFF_CASE_PREFERENCE_SUMMARY_RESPONSE: StaffCasePreferenceSummaryResponse = {
  success: true,
  message: '成功取得服務人員案件偏好摘要',
  data: STAFF_CASE_PREFERENCE_SUMMARY,
  error: null,
};
