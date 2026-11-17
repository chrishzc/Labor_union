/**
 * File: finance_query_no_fake_mutation.test.ts
 * Description: 靜態驗證FinancePage無mock、alert與非GET mutation呼叫。
 */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
describe('FinancePage query safety', () => {
  it('contains no fake mutation or mock dependency', () => {
    const source = readFileSync('src/pages/FinancePage.tsx', 'utf8');
    const withoutLocalCommandCleanup = source.replace('financeApplyCommandByPreview.current.delete(expected.previewFingerprint)', '');
    for (const forbidden of ['mockData', 'MOCK_', 'alert(', 'confirm(', 'prompt(', 'fetch(', '.post(', '.put(', '.delete(', 'handleSettle', 'handleApprove']) expect(withoutLocalCommandCleanup).not.toContain(forbidden);
    expect(source).not.toContain('error instanceof Error ? error.message');
  });

  it('keeps normal import single-click and routes row recovery out of Finance Import', () => {
    const source = readFileSync('src/pages/FinancePage.tsx', 'utf8');
    expect(source).toContain('銀行對帳');
    const workspace = readFileSync('src/components/FinanceBankReconciliationWorkspace.tsx', 'utf8');
    expect(workspace).toContain('選擇銀行交易明細工作簿');
    expect(workspace).toContain('匯入銀行交易明細');
    expect(workspace).toContain('onIngest()');
    expect(source).toContain('await previewImportedBatch(receipt)');
    expect(source).toContain('applyReady && canApplyImportedBatch(preview)');
    expect(source).toContain('await applyImportedBatch(preview, true)');
    expect(source).toContain('observeApplyOutcome(accepted.job_id,');
    for (const presentation of [source, workspace]) {
      expect(presentation).not.toContain('finance.finance-import.correction');
      expect(presentation).not.toContain('帳務更正義務識別');
    }
  });
});
