/**
 * File: case_preference_summary_adapter.ts
 * Description: 將 Staff case-preference summary 轉成 card / Drawer 共用唯讀 view model。
 */
import {
  STAFF_CASE_PREFERENCE_TOPIC_KEYS,
  type StaffCasePreferenceSummaryRead,
  type StaffCasePreferenceTopicKey,
  type StaffCasePreferenceTopicRead,
} from '../../api/staff/case_preference_summary_schemas';

const TOPIC_LABELS: Record<StaffCasePreferenceTopicKey, string> = {
  service_regions: '服務區域',
  service_periods: '服務時段',
  rest_schedule: '排休',
  baby_counts: '胎數',
  holiday_availability: '節日意願',
  transportation: '交通方式',
};

export interface StaffCasePreferenceTopicViewModel {
  key: StaffCasePreferenceTopicKey;
  label: string;
  availability: 'available' | 'unavailable';
  values: readonly string[];
  valuesText: string;
  otherDetailText: string | null;
}

export interface StaffCasePreferenceSummaryViewModel {
  staffId: number;
  topics: readonly StaffCasePreferenceTopicViewModel[];
}

function adaptTopic(key: StaffCasePreferenceTopicKey, topic: StaffCasePreferenceTopicRead): StaffCasePreferenceTopicViewModel {
  if (topic.availability === 'unavailable') {
    return {
      key,
      label: TOPIC_LABELS[key],
      availability: 'unavailable',
      values: [],
      valuesText: '資料暫時無法取得',
      otherDetailText: null,
    };
  }
  return {
    key,
    label: TOPIC_LABELS[key],
    availability: 'available',
    values: topic.data.values,
    valuesText: topic.data.values.length > 0 ? topic.data.values.join('、') : '尚未登錄',
    otherDetailText: topic.data.other_detail_status === 'ready'
      ? `其它：${topic.data.other_detail}`
      : topic.data.other_detail_status === 'source_not_ready'
        ? '其它來源尚未就緒'
        : null,
  };
}

export function adaptStaffCasePreferenceSummary(summary: StaffCasePreferenceSummaryRead): StaffCasePreferenceSummaryViewModel {
  return {
    staffId: summary.staff_id,
    topics: STAFF_CASE_PREFERENCE_TOPIC_KEYS.map((key) => adaptTopic(key, summary[key])),
  };
}
