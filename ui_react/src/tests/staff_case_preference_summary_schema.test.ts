import { describe, expect, it } from 'vitest';
import {
  StaffCasePreferenceSummarySchema,
  StaffCasePreferenceTopicSummarySchema,
} from '../api/staff/case_preference_summary_schemas';
import { STAFF_CASE_PREFERENCE_SUMMARY } from './fixtures/staff/staff_case_preference_contract_fixtures';

describe('Staff case-preference summary schema', () => {
  it('accepts the six-topic strict contract', () => {
    expect(StaffCasePreferenceSummarySchema.parse(STAFF_CASE_PREFERENCE_SUMMARY)).toEqual(STAFF_CASE_PREFERENCE_SUMMARY);
  });

  it('rejects extra root or topic fields', () => {
    expect(StaffCasePreferenceSummarySchema.safeParse({ ...STAFF_CASE_PREFERENCE_SUMMARY, raw_json: {} }).success).toBe(false);
    expect(StaffCasePreferenceTopicSummarySchema.safeParse({
      ...STAFF_CASE_PREFERENCE_SUMMARY.service_regions,
      generic_other_note: '禁止',
    }).success).toBe(false);
  });

  it('enforces detail/status invariants without guessing blank values', () => {
    expect(StaffCasePreferenceTopicSummarySchema.safeParse({
      values: [], other_detail: null, other_detail_status: 'ready',
    }).success).toBe(false);
    expect(StaffCasePreferenceTopicSummarySchema.safeParse({
      values: [], other_detail: '新竹市', other_detail_status: 'not_recorded',
    }).success).toBe(false);
    expect(StaffCasePreferenceTopicSummarySchema.safeParse({
      values: [], other_detail: null, other_detail_status: 'source_not_ready',
    }).success).toBe(true);
  });
});
