/**
 * File: finance_owner_recovery_target.ts
 * Description: 只依 typed owner form schema 與 source bindings 路由財務異常人工修正工作區。
 */
import type { AnomalyDetailView, AnomalyRecoveryContextView, DomainAction, RecoveryAction } from '../../api/anomalies/anomaly_detail_schemas';

export type FinanceOwnerRecoveryTarget =
  | { kind: 'government'; overpaymentIdentity: string }
  | { kind: 'client'; caseNo: string; recoveryIdentity: string; financeImportRowId?: number }
  | { kind: 'staff'; staffId: number; recoveryIdentity: string; financeImportRowId?: number }
  | { kind: 'staff_payout'; staffId: number; obligationIdentity: string };

interface ActionContract {
  actionKey: string;
  owner: string;
  preview: string;
  apply: string;
  capability: string;
  completion: string;
  bindingKeys: string[];
  bindingKinds: Record<string, 'identity' | 'version'>;
  inputKeys: string[];
}

const ACTION_CONTRACTS: Record<string, ActionContract> = {
  'staff_payables.payout_reconciliation.v1': {
    actionKey: 'reconcile_overdue_staff_payable', owner: 'staff_payables',
    preview: 'PreviewStaffPayout', apply: 'ApplyStaffPayout',
    capability: 'staff_payables.payout.apply', completion: 'staff_payable_obligation_settled',
    bindingKeys: ['obligation_identity', 'staff_id'],
    bindingKinds: { obligation_identity: 'identity', staff_id: 'identity' },
    inputKeys: ['finance_import_row_ids', 'reason'],
  },
  'government_subsidy.overpayment.disposition.v1': {
    actionKey: 'dispose_government_subsidy_overpayment', owner: 'government_subsidy',
    preview: 'PreviewGovernmentSubsidyOverpaymentDisposition', apply: 'ApplyGovernmentSubsidyOverpaymentDisposition',
    capability: 'government_subsidy.overpayment.disposition', completion: 'government_subsidy_overpayment_disposed',
    bindingKeys: ['overpayment_identity', 'overpayment_version'],
    bindingKinds: { overpayment_identity: 'identity', overpayment_version: 'version' },
    inputKeys: ['disposition', 'evidence_reference', 'offset_amounts', 'offset_targets', 'reason', 'return_due_date'],
  },
  'client_finance.over_refund_recovery.collection.v1': {
    actionKey: 'collect_client_over_refund_recovery', owner: 'client_finance',
    preview: 'PreviewCollectMatchedClientOverRefundRecovery', apply: 'ApplyCollectMatchedClientOverRefundRecovery',
    capability: 'client_finance.recovery.collect', completion: 'client_over_refund_recovery_remaining_updated',
    bindingKeys: ['account_version', 'case_no', 'finance_import_row_identity', 'matching_identity', 'matching_version', 'recovery_identity', 'recovery_version'],
    bindingKinds: { account_version: 'version', case_no: 'identity', finance_import_row_identity: 'identity', matching_identity: 'identity', matching_version: 'version', recovery_identity: 'identity', recovery_version: 'version' },
    inputKeys: ['evidence_reference', 'reason'],
  },
  'client_finance.over_refund_recovery.matching.v1': {
    actionKey: 'match_client_over_refund_recovery', owner: 'client_finance',
    preview: 'PreviewClientOverRefundRecoveryMatching', apply: 'ApplyClientOverRefundRecoveryMatching',
    capability: 'client_finance.recovery.collect', completion: 'client_over_refund_recovery_matching_established',
    bindingKeys: ['account_version', 'case_no', 'recovery_identity', 'recovery_version'],
    bindingKinds: { account_version: 'version', case_no: 'identity', recovery_identity: 'identity', recovery_version: 'version' },
    inputKeys: ['evidence_reference', 'finance_import_row_identity', 'reason'],
  },
  'client_finance.over_refund_recovery.adjustment.v1': {
    actionKey: 'adjust_client_over_refund_recovery', owner: 'client_finance',
    preview: 'PreviewClientOverRefundRecoveryAdjustment', apply: 'ApplyClientOverRefundRecoveryAdjustment',
    capability: 'client_finance.recovery.adjust', completion: 'client_over_refund_recovery_remaining_updated',
    bindingKeys: ['account_version', 'case_no', 'recovery_identity', 'recovery_version'],
    bindingKinds: { account_version: 'version', case_no: 'identity', recovery_identity: 'identity', recovery_version: 'version' },
    inputKeys: ['adjustment_amount', 'evidence_reference', 'reason'],
  },
  'staff_payables.overpayment_recovery.collection.v1': {
    actionKey: 'collect_staff_overpayment_recovery', owner: 'staff_payables',
    preview: 'PreviewCollectMatchedStaffOverpaymentRecovery', apply: 'ApplyCollectMatchedStaffOverpaymentRecovery',
    capability: 'staff_payables.recovery.collect', completion: 'staff_overpayment_recovery_remaining_updated',
    bindingKeys: ['finance_import_row_identity', 'matching_identity', 'matching_version', 'recovery_identity', 'recovery_version', 'staff_id', 'staff_payables_version'],
    bindingKinds: { finance_import_row_identity: 'identity', matching_identity: 'identity', matching_version: 'version', recovery_identity: 'identity', recovery_version: 'version', staff_id: 'identity', staff_payables_version: 'version' },
    inputKeys: ['evidence_reference', 'reason'],
  },
  'staff_payables.overpayment_recovery.matching.v1': {
    actionKey: 'match_staff_overpayment_recovery', owner: 'staff_payables',
    preview: 'PreviewStaffOverpaymentRecoveryMatching', apply: 'ApplyStaffOverpaymentRecoveryMatching',
    capability: 'staff_payables.recovery.collect', completion: 'staff_overpayment_recovery_matching_established',
    bindingKeys: ['recovery_identity', 'recovery_version', 'staff_id', 'staff_payables_version'],
    bindingKinds: { recovery_identity: 'identity', recovery_version: 'version', staff_id: 'identity', staff_payables_version: 'version' },
    inputKeys: ['evidence_reference', 'finance_import_row_identity', 'reason'],
  },
  'staff_payables.overpayment_recovery.adjustment.v1': {
    actionKey: 'adjust_staff_overpayment_recovery', owner: 'staff_payables',
    preview: 'PreviewStaffOverpaymentRecoveryAdjustment', apply: 'ApplyStaffOverpaymentRecoveryAdjustment',
    capability: 'staff_payables.recovery.adjust', completion: 'staff_overpayment_recovery_remaining_updated',
    bindingKeys: ['recovery_identity', 'recovery_version', 'staff_id', 'staff_payables_version'],
    bindingKinds: { recovery_identity: 'identity', recovery_version: 'version', staff_id: 'identity', staff_payables_version: 'version' },
    inputKeys: ['adjustment_amount', 'evidence_reference', 'reason'],
  },
};

