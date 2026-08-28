/**
 * File: client_settlement_target.ts
 * Description: 依 exact anomaly action contract 路由客戶應收／應付人工處理工作台。
 */
import type { AnomalyDetailView, DomainAction } from '../../api/anomalies/anomaly_detail_schemas';

export type ClientSettlementKind = 'receivable' | 'refund' | 'subsidy_return';
export interface ClientSettlementTarget {
  kind: ClientSettlementKind;
  caseNo: string;
  accountVersion: number;
}

interface Contract {
  actionKey: string;
  owner: 'client_finance';
  preview: string;
  apply: string;
  completion: string;
  inputs: string[];
  kind: ClientSettlementKind;
}

const CONTRACTS: Record<string, Contract> = {
  'client_finance.receivable_reconciliation.v1': {
    actionKey: 'reconcile_client_receivable', owner: 'client_finance',
    preview: 'PreviewClientReceiptReconciliation', apply: 'ApplyClientReceiptReconciliation',
    completion: 'client_receivable_overdue_obligations_cleared',
    inputs: ['bank_fact_identities', 'obligation_identities', 'payment_stage', 'reason'], kind: 'receivable',
  },
  'client_finance.client_payable_refund.v1': {
    actionKey: 'settle_client_payable', owner: 'client_finance',
    preview: 'PreviewClientRefund', apply: 'ApplyClientRefund',
    completion: 'client_payable_overdue_obligations_cleared',
    inputs: ['bank_fact_identities', 'obligation_identities', 'reason'], kind: 'refund',
  },
  'client_finance.subsidy_return.v1': {
    actionKey: 'settle_client_subsidy_return', owner: 'client_finance',
    preview: 'PreviewClientSubsidyReturn', apply: 'ApplyClientSubsidyReturn',
    completion: 'client_subsidy_return_overdue_obligations_cleared',
    inputs: ['bank_fact_identities', 'obligation_identities', 'reason'], kind: 'subsidy_return',
  },
};

function exact(actual: string[], expected: string[]): boolean {
  return actual.length === expected.length && actual.every((item, index) => item === expected[index]);
}

function binding(action: DomainAction, key: string): string | number | null {
  return action.source_bindings?.find((item) => item.key === key)?.value ?? null;
}

function target(action: DomainAction): ClientSettlementTarget | null {
  const contract = CONTRACTS[action.form_schema_key];
  if (!contract || action.action_contract_version !== 1 || !action.requires_preview) return null;
  if (action.action_key !== contract.actionKey || action.owning_domain !== contract.owner) return null;
  if (action.preview_operation !== contract.preview || action.apply_operation !== contract.apply) return null;
  if (action.completion_predicate !== contract.completion || action.required_capability !== null) return null;
  if (!exact(action.source_binding_keys, ['account_version', 'case_no'])) return null;
  if (!exact(action.required_operator_inputs, contract.inputs) || !action.source_bindings) return null;
  const caseNo = binding(action, 'case_no');
  const accountVersion = binding(action, 'account_version');
  if (typeof caseNo !== 'string' || !caseNo || typeof accountVersion !== 'number' || !Number.isSafeInteger(accountVersion) || accountVersion < 0) return null;
  return { kind: contract.kind, caseNo, accountVersion };
}

export function clientSettlementTarget(detail: AnomalyDetailView | null): ClientSettlementTarget | null {
  if (!detail) return null;
  for (const action of detail.available_actions) {
    const result = target(action);
    if (result) return result;
  }
  return null;
}
