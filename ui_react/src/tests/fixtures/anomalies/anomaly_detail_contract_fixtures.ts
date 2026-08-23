/**
 * File: anomaly_detail_contract_fixtures.ts
 * Description: 異常詳情與修復上下文的去敏嚴格契約測試向量。
 */

import type {
  AnomalyDetailResponse,
  AnomalyDetailView,
  AnomalyRecoveryContextView,
  AnomalyRecoveryResponse,
} from '../../../api/anomalies/anomaly_detail_schemas';

const DETAIL_FINGERPRINT = 'a'.repeat(64);
const OCCURRENCE_FINGERPRINT = 'b'.repeat(64);

const VALID_DISPLAY_SNAPSHOT = {
  redaction_version: 'anomaly-safe.v1' as const,
  definition_code: 'finance_import_manual_review',
  fields: [
    {
      kind: 'money_ntd' as const,
      key: 'amount_delta_ntd',
      value: 1200,
    },
    {
      kind: 'identity' as const,
      key: 'case_no',
      value: 'CASE-SYNTH-042',
    },
    {
      kind: 'date' as const,
      key: 'holiday_date',
      value: '2026-08-22',
    },
    {
      kind: 'code_list' as const,
      key: 'issue_codes',
      value: ['AMOUNT_MISMATCH'],
    },
    {
      kind: 'code' as const,
      key: 'notification_reason',
      value: 'missing_document',
    },
    {
      kind: 'identity_list' as const,
      key: 'overdue_obligations',
      value: ['obligation:SYNTH-19'],
    },
    {
      kind: 'masked_text' as const,
      key: 'staff_name',
      value: 'P***',
    },
    {
      kind: 'integer' as const,
      key: 'version',
      value: 7,
    },
  ],
};

export const VALID_ANOMALY_DETAIL_VIEW: AnomalyDetailView = {
  summary: {
    fingerprint: DETAIL_FINGERPRINT,
    definition_code: 'finance_import_manual_review',
    source_domain: 'finance_import',
    source_identity: 'opaque-subject:SYNTH-42',
    source_version: 7,
    severity: 'warning',
    predicate_active: true,
    workflow_status: 'open',
    workflow_version: 3,
    display_snapshot: VALID_DISPLAY_SNAPSHOT,
    staff_calendar_navigation: null,
  },
  timeline: [
    {
      action: 'claim',
      expected_workflow_version: 2,
      resulting_workflow_version: 3,
      actor: 'O***',
      reason: '異常已進入人工確認流程。',
      correlation_id: 'anomaly-detail:SYNTH-42',
      created_at: '2026-08-22T09:30:00+00:00',
    },
    {
      action: 'resolve',
      expected_workflow_version: 3,
      resulting_workflow_version: 4,
      actor: 'S***',
      reason: '人工處理進度已更新；不代表根事實已修正。',
      correlation_id: 'anomaly-detail:SYNTH-43',
      created_at: '2026-08-22T10:00:00+00:00',
    },
  ],
  available_actions: [
    {
      action_key: 'review_safe_projection',
      label: '檢視安全投影',
      owning_domain: 'finance_import',
      form_schema_key: 'finance_import.review.v1',
      source_binding_keys: ['source_version'],
      source_bindings: null,
      required_operator_inputs: ['evidence', 'reason'],
      preview_operation: 'PreviewSafeProjection',
      apply_operation: 'ApplySafeProjection',
      required_capability: 'finance_import.review',
      completion_predicate: 'source_predicate_cleared',
      action_contract_version: 1,
      requires_preview: true,
    },
  ],
};

export const VALID_ANOMALY_DETAIL_RESPONSE: AnomalyDetailResponse = {
  success: true,
  message: '成功取得異常詳情',
  data: VALID_ANOMALY_DETAIL_VIEW,
  error: null,
};

const VALID_OCCURRENCE_SNAPSHOT = {
  redaction_version: 'anomaly-safe.v1' as const,
  definition_code: 'finance_import_manual_review',
  fields: [
    {
      kind: 'identity_list' as const,
      key: 'affected_obligation_identities',
      value: ['obligation:SYNTH-19'],
    },
    {
      kind: 'identity_list' as const,
      key: 'affected_order_identities',
      value: ['order:SYNTH-17'],
    },
    {
      kind: 'money_ntd' as const,
      key: 'amount_delta_ntd',
      value: 1200,
    },
    {
      kind: 'code_list' as const,
      key: 'domain_blockers',
      value: ['manual_review'],
    },
    {
      kind: 'identity' as const,
      key: 'finance_import_batch_id',
      value: 'batch:SYNTH-09',
    },
    {
      kind: 'identity' as const,
      key: 'finance_import_row_id',
      value: 'row:SYNTH-42',
    },
    {
      kind: 'boolean' as const,
      key: 'integrity_blocker_active',
      value: false,
    },
    {
      kind: 'datetime' as const,
      key: 'occurred_at',
      value: '2026-08-22T09:30:00+00:00',
    },
    {
      kind: 'identity' as const,
      key: 'original_refund_ledger_entry_id',
      value: 'ledger-refund:SYNTH-42',
    },
    {
      kind: 'code_list' as const,
      key: 'reason_codes',
      value: ['AMOUNT_MISMATCH'],
    },
    {
      kind: 'boolean' as const,
      key: 'root_condition_active',
      value: true,
    },
    {
      kind: 'identity' as const,
      key: 'source_identity',
      value: 'event:SYNTH-42',
    },
    {
      kind: 'integer' as const,
      key: 'source_version',
      value: 7,
    },
  ],
};