const DEFINITION_BY_SCHEMA: Record<string, string> = {
  'government_subsidy.overpayment.disposition.v1': 'GOVSUB-006',
  'client_finance.over_refund_recovery.collection.v1': 'client_over_refund_recovery_open',
  'client_finance.over_refund_recovery.matching.v1': 'client_over_refund_recovery_open',
  'client_finance.over_refund_recovery.adjustment.v1': 'client_over_refund_recovery_open',
  'staff_payables.overpayment_recovery.collection.v1': 'staff_overpayment_recovery_open',
  'staff_payables.overpayment_recovery.matching.v1': 'staff_overpayment_recovery_open',
  'staff_payables.overpayment_recovery.adjustment.v1': 'staff_overpayment_recovery_open',
};

type ActionSource = AnomalyRecoveryContextView;
type ActionView = RecoveryAction | DomainAction;

function binding(action: ActionView, key: string): string | number | null {
  return Array.isArray(action.source_bindings)
    ? action.source_bindings.find((item) => item.key === key)?.value ?? null
    : null;
}

function positiveIntegerBinding(value: string | number | null): number | undefined {
  if (typeof value === 'string' && !/^[1-9][0-9]*$/.test(value)) return undefined;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : undefined;
}

function exactValues(actual: string[], expected: string[]): boolean {
  return Array.isArray(actual)
    && actual.length === expected.length
    && actual.every((value, index) => value === expected[index]);
}

function exactBindings(action: ActionView, contract: ActionContract): boolean {
  const bindings = action.source_bindings;
  if (!Array.isArray(bindings) || bindings.length !== contract.bindingKeys.length) return false;
  return contract.bindingKeys.every((key, index) => {
    const source = bindings[index];
    if (source.key !== key || source.kind !== contract.bindingKinds[key]) return false;
    if (source.kind === 'identity') return typeof source.value === 'string' && source.value.trim().length > 0;
    return typeof source.value === 'number' && Number.isSafeInteger(source.value) && source.value > 0;
  });
}

