/**
 * File: finance_owner_recovery_target.test.ts
 * Description: 驗證異常頁只依 exact owner form schema 與 typed bindings 路由財務人工修正工作區。
 */
import { describe, expect, it } from 'vitest';
import { AnomalyDetailViewSchema, AnomalyRecoveryContextViewSchema } from '../api/anomalies/anomaly_detail_schemas';
import { financeOwnerRecoveryTarget, payoutOwnerDetailTarget } from '../adapters/anomalies/finance_owner_recovery_target';

const fingerprint = 'a'.repeat(64);

function context(action: Record<string, unknown>) {
  const owner = typeof action.owning_domain === 'string' ? action.owning_domain : 'government_subsidy';
  const formSchema = typeof action.form_schema_key === 'string' ? action.form_schema_key : '';
  const definitionCode = formSchema.startsWith('client_finance.')
    ? 'client_over_refund_recovery_open'
    : formSchema.startsWith('staff_payables.overpayment_')
      ? 'staff_overpayment_recovery_open'
      : formSchema === 'staff_payables.payout_reconciliation.v1'
        ? 'PAYOUT-001'
        : 'GOVSUB-006';
  return AnomalyRecoveryContextViewSchema.parse({
    fingerprint,
    definition_code: definitionCode,
    source_domain: owner,
    source_identity: 'source:17',
    source_version: 3,
    severity: 'blocking',
    predicate_active: true,
    workflow_status: 'open',
    workflow_version: 1,
    domain_blocker_active: true,
    projection_freshness: 'fresh',
    root_fact_snapshot: {
      occurred_at: '2026-08-27T10:00:00+08:00',
      source_version: 3,
      finance_import_row_identity: 'row:17',
      finance_import_batch_identity: 'batch:2',
      original_refund_ledger_entry_identity: null,
      amount_delta_ntd: 1000,
      root_condition_active: true,
      integrity_blocker_active: false,
      affected_order_identities: [],
      affected_obligation_identities: [],
      domain_blockers: ['pending_review'],
      reason_codes: ['OVERPAYMENT'],
    },
    occurrence_timeline: [],
    workflow_timeline: [],
    available_actions: [action],
  });
}

function action(overrides: Record<string, unknown>) {
  return {
    action_key: 'dispose_government_subsidy_overpayment',
    label: '人工修正',
    owning_domain: 'government_subsidy',
    form_schema_key: 'government_subsidy.overpayment.disposition.v1',
    source_binding_keys: ['overpayment_identity', 'overpayment_version'],
    source_bindings: [
      { kind: 'identity', key: 'overpayment_identity', value: 'gov-overpayment:17' },
      { kind: 'version', key: 'overpayment_version', value: 3 },
    ],
    required_operator_inputs: ['disposition', 'evidence_reference', 'offset_amounts', 'offset_targets', 'reason', 'return_due_date'],
    preview_operation: 'PreviewGovernmentSubsidyOverpaymentDisposition',
    apply_operation: 'ApplyGovernmentSubsidyOverpaymentDisposition',
    required_capability: 'government_subsidy.overpayment.disposition',
    completion_predicate: 'government_subsidy_overpayment_disposed',
    action_contract_version: 1,
    requires_preview: true,
    ...overrides,
  };
}

