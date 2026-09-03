import type {
  StaffCasePreferenceSummary,
  StaffCasePreferenceSummaryRead,
} from '../../../api/staff/case_preference_summary_schemas';

export const STAFF_CASE_PREFERENCE_SUMMARY: StaffCasePreferenceSummary = {
  staff_id: 11,
  service_regions: {
    values: ['北區'],
    other_detail: '新竹市',
    other_detail_status: 'ready',
  },
  service_periods: {
    values: ['8小時'],
    other_detail: null,
    other_detail_status: 'not_recorded',
  },
  rest_schedule: {
    values: ['週休1日'],
    other_detail: null,
    other_detail_status: 'not_recorded',
  },
  baby_counts: {
    values: ['單胞胎', '雙胞胎'],
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

export const STAFF_CASE_PREFERENCE_RESPONSE = {
  success: true,
  message: '成功取得服務人員接案偏好摘要',
  data: STAFF_CASE_PREFERENCE_SUMMARY,
  error: null,
};

export const STAFF_CASE_PREFERENCE_READ: StaffCasePreferenceSummaryRead = {
  staff_id: 11,
  service_regions: { availability: 'available', data: STAFF_CASE_PREFERENCE_SUMMARY.service_regions },
  service_periods: { availability: 'available', data: STAFF_CASE_PREFERENCE_SUMMARY.service_periods },
  rest_schedule: { availability: 'available', data: STAFF_CASE_PREFERENCE_SUMMARY.rest_schedule },
  baby_counts: { availability: 'available', data: STAFF_CASE_PREFERENCE_SUMMARY.baby_counts },
  holiday_availability: { availability: 'available', data: STAFF_CASE_PREFERENCE_SUMMARY.holiday_availability },
  transportation: { availability: 'available', data: STAFF_CASE_PREFERENCE_SUMMARY.transportation },
};
