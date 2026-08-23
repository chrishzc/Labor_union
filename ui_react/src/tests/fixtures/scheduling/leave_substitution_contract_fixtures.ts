/**
 * File: leave_substitution_contract_fixtures.ts
 * Description: 提供請假代班 client 的去敏 strict assignments、Preview、Apply 與 receipt fixtures。
 */
import type {
  LeaveSubstitutionApplyRequest,
  LeaveSubstitutionAssignment,
  LeaveSubstitutionPreview,
  LeaveSubstitutionPreviewRequest,
  LeaveSubstitutionReceipt,
} from '../../../api/scheduling/leave_substitution_schemas';

export const LEAVE_CASE_NO = 'CASE-LEAVE-001';
export const LEAVE_FINGERPRINT = 'a'.repeat(64);

export const LEAVE_ASSIGNMENTS: LeaveSubstitutionAssignment[] = [
  {
    assignment_id: 31,
    staff_id: 11,
    assigned_start_date: '2026-08-01',
    assigned_end_date: '2026-08-05',
    official_schedules: [{ schedule_id: 301, work_date: '2026-08-03' }],
  },
];

export const LEAVE_OBSERVED_ASSIGNMENTS: LeaveSubstitutionAssignment[] = [
  {
    assignment_id: 32,
    staff_id: 12,
    assigned_start_date: '2026-08-03',
    assigned_end_date: '2026-08-03',
    official_schedules: [{ schedule_id: 302, work_date: '2026-08-03' }],
  },
];

export const LEAVE_PREVIEW_REQUEST: LeaveSubstitutionPreviewRequest = {
  original_assignment_id: 31,
  items: [
    {
      original_schedule_id: 301,
      work_date: '2026-08-03',
      resolution_type: 'substitute',
      substitute_staff_id: 12,
      is_double_pay: false,
    },
  ],
  leave_request_id: 77,
  expected_leave_request_version: 4,
};

export const LEAVE_APPLY_REQUEST: LeaveSubstitutionApplyRequest = {
  ...LEAVE_PREVIEW_REQUEST,
  expected_order_version: 3,
  expected_scheduling_version: 2,
  expected_client_finance_version: 5,
  expected_payroll_version: 4,
  preview_fingerprint: LEAVE_FINGERPRINT,
  reason: '正式處理請假代班',
};

const LEAVE_LINKED_REQUEST = {
  request_id: 77,
  expected_version: 4,
  resolved_version: 4,
  status: 'resolved' as const,
  receipt_key: 'leave-apply-001',
  notification_intent: 'enqueued' as const,
};

const LEAVE_ASSIGNMENT_PLAN = {
  candidate_key: 'CASE-LEAVE-001:g3:a1',
  staff_id: 12,
  sequence: 1,
  assigned_start_date: '2026-08-03',
  assigned_end_date: '2026-08-03',
  official_service_dates: ['2026-08-03'],
  actual_hours: 8,
  lineage_source_assignment_ids: [31],
};

const LEAVE_IMPACT = {
  expected_version: 1,
  resulting_version: 2,
  fingerprint: LEAVE_FINGERPRINT,
  blockers: [],
};

export const LEAVE_PREVIEW: LeaveSubstitutionPreview = {
  case_no: LEAVE_CASE_NO,
  order_version: 3,
  scheduling_version: 2,
  scheduling_generation: 3,
  client_finance_version: 5,
  payroll_version: 4,
  cancelled_assignment_ids: [31],
  assignments: [LEAVE_ASSIGNMENT_PLAN],
  outcomes: [
    {
      item_index: 0,
      original_schedule_id: 301,
      original_assignment_id: 31,
      original_staff_id: 11,
      original_work_date: '2026-08-03',
      resolution_type: 'substitute',
      leave_occupancy_date: '2026-08-03',
      resulting_service_date: '2026-08-03',
      resulting_staff_id: 12,
      resulting_assignment_key: 'CASE-LEAVE-001:g3:a1',
      is_double_pay: false,
    },
  ],
  client_finance_impact: LEAVE_IMPACT,
  payroll_impact: LEAVE_IMPACT,
  orders_impact: LEAVE_IMPACT,
  calendar_candidate: {
    before_service_day_count: 5,
    after_service_day_count: 5,
    before_service_start_date: '2026-08-01',
    before_service_end_date: '2026-08-05',
    after_service_start_date: '2026-08-01',
    after_service_end_date: '2026-08-05',
    contracted_service_day_count: 5,
    deferred_day_count: 0,
    substitute_day_count: 1,
    leave_day_count: 1,
    holiday_rest_day_count: 0,
    fixed_rest_day_count: 0,
    holiday_version: 'holiday-v1',
    holiday_rows: [],
    conservation_status: 'conserved',
    day_cells: [
      {
        calendar_date: '2026-08-03',
        before_kind: 'official_service',
        after_kind: 'official_service',
        change_kind: 'substituted',
        before_staff_id: 11,
        after_staff_id: 12,
      },
    ],
  },
  apply_readiness: { status: 'ready', blockers: [] },
  linked_request: LEAVE_LINKED_REQUEST,
  preview_fingerprint: LEAVE_FINGERPRINT,
};

export const LEAVE_RECEIPT: LeaveSubstitutionReceipt = {
  batch_key: 'leave-apply-001',
  case_no: LEAVE_CASE_NO,
  order_version: 4,
  scheduling_generation: 3,
  scheduling_version: 3,
  client_finance_version: 6,
  payroll_version: 5,
  outcome_event_ids: [901],
  preview_fingerprint: LEAVE_FINGERPRINT,
  linked_request: {
    ...LEAVE_LINKED_REQUEST,
    resolved_version: 5,
  },
};

export const LEAVE_ASSIGNMENTS_RESPONSE = {
  success: true,
  message: '成功取得請假與代班正式服務指派',
  data: LEAVE_ASSIGNMENTS,
  error: null,
};

export const LEAVE_PREVIEW_RESPONSE = {
  success: true,
  message: '成功產生請假與代班預覽',
  data: LEAVE_PREVIEW,
  error: null,
};

export const LEAVE_APPLY_RESPONSE = {
  success: true,
  message: '成功套用請假與代班處理',
  data: LEAVE_RECEIPT,
  error: null,
};

export const LEAVE_TYPED_CONFLICT_RESPONSE = {
  detail: {
    error: {
      category: 'conflict',
      code: 'stale_preview',
      message: 'Leave/substitution facts changed after Preview.',
      field_errors: [],
      domain_blockers: ['scheduling_version'],
      retryable: false,
      correlation_id: 'leave-conflict-correlation',
      current_version: 3,
    },
  },
};