function payoutDetail(overrides: { sourceIdentity?: string; sourceDomain?: string; predicateActive?: boolean; action?: Record<string, unknown> } = {}) {
  const sourceIdentity = overrides.sourceIdentity ?? 'staff-obligation:17';
  return AnomalyDetailViewSchema.parse({
    summary: {
      fingerprint,
      definition_code: 'PAYOUT-001',
      source_domain: overrides.sourceDomain ?? 'staff_payables',
      source_identity: sourceIdentity,
      source_version: 3,
      severity: 'warning',
      predicate_active: overrides.predicateActive ?? true,
      workflow_status: 'open',
      workflow_version: 1,
      display_snapshot: {
        redaction_version: 'anomaly-safe.v1',
        definition_code: 'PAYOUT-001',
        fields: [],
      },
      staff_calendar_navigation: null,
    },
    timeline: [],
    available_actions: [action({
      action_key: 'reconcile_overdue_staff_payable',
      owning_domain: 'staff_payables',
      form_schema_key: 'staff_payables.payout_reconciliation.v1',
      source_binding_keys: ['obligation_identity', 'staff_id'],
      source_bindings: [
        { kind: 'identity', key: 'obligation_identity', value: sourceIdentity },
        { kind: 'identity', key: 'staff_id', value: '42' },
      ],
      required_operator_inputs: ['finance_import_row_ids', 'reason'],
      preview_operation: 'PreviewStaffPayout',
      apply_operation: 'ApplyStaffPayout',
      required_capability: 'staff_payables.payout.apply',
      completion_predicate: 'staff_payable_obligation_settled',
      ...overrides.action,
    })],
  });
}