function hasCompleteRecoveryContext(context: ActionSource): boolean {
  // Recovery actions are only trustworthy when they came from the complete
  // recovery GET. A detail-only DomainAction has no root facts or freshness
  // guarantee and must never be used to open an owner workbench.
  if (typeof context !== 'object' || context === null) return false;
  if (typeof context.predicate_active !== 'boolean'
    || typeof context.projection_freshness !== 'string'
    || typeof context.fingerprint !== 'string'
    || typeof context.source_identity !== 'string'
    || !Number.isSafeInteger(context.source_version)
    || typeof context.root_fact_snapshot !== 'object'
    || context.root_fact_snapshot === null
    || typeof context.root_fact_snapshot.root_condition_active !== 'boolean'
    || !Array.isArray(context.available_actions)) return false;
  return context.predicate_active
    && context.projection_freshness === 'fresh'
    && /^[0-9a-f]{64}$/.test(context.fingerprint)
    && context.source_identity.trim().length > 0
    && context.root_fact_snapshot.root_condition_active
    && Array.isArray(context.occurrence_timeline)
    && Array.isArray(context.workflow_timeline);
}

function exactContract(action: ActionView): ActionContract | null {
  if (typeof action !== 'object' || action === null) return null;
  const contract = ACTION_CONTRACTS[action.form_schema_key];
  if (!contract || action.action_contract_version !== 1 || !action.requires_preview) return null;
  if (action.action_key !== contract.actionKey || action.owning_domain !== contract.owner) return null;
  if (action.preview_operation !== contract.preview || action.apply_operation !== contract.apply) return null;
  if (action.required_capability !== contract.capability || action.completion_predicate !== contract.completion) return null;
  if (!exactValues(action.source_binding_keys, contract.bindingKeys)) return null;
  if (!exactBindings(action, contract)) return null;
  if (!exactValues(action.required_operator_inputs, contract.inputKeys)) return null;
  return contract;
}

function contextMatchesContract(context: ActionSource, action: ActionView, contract: ActionContract): boolean {
  return context.source_domain === contract.owner
    && context.definition_code === DEFINITION_BY_SCHEMA[action.form_schema_key];
}

export function financeOwnerRecoveryTarget(context: ActionSource | null): FinanceOwnerRecoveryTarget | null {
  if (!context || !hasCompleteRecoveryContext(context)) return null;
  for (const action of context.available_actions) {
    const contract = exactContract(action);
    if (!contract) continue;
    if (!contextMatchesContract(context, action, contract)) continue;
    if (contract.owner === 'government_subsidy') {
      const overpaymentIdentity = binding(action, 'overpayment_identity');
      if (typeof overpaymentIdentity === 'string' && overpaymentIdentity) {
        return { kind: 'government', overpaymentIdentity };
      }
    }
    if (contract.owner === 'client_finance') {
      const caseNo = binding(action, 'case_no');
      const recoveryIdentity = binding(action, 'recovery_identity');
      if (typeof caseNo === 'string' && caseNo && typeof recoveryIdentity === 'string' && recoveryIdentity) {
        return {
          kind: 'client',
          caseNo,
          recoveryIdentity,
          financeImportRowId: positiveIntegerBinding(binding(action, 'finance_import_row_identity')),
        };
      }
    }
    if (contract.owner === 'staff_payables') {
      const staffIdValue = binding(action, 'staff_id');
      const staffId = positiveIntegerBinding(staffIdValue);
      if (action.form_schema_key === 'staff_payables.payout_reconciliation.v1') {
        const obligationIdentity = binding(action, 'obligation_identity');
        if (staffId !== undefined && typeof obligationIdentity === 'string' && obligationIdentity) {
          return { kind: 'staff_payout', staffId, obligationIdentity };
        }
        continue;
      }
      const recoveryIdentity = binding(action, 'recovery_identity');
      if (staffId !== undefined && typeof recoveryIdentity === 'string' && recoveryIdentity) {
        return {
          kind: 'staff',
          staffId,
          recoveryIdentity,
          financeImportRowId: positiveIntegerBinding(binding(action, 'finance_import_row_identity')),
        };
      }
    }
  }
  return null;
}

export function payoutOwnerDetailTarget(
  detail: AnomalyDetailView | null,
): Extract<FinanceOwnerRecoveryTarget, { kind: 'staff_payout' }> | null {
  if (!detail) return null;
  const summary = detail.summary;
  if (summary.definition_code !== 'PAYOUT-001'
    || summary.source_domain !== 'staff_payables'
    || !summary.predicate_active) return null;

  for (const action of detail.available_actions) {
    const contract = exactContract(action);
    if (!contract || action.form_schema_key !== 'staff_payables.payout_reconciliation.v1') continue;
    const staffId = positiveIntegerBinding(binding(action, 'staff_id'));
    const obligationIdentity = binding(action, 'obligation_identity');
    if (staffId === undefined
      || typeof obligationIdentity !== 'string'
      || obligationIdentity !== summary.source_identity) continue;
    return { kind: 'staff_payout', staffId, obligationIdentity };
  }
  return null;
}
