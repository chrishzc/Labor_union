/**
 * File: staff_case_preference_summary_adapter.ts
 * Description: 將 canonical 接案偏好摘要映射成名冊 card / Drawer 可直接呈現的唯讀 view model。
 */
import type {
  StaffCasePreferenceOtherDetailStatus,
  StaffCasePreferenceSummary,
  StaffCasePreferenceTopic,
} from '../../api/staff_case_preference_summary/staff_case_preference_summary_schemas';

export type StaffCasePreferenceTopicKey =
  | 'service_regions'
  | 'service_periods'
  | 'rest_schedule'
  | 'baby_counts'
  | 'holiday_availability'
  | 'transportation';

export interface StaffCasePreferenceTopicViewModel {
  key: StaffCasePreferenceTopicKey;
  label: string;
  valuesText: string;
  otherDetailStatus: StaffCasePreferenceOtherDetailStatus;
  detailText: string | null;
}

export interface StaffCasePreferenceSummaryViewModel {
  staffId: number;
  topics: StaffCasePreferenceTopicViewModel[];
}

const TOPICS: ReadonlyArray<{ key: StaffCasePreferenceTopicKey; label: string }> = [
  { key: 'service_regions', label: '希望服務地區' },
  { key: 'service_periods', label: '服務時段' },
  { key: 'rest_schedule', label: '如何排休' },
  { key: 'baby_counts', label: '通常接幾胞胎' },
  { key: 'holiday_availability', label: '特殊節日可接案' },
  { key: 'transportation', label: '交通方式' },
];

function detailText(topic: StaffCasePreferenceTopic): string | null {
  if (topic.other_detail_status === 'ready') {
    return `其它：${topic.other_detail}`;
  }
  if (topic.other_detail_status === 'source_not_ready') {
    return '其它來源尚未就緒';
  }
  return null;
}

export function adaptStaffCasePreferenceSummary(
  summary: StaffCasePreferenceSummary,
): StaffCasePreferenceSummaryViewModel {
  return {
    staffId: summary.staff_id,
    topics: TOPICS.map(({ key, label }) => {
      const topic = summary[key];
      return {
        key,
        label,
        valuesText: topic.values.length > 0 ? topic.values.join('、') : '尚未登錄',
        otherDetailStatus: topic.other_detail_status,
        detailText: detailText(topic),
      };
    }),
  };
}
