/**
 * File: hcm_import_result_adapter.test.ts
 * Description: 驗證 HCM receipt守恆，並正確分組新增、問題、replay與legacy unavailable。
 */
import { describe, expect, it } from 'vitest';
import { adaptHcmImportResult } from '../adapters/case_import/hcm_import_result_adapter';
import { detailedHcmResult } from './fixtures/hcm_import_result_fixtures';

describe('HCM import result adapter', () => {
  it('separates new orders, problems and exact replay without inference', () => {
    const view = adaptHcmImportResult(detailedHcmResult);
    expect(view.newOrders.map((row) => row.case_no)).toEqual(['115000001', '115000002']);
    expect(view.problems.map((row) => row.case_no)).toEqual(['115000002']);
    expect(view.replays.map((row) => row.case_no)).toEqual(['115000003']);
  });

  it('keeps legacy count-only membership unavailable', () => {
    const view = adaptHcmImportResult({ ...detailedHcmResult, row_outcomes_available: false, legacy_summary_only: true, row_outcomes: [] });
    expect(view.rowOutcomesAvailable).toBe(false);
    expect(view.newOrders).toEqual([]);
  });

  it('rejects non-conserved aggregate counts', () => {
    expect(() => adaptHcmImportResult({ ...detailedHcmResult, failed_count: 1 })).toThrow('計數不守恆');
  });
});
