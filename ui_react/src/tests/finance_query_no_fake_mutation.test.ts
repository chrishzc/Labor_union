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

  it('keeps normal import three-step and routes row recovery out of Finance Import', () => {
    const source = readFileSync('src/pages/FinancePage.tsx', 'utf8');
    expect(source).toContain('上傳檔案 → 預覽 → 匯入完成');
    expect(source).toContain('上傳檔案');
    expect(source).toContain('預覽匯入結果');
    expect(source).toContain('確認匯入');
    expect(source).toContain('observeApplyOutcome(accepted.job_id)');
    expect(source).not.toContain('finance.finance-import.correction');
    expect(source).not.toContain('帳務更正義務識別');
  });
});
