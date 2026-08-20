/**
 * File: finance_query_no_fake_mutation.test.ts
 * Description: 靜態驗證FinancePage無mock、alert與非GET mutation呼叫。
 */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
describe('FinancePage query safety', () => {
  it('contains no fake mutation or mock dependency', () => {
    const source = readFileSync('src/pages/FinancePage.tsx', 'utf8');
    for (const forbidden of ['mockData', 'MOCK_', 'alert(', 'confirm(', 'prompt(', '.post(', '.put(', '.delete(', 'handleSettle', 'handleApprove']) expect(source).not.toContain(forbidden);
  });
});