export const VALID_ANOMALY_RECOVERY_CONTEXT_VIEW: AnomalyRecoveryContextView = {
  fingerprint: DETAIL_FINGERPRINT,
  definition_code: 'finance_import_manual_review',
  source_domain: 'finance_import',
  source_identity: 'opaque-subject:SYNTH-42',
  source_version: 7,
  severity: 'warning',
  predicate_active: true,
  workflow_status: 'open',
  workflow_version: 3,
  domain_blocker_active: true,
  projection_freshness: 'fresh',
  root_fact_snapshot: {
    occurred_at: '2026-08-22T09:30:00+00:00',
    source_version: 7,
    finance_import_row_identity: 'row:SYNTH-42',
    finance_import_batch_identity: 'batch:SYNTH-09',
    original_refund_ledger_entry_identity: 'ledger-refund:SYNTH-42',
    amount_delta_ntd: 1200,
    root_condition_active: true,
    integrity_blocker_active: false,
    affected_order_identities: ['order:SYNTH-17'],
    affected_obligation_identities: ['obligation:SYNTH-19'],
    domain_blockers: ['manual_review'],
    reason_codes: ['AMOUNT_MISMATCH'],
  },
  occurrence_timeline: [
    {
      occurrence_fingerprint: OCCURRENCE_FINGERPRINT,
      definition_code: 'finance_import_manual_review',
      source_event_identity: 'event:SYNTH-42',
      finance_import_row_id: 42,
      finance_import_batch_id: 9,
      source_version: 7,
      occurred_at: '2026-08-22T09:30:00+00:00',
      bounded_snapshot: VALID_OCCURRENCE_SNAPSHOT,
    },
  ],
  workflow_timeline: [
    {
      action: 'resolve',
      expected_workflow_version: 2,
      resulting_workflow_version: 3,
      actor: 'O***',
      reason: '人工處理進度已更新；不代表根事實已修正。',
      correlation_id: 'anomaly-recovery:SYNTH-42',
      created_at: '2026-08-22T10:00:00+00:00',
    },
  ],
  available_actions: [
    {
      action_key: 'repair_finance_projection',
      label: '預覽財務投影修復',
      owning_domain: 'finance_import',
      form_schema_key: 'finance_import.recovery.v1',
      source_binding_keys: ['finance_import_row_identity', 'source_version'],
      source_bindings: [
        {
          kind: 'identity',
          key: 'finance_import_row_identity',
          value: 'row:SYNTH-42',
        },
        { kind: 'version', key: 'source_version', value: 7 },
      ],
      required_operator_inputs: ['evidence', 'reason'],
      preview_operation: 'PreviewFinanceProjectionRepair',
      apply_operation: 'ApplyFinanceProjectionRepair',
      required_capability: 'finance_import.recovery',
      completion_predicate: 'root_condition_cleared',
      action_contract_version: 1,
      requires_preview: true,
    },
  ],
};

export const VALID_ANOMALY_RECOVERY_RESPONSE: AnomalyRecoveryResponse = {
  success: true,
  message: '成功取得異常修復上下文',
  data: VALID_ANOMALY_RECOVERY_CONTEXT_VIEW,
  error: null,
};

export const INVALID_ANOMALY_DETAIL_UNKNOWN_EVIDENCE_KIND = {
  ...VALID_ANOMALY_DETAIL_RESPONSE,
  data: {
    ...VALID_ANOMALY_DETAIL_VIEW,
    summary: {
      ...VALID_ANOMALY_DETAIL_VIEW.summary,
      display_snapshot: {
        ...VALID_DISPLAY_SNAPSHOT,
        fields: [
          {
            kind: 'unknown_evidence',
            key: 'case_no',
            value: 'CASE-SYNTH-042',
          },
        ],
      },
    },
  },
};

export const INVALID_ANOMALY_DETAIL_EXTRA_FIELD = {
  ...VALID_ANOMALY_DETAIL_RESPONSE,
  leaked_projection_payload: 'must-be-rejected',
};

export const INVALID_ANOMALY_RECOVERY_MISSING_BINDING = {
  ...VALID_ANOMALY_RECOVERY_RESPONSE,
  data: {
    ...VALID_ANOMALY_RECOVERY_CONTEXT_VIEW,
    available_actions: [
      {
        ...VALID_ANOMALY_RECOVERY_CONTEXT_VIEW.available_actions[0],
        source_binding_keys: [
          'finance_import_row_identity',
          'source_version',
          'missing_binding',
        ],
      },
    ],
  },
};

export const INVALID_ANOMALY_RECOVERY_MALFORMED_IDENTITY = {
  ...VALID_ANOMALY_RECOVERY_RESPONSE,
  data: {
    ...VALID_ANOMALY_RECOVERY_CONTEXT_VIEW,
    root_fact_snapshot: {
      ...VALID_ANOMALY_RECOVERY_CONTEXT_VIEW.root_fact_snapshot,
      finance_import_row_identity: '',
    },
  },
};

export const INVALID_ANOMALY_DETAIL_MALFORMED_DATE = {
  ...VALID_ANOMALY_DETAIL_RESPONSE,
  data: {
    ...VALID_ANOMALY_DETAIL_VIEW,
    summary: {
      ...VALID_ANOMALY_DETAIL_VIEW.summary,
      display_snapshot: {
        ...VALID_DISPLAY_SNAPSHOT,
        fields: [
          {
            kind: 'date',
            key: 'holiday_date',
            value: '2026/08/22',
          },
        ],
      },
    },
  },
};
