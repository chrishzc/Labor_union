/**
 * File: matching_coordination_contract_fixtures.ts
 * Description: 提供 M3 React client 的最小完整公開契約樣本。
 */
import type {
  MatchingSourceTuple,
} from '../../../api/matching_coordination/matching_coordination_schemas';

const SHA_A = 'a'.repeat(64);
const SHA_B = 'b'.repeat(64);

const SOURCE_KINDS = [
  'orders_terms',
  'orders_service_dates',
  'scheduling_availability',
  'scheduling_effective_generation',
  'staff_profile_definition',
  'staff_profile_values',
  'staff_lifecycle',
  'matching_criteria_snapshot',
  'candidate_pool',
  'matching_package',
  'incumbent_assignment',
  'leave_request_or_outcome',
  'assignment_conversion_reference',
] as const;

export const MATCHING_SOURCE_TUPLE: MatchingSourceTuple = {
  items: SOURCE_KINDS.map((sourceKind, index) => ({
    source_kind: sourceKind,
    source_id: `${sourceKind}-fixture`,
    version: index + 1,
    fingerprint: SHA_A,
  })),
};

export const MATCHING_SNAPSHOT = {
  snapshot_id: 'snapshot-1',
  case_no: 'CASE-001',
  criteria_version: 1,
  criteria: [['district', '北區'] as [string, unknown]],
  source_versions: MATCHING_SOURCE_TUPLE.items,
  fingerprint: SHA_A,
  created_at: '2026-08-23T01:00:00+08:00',
  superseded_by: null,
};

export const MATCHING_CANDIDATE = {
  candidate_id: 'candidate-1',
  staff_id: 7,
  eligibility: 'eligible' as const,
  criteria_results: [],
  rejection_reasons: [],
  coverage_evidence: ['2026-08-24'],
  willingness: 'pending' as const,
  notification_lineage: [],
  staff_name: '測試月嫂',
};

export const MATCHING_PACKAGE = {
  package_id: 'package-1',
  version: 1,
  mode: 'single' as const,
  segments: [
    { staff_id: 7, service_dates: ['2026-08-24'], sequence: 1 },
  ],
  required_service_dates: ['2026-08-24'],
  candidate_results: [MATCHING_CANDIDATE],
  criteria_snapshot_id: 'snapshot-1',
  source_versions: MATCHING_SOURCE_TUPLE,
  blockers: [],
  warnings: [],
  state: 'awaiting_caregiver_willingness' as const,
  fingerprint: SHA_B,
};

export const MATCHING_QUERY_DATA = {
  case_no: 'CASE-001',
  snapshot: MATCHING_SNAPSHOT,
  package: MATCHING_PACKAGE,
  candidates: [MATCHING_CANDIDATE],
  source_versions: MATCHING_SOURCE_TUPLE,
  refusal_history: [],
  willingness_lineage: [],
  expected_source_versions_match: true,
};

export const MATCHING_CRITERIA_DIFF = {
  before_snapshot_id: 'snapshot-0',
  after_snapshot_id: 'snapshot-1',
  added: ['district'],
  removed: [],
  changed: [],
  unchanged: [],
  affected_candidate_ids: ['candidate-1'],
  affected_recipient_ids: ['staff-7'],
  resend_eligible: true,
  diff_fingerprint: SHA_A,
  refusal_routes: [],
};

export const MATCHING_ZERO_CANDIDATE = {
  alternative_id: 'alternative-1',
  policy_id: 'policy-1',
  policy_version: 1,
  relaxed_criteria: ['district'],
  unchanged_hard_criteria: ['service_dates'],
  candidate_result: MATCHING_CANDIDATE,
  risk_warnings: ['需人工確認區域'],
  deterministic_rank: 1,
  preview_fingerprint: SHA_A,
};

