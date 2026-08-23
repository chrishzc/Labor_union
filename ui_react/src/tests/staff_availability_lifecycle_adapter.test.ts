/**
 * File: staff_availability_lifecycle_adapter.test.ts
 * Description: 驗證 Availability/Lifecycle adapter 不推導日期、天數或資格。
 */
import { describe, expect, it } from 'vitest';
import {
  adaptStaffAvailabilityBlock,
  adaptStaffAvailabilityPreview,
  adaptStaffAvailabilityReceipt,
} from '../adapters/staff/staff_availability_adapter';
import {
  adaptStaffLifecyclePreview,
  adaptStaffLifecycleReceipt,
  adaptStaffLifecycleView,
} from '../adapters/staff/staff_lifecycle_adapter';
import {
  STAFF_AVAILABILITY_BLOCK,
  STAFF_AVAILABILITY_PAUSE_BLOCK,
  STAFF_AVAILABILITY_PREVIEW_RESPONSE,
  STAFF_AVAILABILITY_RECEIPT_RESPONSE,
} from './fixtures/staff/staff_availability_contract_fixtures';
import {
  STAFF_LIFECYCLE_PREVIEW,
  STAFF_LIFECYCLE_RECEIPT,
  STAFF_LIFECYCLE_VIEW,
} from './fixtures/staff/staff_lifecycle_contract_fixtures';

describe('staff availability/lifecycle adapters', () => {
  it('preserves server availability dates and leaves non-contract duration neutral', () => {
    const view = adaptStaffAvailabilityBlock(STAFF_AVAILABILITY_BLOCK);
    const openEndedPause = adaptStaffAvailabilityBlock(STAFF_AVAILABILITY_PAUSE_BLOCK);
    expect(view.startDate).toBe('2026-09-01');
    expect(view.endDate).toBe('2026-09-30');
    expect(openEndedPause.displayEndDate).toBe('—');
    expect(view.durationDays).toBeNull();
    expect(view.durationLabel).toBe('—');
  });

  it('preserves availability preview blockers and receipt lineage', () => {
    const preview = adaptStaffAvailabilityPreview(STAFF_AVAILABILITY_PREVIEW_RESPONSE.data!);
    const receipt = adaptStaffAvailabilityReceipt(STAFF_AVAILABILITY_RECEIPT_RESPONSE.data!);
    expect(preview.blockers).toEqual([]);
    expect(preview.previewFingerprint).toBe('a'.repeat(64));
    expect(receipt.aggregateVersion).toBe(3);
    expect(receipt.idempotencyKey).toBe('availability-apply-7-01');
  });

  it('uses only server lifecycle state to expose transition controls', () => {
    const view = adaptStaffLifecycleView(STAFF_LIFECYCLE_VIEW);
    const preview = adaptStaffLifecyclePreview(STAFF_LIFECYCLE_PREVIEW, 'retirement');
    const receipt = adaptStaffLifecycleReceipt(STAFF_LIFECYCLE_RECEIPT);
    expect(view.canRetire).toBe(true);
    expect(view.canReactivate).toBe(false);
    expect(view.displayEffectiveAt).toBe('—');
    expect(preview.afterState).toBe('retired');
    expect(receipt.resultingVersion).toBe(3);
    expect(receipt.previewFingerprint).toBe('b'.repeat(64));
  });
});