describe('financeOwnerRecoveryTarget', () => {
  it('routes government owner identity from typed source bindings', () => {
    expect(financeOwnerRecoveryTarget(context(action({})))).toEqual({
      kind: 'government',
      overpaymentIdentity: 'gov-overpayment:17',
    });
  });

  it('routes client and staff contracts without inferring from anomaly display text', () => {
    const client = action({
      action_key: 'collect_client_over_refund_recovery',
      owning_domain: 'client_finance',
      form_schema_key: 'client_finance.over_refund_recovery.collection.v1',
      source_binding_keys: ['account_version', 'case_no', 'finance_import_row_identity', 'matching_identity', 'matching_version', 'recovery_identity', 'recovery_version'],
      source_bindings: [
        { kind: 'version', key: 'account_version', value: 4 },
        { kind: 'identity', key: 'case_no', value: 'CASE-17' },
        { kind: 'identity', key: 'finance_import_row_identity', value: '77' },
        { kind: 'identity', key: 'matching_identity', value: 'client-match:17' },
        { kind: 'version', key: 'matching_version', value: 1 },
        { kind: 'identity', key: 'recovery_identity', value: 'client-recovery:17' },
        { kind: 'version', key: 'recovery_version', value: 2 },
      ],
      required_operator_inputs: ['evidence_reference', 'reason'],
      preview_operation: 'PreviewCollectMatchedClientOverRefundRecovery',
      apply_operation: 'ApplyCollectMatchedClientOverRefundRecovery',
      required_capability: 'client_finance.recovery.collect',
      completion_predicate: 'client_over_refund_recovery_remaining_updated',
    });
    const staff = action({
      owning_domain: 'staff_payables',
      form_schema_key: 'staff_payables.overpayment_recovery.adjustment.v1',
      source_binding_keys: ['recovery_identity', 'recovery_version', 'staff_id', 'staff_payables_version'],
      source_bindings: [
        { kind: 'identity', key: 'recovery_identity', value: 'staff-recovery:17' },
        { kind: 'version', key: 'recovery_version', value: 3 },
        { kind: 'identity', key: 'staff_id', value: '42' },
        { kind: 'version', key: 'staff_payables_version', value: 7 },
      ],
      action_key: 'adjust_staff_overpayment_recovery',
      required_operator_inputs: ['adjustment_amount', 'evidence_reference', 'reason'],
      preview_operation: 'PreviewStaffOverpaymentRecoveryAdjustment',
      apply_operation: 'ApplyStaffOverpaymentRecoveryAdjustment',
      required_capability: 'staff_payables.recovery.adjust',
      completion_predicate: 'staff_overpayment_recovery_remaining_updated',
    });

    expect(financeOwnerRecoveryTarget(context(client))).toEqual({
      kind: 'client', caseNo: 'CASE-17', recoveryIdentity: 'client-recovery:17', financeImportRowId: 77,
    });
    expect(financeOwnerRecoveryTarget(context(staff))).toEqual({
      kind: 'staff', staffId: 42, recoveryIdentity: 'staff-recovery:17', financeImportRowId: undefined,
    });
  });

  it('does not route PAYOUT-001 through the Finance recovery context', () => {
    const payout = action({
      action_key: 'reconcile_overdue_staff_payable',
      owning_domain: 'staff_payables',
      form_schema_key: 'staff_payables.payout_reconciliation.v1',
      source_binding_keys: ['obligation_identity', 'staff_id'],
      source_bindings: [
        { kind: 'identity', key: 'obligation_identity', value: 'staff-obligation:17' },
        { kind: 'identity', key: 'staff_id', value: '42' },
      ],
      required_operator_inputs: ['finance_import_row_ids', 'reason'],
      preview_operation: 'PreviewStaffPayout',
      apply_operation: 'ApplyStaffPayout',
      required_capability: 'staff_payables.payout.apply',
      completion_predicate: 'staff_payable_obligation_settled',
    });

    expect(financeOwnerRecoveryTarget(context(payout))).toBeNull();
    expect(financeOwnerRecoveryTarget(context({
      ...payout,
      source_bindings: [
        { kind: 'identity', key: 'obligation_identity', value: 'staff-obligation:17' },
        { kind: 'identity', key: 'staff_id', value: '0' },
      ],
    }))).toBeNull();
    expect(financeOwnerRecoveryTarget({ available_actions: [payout] } as never)).toBeNull();
  });

  it('routes PAYOUT-001 from current typed detail when finance recovery is unavailable', () => {
    expect(payoutOwnerDetailTarget(payoutDetail())).toEqual({
      kind: 'staff_payout', staffId: 42, obligationIdentity: 'staff-obligation:17',
    });
  });

  it('fails closed for inactive, wrong-owner, identity-drift, or contract-drift payout detail', () => {
    expect(payoutOwnerDetailTarget(payoutDetail({ predicateActive: false }))).toBeNull();
    expect(payoutOwnerDetailTarget(payoutDetail({ sourceDomain: 'finance_import' }))).toBeNull();
    expect(payoutOwnerDetailTarget(payoutDetail({ action: {
      source_bindings: [
        { kind: 'identity', key: 'obligation_identity', value: 'staff-obligation:other' },
        { kind: 'identity', key: 'staff_id', value: '42' },
      ],
    } }))).toBeNull();
    expect(payoutOwnerDetailTarget(payoutDetail({ action: { action_contract_version: 2 } }))).toBeNull();
  });

  it('fails closed for similar but unauthorized form schemas or incomplete bindings', () => {
    expect(financeOwnerRecoveryTarget(context(action({
      form_schema_key: 'government_subsidy.overpayment.disposition.v2',
    })))).toBeNull();
    expect(financeOwnerRecoveryTarget(context(action({
      source_binding_keys: ['different_identity'],
      source_bindings: [{ kind: 'identity', key: 'different_identity', value: 'display-derived:17' }],
    })))).toBeNull();
    expect(financeOwnerRecoveryTarget(context(action({ action_contract_version: 2 })))).toBeNull();
    expect(financeOwnerRecoveryTarget(context(action({ requires_preview: false })))).toBeNull();
    expect(financeOwnerRecoveryTarget({ available_actions: [action({})] } as never)).toBeNull();
  });

  it('fails closed when binding kind or value semantics do not match the exact contract', () => {
    expect(financeOwnerRecoveryTarget(context(action({
      source_bindings: [
        { kind: 'version', key: 'overpayment_identity', value: 3 },
        { kind: 'identity', key: 'overpayment_version', value: '3' },
      ],
    })))).toBeNull();
    expect(financeOwnerRecoveryTarget(context(action({
      source_bindings: [
        { kind: 'identity', key: 'overpayment_identity', value: 'gov-overpayment:17' },
        { kind: 'version', key: 'overpayment_version', value: 0 },
      ],
    })))).toBeNull();
  });
});