export const MATCHING_LEAVE_IMPACT = {
  receipt_key: 'leave-receipt-1',
  result_state: 'leave_deferred',
  package_id: 'package-1',
  criteria_snapshot_id: 'snapshot-1',
  rematch_required: false,
  resolution_type: 'defer_following_assignments',
  original_work_date: '2026-08-24',
  resulting_work_date: '2026-08-25',
  outcome_event_ids: ['leave-event-1'],
  source_versions: MATCHING_SOURCE_TUPLE,
  receipt_fingerprint: SHA_A,
  preview_fingerprint: SHA_B,
  substitute_staff_id: null,
};

export const MATCHING_SERVICE_DATE_REMATCH = {
  outcome_kind: 'availability_confirmation',
  availability_confirmation: {
    intent_id: 'availability-intent-1',
    case_no: 'CASE-001',
    assignment_id: 23,
    staff_id: 7,
    original_service_dates: ['2026-08-24'],
    shifted_service_dates: ['2026-08-25'],
    source_fingerprint: SHA_A,
  },
  reassignment_reference: null,
};

export const MATCHING_APPLY_RECEIPT = {
  receipt_id: 'receipt-1',
  command_name: 'ApplyInitialCriteriaSnapshot' as const,
  command_fingerprint: SHA_A,
  preview_fingerprint: SHA_B,
  source_versions: MATCHING_SOURCE_TUPLE,
  decision_event_id: null,
  package_id: 'package-1',
  outbox_intent_ids: [],
  result_state: 'criteria_snapshotted' as const,
  cross_domain_request: null,
  zero_candidate_decision: null,
  willingness_lineage: null,
  notification_intents: [],
  criteria_recontact_intents: [],
};

export function successEnvelope(data: unknown) {
  return { success: true, message: 'Success', data, error: null };
}

export const QUERY_REQUEST = { expected_source_versions: MATCHING_SOURCE_TUPLE };
export const PREVIEW_INITIAL_REQUEST = {
  reason: '建立初始條件',
  expected_source_versions: MATCHING_SOURCE_TUPLE,
};
export const PREVIEW_PACKAGE_REQUEST = {
  reason: '建立媒合包',
  expected_source_versions: MATCHING_SOURCE_TUPLE,
  criteria_snapshot_id: 'snapshot-1',
  required_service_dates: ['2026-08-24'],
  segments: [{ staff_id: 7, service_dates: ['2026-08-24'], sequence: 1 }],
};
export const PREVIEW_DIFF_REQUEST = {
  reason: '條件變更',
  expected_source_versions: MATCHING_SOURCE_TUPLE,
  before_snapshot_id: 'snapshot-0',
  after_snapshot_id: 'snapshot-1',
};
export const PREVIEW_ZERO_REQUEST = {
  reason: '零候選替代方案',
  expected_source_versions: MATCHING_SOURCE_TUPLE,
  criteria_snapshot_id: 'snapshot-1',
  policy_id: 'policy-1',
  policy_version: 1,
  relaxed_criteria: ['district'],
};
export const PREVIEW_REMATCH_REQUEST = {
  reason: '重新媒合',
  expected_source_versions: MATCHING_SOURCE_TUPLE,
  criteria_snapshot_id: 'snapshot-1',
  package_id: 'package-1',
};
export const PREVIEW_LEAVE_REQUEST = {
  reason: '請假影響',
  expected_source_versions: MATCHING_SOURCE_TUPLE,
  package_id: 'package-1',
  criteria_snapshot_id: 'snapshot-1',
  receipt_key: 'leave-receipt-1',
  expected_leave_version: 1,
  original_staff_id: 7,
};
export const PREVIEW_SERVICE_DATE_REQUEST = {
  reason: '服務日期異動',
  expected_source_versions: MATCHING_SOURCE_TUPLE,
  criteria_snapshot_id: 'snapshot-1',
  package_id: 'package-1',
  assignment_id: 23,
  original_staff_id: 7,
  original_service_dates: ['2026-08-24'],
  shifted_service_dates: ['2026-08-25'],
};

export const APPLY_OPTIONS = {
  correlationId: 'matching-apply-correlation-1',
  idempotencyKey: 'matching-apply-idempotency-1',
};

export const SHA_A_FIXTURE = SHA_A;
