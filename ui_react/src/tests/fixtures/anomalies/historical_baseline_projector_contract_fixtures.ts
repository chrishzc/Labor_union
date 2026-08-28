/**
 * File: historical_baseline_projector_contract_fixtures.ts
 * Description: HPROJ v2 React strict readback fixtures。
 */
import type { HistoricalBaselineProjectorReadModel } from '../../../api/anomalies/historical_baseline_projector_schemas';

const fingerprint = (character: string): string => character.repeat(64);

export const HISTORICAL_BASELINE_CASE_NO = 'CASE-HPROJ-1';

export const HISTORICAL_BASELINE_PROJECTOR_VIEW: HistoricalBaselineProjectorReadModel = {
  delivery: {
    delivery_identity: fingerprint('a'),
    source_trigger_identity: 'owner-repair:orders:4',
    payload_digest: fingerprint('b'),
    source_kind: 'owner_repair',
    source_domain: 'orders',
    source_event_identity: 'orders-repair:4',
    source_version: 4,
    partition_key: HISTORICAL_BASELINE_CASE_NO,
    projection_sequence: 7,
    projector_receipt_identity: fingerprint('c'),
    status: 'committed_unverified',
    attempt_count: 2,
    max_attempts: 5,
    next_attempt_at: null,
    lease_expires_at: null,
    last_error_code: 'historical_baseline_post_commit_readback_unknown',
  },
  receipt: {
    projector_receipt_identity: fingerprint('c'),
    source_trigger_identity: 'owner-repair:orders:4',
    source_trigger_version: 4,
    payload_digest: fingerprint('b'),
    idempotency_key: 'historical-baseline.orders.4',
    case_no: HISTORICAL_BASELINE_CASE_NO,
    order_identity: 'order:1',
    catalog_identity: fingerprint('d'),
    catalog_version: 2,
    whole_vector_fingerprint: fingerprint('e'),
    whole_vector_count: 21,
    emitted_occurrence_set_digest: fingerprint('f'),
    emitted_occurrence_set_count: 2,
    active_membership_set_digest: fingerprint('1'),
    active_membership_set_count: 2,
    umbrella_identity: fingerprint('2'),
    projection_sequence: 7,
    current_alert_fingerprint: fingerprint('3'),
    expected_readback_digest: fingerprint('4'),
    result_state: 'held_active',
  },
  active_memberships: [
    { membership_identity: fingerprint('5'), set_ordinal: 1, occurrence_identity: fingerprint('6') },
    { membership_identity: fingerprint('7'), set_ordinal: 2, occurrence_identity: fingerprint('8') },
  ],
  post_commit_readback: {
    readback_identity: fingerprint('9'),
    readback_attempt: 1,
    expected_readback_digest: fingerprint('4'),
    actual_readback_digest: null,
    emitted_occurrence_set_digest: null,
    emitted_occurrence_set_count: null,
    active_membership_set_digest: null,
    active_membership_set_count: null,
    state_event_set_digest: null,
    successor_set_digest: null,
    workflow_event_set_digest: null,
    current_alert_fingerprint: null,
    result: 'unknown',
    error_code: 'historical_baseline_post_commit_readback_unknown',
  },
  current_alert: {
    fingerprint: fingerprint('3'),
    definition_code: 'HISTORICAL-BASELINE-ROOTS-001',
    definition_version: 1,
    source_domain: 'historical_baseline',
    source_identity: fingerprint('2'),
    source_version: 7,
    predicate_active: true,
    workflow_status: 'open',
    workflow_version: 0,
    projection_version: 7,
    display: {
      case_no: HISTORICAL_BASELINE_CASE_NO,
      earliest_blocked_step: 3,
      active_count: 2,
      repair_referrals: [
        {
          step: 3,
          contract_id: 'historical-baseline.orders.actual-start',
          owner_domain: 'orders',
          repair_target: 'orders',
          repair_capability: 'orders.historical_review.remediate',
        },
        {
          step: 8,
          contract_id: 'historical-baseline.scheduling.assignment',
          owner_domain: 'scheduling',
          repair_target: 'scheduling',
          repair_capability: 'scheduling.assignment.repair',
        },
      ],
      projection_fingerprint: fingerprint('0'),
    },
  },
  reconciliation: {
    status: 'outcome_unknown',
    delivery_identity: fingerprint('a'),
    projector_receipt_identity: fingerprint('c'),
    reason_code: 'historical_baseline_post_commit_readback_unknown',
    referral: 'retry_original_trigger_reconcile',
  },
};

export const HISTORICAL_BASELINE_PROJECTOR_RESPONSE = {
  success: true as const,
  message: '成功載入案件最新的歷史基線投影',
  data: HISTORICAL_BASELINE_PROJECTOR_VIEW,
  error: null,
};
