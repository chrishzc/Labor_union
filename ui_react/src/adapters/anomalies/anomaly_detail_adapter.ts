/**
 * File: anomaly_detail_adapter.ts
 * Description: 將 typed detail／recovery 原樣投影為唯讀 Drawer view model。
 */
import type { AnomalyDetailView, AnomalyEvidenceField, AnomalyRecoveryContextView, AnomalySourceBinding } from '../../api/anomalies/anomaly_detail_schemas';

export interface EvidenceRowViewModel { key: string; kind: string; value: string }
export interface TimelineRowViewModel { action: string; actor: string; reason: string; correlationId: string; expectedVersion: number; resultingVersion: number; createdAt: string }
export interface RecoveryActionViewModel { key: string; label: string; owner: string; bindings: string[]; requiredInputs: string[]; previewOperation: string; applyOperation: string | null; completionPredicate: string; contractVersion: number }
export interface AnomalyDetailBundleViewModel {
  fingerprint: string;
  definitionCode: string;
  evidence: EvidenceRowViewModel[];
  detailTimeline: TimelineRowViewModel[];
  recoveryTimeline: TimelineRowViewModel[];
  rootFacts: EvidenceRowViewModel[];
  occurrences: Array<{ fingerprint: string; occurredAt: string; evidence: EvidenceRowViewModel[] }>;
  actions: RecoveryActionViewModel[];
  projectionFreshness: string;
  domainBlockerActive: boolean;
  recoveryAvailable: boolean;
}

function renderValue(field: AnomalyEvidenceField): string {
  if (Array.isArray(field.value)) return field.value.join(', ');
  return String(field.value);
}

function adaptEvidence(fields: AnomalyEvidenceField[]): EvidenceRowViewModel[] {
  return fields.map((field) => ({ key: field.key, kind: field.kind, value: renderValue(field) }));
}

function adaptTimeline(items: AnomalyDetailView['timeline']): TimelineRowViewModel[] {
  return items.map((item) => ({ action: item.action, actor: item.actor, reason: item.reason, correlationId: item.correlation_id, expectedVersion: item.expected_workflow_version, resultingVersion: item.resulting_workflow_version, createdAt: item.created_at }));
}

function renderBinding(item: AnomalySourceBinding): string {
  return `${item.key}=${String(item.value)}`;
}

export function adaptAnomalyDetailBundle(detail: AnomalyDetailView, recovery: AnomalyRecoveryContextView | null): AnomalyDetailBundleViewModel {
  if (recovery && (detail.summary.fingerprint !== recovery.fingerprint || detail.summary.definition_code !== recovery.definition_code)) {
    throw new Error('detail 與 recovery identity 不一致');
  }
  const root = recovery?.root_fact_snapshot;
  return {
    fingerprint: detail.summary.fingerprint,
    definitionCode: detail.summary.definition_code,
    evidence: adaptEvidence(detail.summary.display_snapshot.fields),
    detailTimeline: adaptTimeline(detail.timeline),
    recoveryTimeline: recovery ? adaptTimeline(recovery.workflow_timeline) : [],
    rootFacts: root ? [
      { key: 'occurred_at', kind: 'datetime', value: root.occurred_at },
      { key: 'source_version', kind: 'integer', value: String(root.source_version) },
      { key: 'finance_import_row_identity', kind: 'identity', value: root.finance_import_row_identity },
      { key: 'finance_import_batch_identity', kind: 'identity', value: root.finance_import_batch_identity },
      { key: 'original_refund_ledger_entry_identity', kind: 'identity', value: root.original_refund_ledger_entry_identity ?? '—' },
      { key: 'amount_delta_ntd', kind: 'money_ntd', value: String(root.amount_delta_ntd) },
      { key: 'root_condition_active', kind: 'boolean', value: String(root.root_condition_active) },
      { key: 'integrity_blocker_active', kind: 'boolean', value: String(root.integrity_blocker_active) },
      { key: 'affected_order_identities', kind: 'identity_list', value: root.affected_order_identities.join(', ') || '—' },
      { key: 'affected_obligation_identities', kind: 'identity_list', value: root.affected_obligation_identities.join(', ') || '—' },
      { key: 'domain_blockers', kind: 'code_list', value: root.domain_blockers.join(', ') || '—' },
      { key: 'reason_codes', kind: 'code_list', value: root.reason_codes.join(', ') || '—' },
    ] : [],
    occurrences: recovery?.occurrence_timeline.map((item) => ({ fingerprint: item.occurrence_fingerprint, occurredAt: item.occurred_at, evidence: adaptEvidence(item.bounded_snapshot.fields) })) ?? [],
    actions: recovery?.available_actions.map((action) => ({ key: action.action_key, label: action.label, owner: action.owning_domain, bindings: action.source_bindings.map(renderBinding), requiredInputs: action.required_operator_inputs, previewOperation: action.preview_operation, applyOperation: action.apply_operation, completionPredicate: action.completion_predicate, contractVersion: action.action_contract_version })) ?? [],
    projectionFreshness: recovery?.projection_freshness ?? 'unavailable',
    domainBlockerActive: recovery?.domain_blocker_active ?? false,
    recoveryAvailable: recovery !== null,
  };
}
