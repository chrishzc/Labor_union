/**
 * File: import_warning_transition_adapter.ts
 * Description: 將匯入警示 transition typed DTO 投影為 UI view model，不重算狀態或宣稱修復完成。
 */

import type {
  WarningTransitionPreview,
  WarningTransitionReceipt,
} from '../../api/import_warning/import_warning_transition_schemas';

export interface ImportWarningTransitionPreviewViewModel {
  occurrenceIdentity: string;
  expectedVersion: number;
  resultingStatus: WarningTransitionPreview['resulting_status'];
  resultingVersion: number;
}

export interface ImportWarningTransitionReceiptViewModel {
  occurrenceIdentity: string;
  beforeStatus: WarningTransitionReceipt['before_status'];
  afterStatus: WarningTransitionReceipt['after_status'];
  resultingVersion: number;
  receiptIdentity: string;
  correlationId: string;
  replayed: boolean;
}

export function adaptImportWarningTransitionPreview(
  value: WarningTransitionPreview,
): ImportWarningTransitionPreviewViewModel {
  return {
    occurrenceIdentity: value.occurrence_identity,
    expectedVersion: value.expected_version,
    resultingStatus: value.resulting_status,
    resultingVersion: value.resulting_version,
  };
}

export function adaptImportWarningTransitionReceipt(
  value: WarningTransitionReceipt,
): ImportWarningTransitionReceiptViewModel {
  return {
    occurrenceIdentity: value.occurrence_identity,
    beforeStatus: value.before_status,
    afterStatus: value.after_status,
    resultingVersion: value.resulting_version,
    receiptIdentity: value.receipt_identity,
    correlationId: value.correlation_id,
    replayed: value.replayed,
  };
}

