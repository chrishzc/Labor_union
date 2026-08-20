/**
 * File: reports_query_no_fake_mutation.test.ts
 * Description: 靜態驗證ReportsPage無mock、alert、export GET與local business arrays。
 */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
describe('ReportsPage query safety', () => {
  it('contains no fake data or export mutation', () => {
    const source = readFileSync('src/pages/ReportsPage.tsx', 'utf8');
    for (const forbidden of ['alert(', 'confirm(', 'prompt(', 'WeeklyCaseRow', 'SubsidyDetailRow', 'WeeklyActiveServiceRow', '.post(', '.put(', '.delete(']) expect(source).not.toContain(forbidden);
  });
});
