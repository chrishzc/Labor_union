/**
 * File: staff_lifecycle_contract_fixtures.ts
 * Description: 提供去敏 Staff lifecycle Query、Preview、Apply 合約測試資料。
 */
import type {
  StaffLifecycleApplyPayload,
  StaffLifecycleApplyReceipt,
  StaffLifecyclePreview,
  StaffLifecycleTransitionInput,
  StaffLifecycleView,
} from '../../../api/staff_lifecycle/staff_lifecycle_schemas';

export const STAFF_LIFECYCLE_VIEW = {
  staff_id: 7,
  state: 'active',
  version: 2,
  effective_at: null,
  masked_reason_code: null,
} satisfies StaffLifecycleView;

export const STAFF_LIFECYCLE_PREVIEW = {
  staff_id: 7,
  state: 'active',
  version: 2,
  effective_at: null,
  masked_reason_code: null,
  after_state: 'retired',
  preview_fingerprint: 'b'.repeat(64),
} satisfies StaffLifecyclePreview;

export const STAFF_LIFECYCLE_RECEIPT = {
  staff_id: 7,
  state: 'retired',
  resulting_version: 3,
  preview_fingerprint: 'b'.repeat(64),
  idempotency_key: 'lifecycle-apply-7-01',
} satisfies StaffLifecycleApplyReceipt;

export const STAFF_LIFECYCLE_QUERY_RESPONSE = {
  success: true,
  message: 'Success',
  data: STAFF_LIFECYCLE_VIEW,
  error: null,
};

export const STAFF_LIFECYCLE_PREVIEW_RESPONSE = {
  success: true,
  message: 'Success',
  data: STAFF_LIFECYCLE_PREVIEW,
  error: null,
};

export const STAFF_LIFECYCLE_RECEIPT_RESPONSE = {
  success: true,
  message: 'Success',
  data: STAFF_LIFECYCLE_RECEIPT,
  error: null,
} satisfies { success: boolean; message: string; data: StaffLifecycleApplyReceipt; error: string | null };

export const STAFF_LIFECYCLE_PREVIEW_PAYLOAD = {
  effective_at: '2026-08-15T09:00:00+08:00',
  reason_code: 'left_union',
} satisfies StaffLifecycleTransitionInput;

export const STAFF_LIFECYCLE_APPLY_PAYLOAD = {
  ...STAFF_LIFECYCLE_PREVIEW_PAYLOAD,
  expected_version: 2,
  preview_fingerprint: 'b'.repeat(64),
} satisfies StaffLifecycleApplyPayload;
