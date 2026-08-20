/**
 * File: subsidy_report_query_adapter.test.ts
 * Description: 驗證補助報表adapter只格式化server rows與aggregates。
 */
import { describe, expect, it } from 'vitest';
import { adaptSubsidyReport } from '../adapters/reports/subsidy_report_query_adapter';
import { SUBSIDY_REPORT_RESPONSE } from './fixtures/reports/subsidy_report_query_contract_fixtures';
describe('subsidy report adapter', () => {
  it('preserves server totals and masked fields', () => {
    const view = adaptSubsidyReport(SUBSIDY_REPORT_RESPONSE.data);
    expect(view.totalAmount).toBe('NT$ 12,000');
    expect(view.partitions[0].rows[0].identity).toBe('A*********');
    expect(view.partitions[0].rows[0].subsidyHours).toBe('40');
  });
});
