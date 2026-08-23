/**
 * File: import_warning_transition_adapter.test.ts
 * Description: 驗證匯入警示 transition adapter 只投影 server typed values，不推導業務結果。
 */

import { describe, expect, it } from 'vitest';
import {
  adaptImportWarningTransitionPreview,
  adaptImportWarningTransitionReceipt,
} from '../adapters/import_warning/import_warning_transition_adapter';
import {
  VALID_WARNING_TRANSITION_PREVIEW,
  VALID_WARNING_TRANSITION_RECEIPT,
} from './fixtures/import_warning/import_warning_transition_contract_fixtures';

describe('Import warning transition adapter', () => {
  it('原樣投影 Preview 與 terminal receipt 欄位', () => {
    expect(adaptImportWarningTransitionPreview(VALID_WARNING_TRANSITION_PREVIEW)).toEqual({
      occurrenceIdentity: 'import-warning:fixture-001',
      expectedVersion: 7,
      resultingStatus: 'awaiting_external_confirmation',
      resultingVersion: 8,
    });
    expect(adaptImportWarningTransitionReceipt(VALID_WARNING_TRANSITION_RECEIPT)).toEqual({
      occurrenceIdentity: 'import-warning:fixture-001',
      beforeStatus: 'open',
      afterStatus: 'awaiting_external_confirmation',
      resultingVersion: 8,
      receiptIdentity: 'a'.repeat(64),
      correlationId: 'phase3d-w-r-correlation-001',
      replayed: false,
    });
  });

  it('不建立成功文案、已修復結論或任何領域衍生欄位', () => {
    const preview = adaptImportWarningTransitionPreview(VALID_WARNING_TRANSITION_PREVIEW);
    const receipt = adaptImportWarningTransitionReceipt(VALID_WARNING_TRANSITION_RECEIPT);
    const serialized = JSON.stringify({ preview, receipt });

    expect(serialized).not.toContain('已修復');
    expect(preview).not.toHaveProperty('statusLabel');
    expect(preview).not.toHaveProperty('success');
    expect(receipt).not.toHaveProperty('changed');
    expect(receipt).not.toHaveProperty('ownerRepairCompleted');
  });
});
