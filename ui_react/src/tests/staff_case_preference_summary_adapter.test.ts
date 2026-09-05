/**
 * File: staff_case_preference_summary_adapter.test.ts
 * Description: 驗證六母題順序、空值與 local other fallback 的 UI 映射。
 */
import { describe, expect, it } from 'vitest';
import { adaptStaffCasePreferenceSummary } from '../adapters/staff/staff_case_preference_summary_adapter';
import { STAFF_CASE_PREFERENCE_SUMMARY } from './fixtures/staff/staff_case_preference_summary_contract_fixtures';

describe('staff case preference summary adapter', () => {
  it('preserves the six owner-defined topics and response value order', () => {
    const view = adaptStaffCasePreferenceSummary(STAFF_CASE_PREFERENCE_SUMMARY);

    expect(view.staffId).toBe(11);
    expect(view.topics.map((topic) => topic.label)).toEqual([
      '希望服務地區',
      '服務時段',
      '如何排休',
      '通常接幾胞胎',
      '特殊節日可接案',
      '交通方式',
    ]);
    expect(view.topics[0].valuesText).toBe('北區、新竹縣');
  });

  it('maps empty values and topic-local other statuses without inventing fallback facts', () => {
    const view = adaptStaffCasePreferenceSummary(STAFF_CASE_PREFERENCE_SUMMARY);
    const byKey = Object.fromEntries(view.topics.map((topic) => [topic.key, topic]));

    expect(byKey.service_periods.valuesText).toBe('尚未登錄');
    expect(byKey.service_regions.detailText).toBe('其它：偏遠地區需先確認交通');
    expect(byKey.rest_schedule.detailText).toBeNull();
    expect(byKey.transportation.detailText).toBe('其它來源尚未就緒');
    expect(byKey.transportation.valuesText).toBe('機車');
  });
});
