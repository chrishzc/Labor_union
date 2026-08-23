/**
 * File: staff_availability_contract_fixtures.ts
 * Description: 提供去敏 Availability Query、Preview、Apply 合約測試資料。
 */
import type {
  StaffAvailabilityPreviewResponse,
  StaffAvailabilityQueryResponse,
  StaffAvailabilityReceiptResponse,
  StaffAvailabilityApplyPayload,
  StaffUnavailabilityBlock,
} from '../../../api/staff_availability/staff_availability_schemas';

export const STAFF_AVAILABILITY_BLOCK = {
  block_id: 91,
  staff_id: 7,
  kind: 'long_leave',
  start_date: '2026-09-01',
  end_date: '2026-09-30',
  status: 'effective',
  reason: '去敏照護安排',
} satisfies StaffUnavailabilityBlock;

export const STAFF_AVAILABILITY_PAUSE_BLOCK = {
  block_id: 92,
  staff_id: 7,
  kind: 'paused_service',
  start_date: '2026-10-01',
  end_date: null,
  status: 'effective',
  reason: '去敏暫停接案',
} satisfies StaffUnavailabilityBlock;

export const STAFF_AVAILABILITY_SELECTED_PAUSE_BLOCK = {
  ...STAFF_AVAILABILITY_PAUSE_BLOCK,
  staff_id: 11,
} satisfies StaffUnavailabilityBlock;

export const STAFF_AVAILABILITY_CLOSED_PAUSE_BLOCK = {
  ...STAFF_AVAILABILITY_SELECTED_PAUSE_BLOCK,
  end_date: '2026-10-14',
} satisfies StaffUnavailabilityBlock;

export const STAFF_AVAILABILITY_QUERY_RESPONSE = {
  success: true,
  message: '成功取得月嫂不可服務期間',
  data: [STAFF_AVAILABILITY_BLOCK, STAFF_AVAILABILITY_PAUSE_BLOCK],
  error: null,
} satisfies StaffAvailabilityQueryResponse;

export const STAFF_AVAILABILITY_PREVIEW_RESPONSE = {
  success: true,
  message: '成功產生月嫂不可服務期間預覽',
  data: {
    staff_id: 7,
    action: 'create_pause',
    source_version: 2,
    target_block: null,
    candidate_kind: 'paused_service',
    candidate_start_date: '2026-10-01',
    candidate_end_date: null,
    blockers: [],
    can_apply: true,
    preview_fingerprint: 'a'.repeat(64),
  },
  error: null,
} satisfies StaffAvailabilityPreviewResponse;

export const STAFF_AVAILABILITY_RECEIPT_RESPONSE = {
  success: true,
  message: '成功套用月嫂不可服務期間異動',
  data: {
    staff_id: 7,
    action: 'create_pause',
    block: STAFF_AVAILABILITY_PAUSE_BLOCK,
    aggregate_version: 3,
    preview_fingerprint: 'a'.repeat(64),
    idempotency_key: 'availability-apply-7-01',
  },
  error: null,
} satisfies StaffAvailabilityReceiptResponse;

export const STAFF_AVAILABILITY_END_PAUSE_PREVIEW_RESPONSE = {
  success: true,
  message: '成功產生結束暫停接案預覽',
  data: {
    staff_id: 11,
    action: 'end_pause',
    source_version: 4,
    target_block: STAFF_AVAILABILITY_SELECTED_PAUSE_BLOCK,
    candidate_kind: 'paused_service',
    candidate_start_date: '2026-10-01',
    candidate_end_date: '2026-10-14',
    blockers: [],
    can_apply: true,
    preview_fingerprint: 'b'.repeat(64),
  },
  error: null,
} satisfies StaffAvailabilityPreviewResponse;

export const STAFF_AVAILABILITY_END_PAUSE_RECEIPT_RESPONSE = {
  success: true,
  message: '成功結束暫停接案',
  data: {
    staff_id: 11,
    action: 'end_pause',
    block: STAFF_AVAILABILITY_CLOSED_PAUSE_BLOCK,
    aggregate_version: 5,
    preview_fingerprint: 'b'.repeat(64),
    idempotency_key: 'availability-end-pause-11-01',
  },
  error: null,
} satisfies StaffAvailabilityReceiptResponse;

export const STAFF_AVAILABILITY_APPLY_PAYLOAD = {
  action: 'create_pause',
  reason: '去敏暫停接案',
  start_date: '2026-10-01',
  end_date: null,
  block_id: null,
  resume_date: null,
  expected_version: 2,
  preview_fingerprint: 'a'.repeat(64),
} satisfies StaffAvailabilityApplyPayload;
