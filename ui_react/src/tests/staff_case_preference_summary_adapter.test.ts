import { describe, expect, it } from 'vitest';
import { adaptStaffCasePreferenceSummary } from '../adapters/staff/case_preference_summary_adapter';
import { STAFF_CASE_PREFERENCE_READ } from './fixtures/staff/staff_case_preference_contract_fixtures';

describe('Staff case-preference summary adapter', () => {
  it('renders values, topic-local other, and transport source readiness independently', () => {
    const view = adaptStaffCasePreferenceSummary(STAFF_CASE_PREFERENCE_READ);
    const regions = view.topics.find((topic) => topic.key === 'service_regions')!;
    const transport = view.topics.find((topic) => topic.key === 'transportation')!;

    expect(regions.valuesText).toBe('北區');
    expect(regions.otherDetailText).toBe('其它：新竹市');
    expect(transport.valuesText).toBe('機車');
    expect(transport.otherDetailText).toBe('其它來源尚未就緒');
  });

  it('uses 尚未登錄 only for empty readable values and degrades one malformed topic locally', () => {
    const view = adaptStaffCasePreferenceSummary({
      ...STAFF_CASE_PREFERENCE_READ,
      service_periods: {
        availability: 'available',
        data: { values: [], other_detail: null, other_detail_status: 'not_recorded' },
      },
      baby_counts: { availability: 'unavailable', reason: 'invalid_topic' },
    });
    expect(view.topics.find((topic) => topic.key === 'service_periods')?.valuesText).toBe('尚未登錄');
    expect(view.topics.find((topic) => topic.key === 'baby_counts')?.valuesText).toBe('資料暫時無法取得');
  });
});
