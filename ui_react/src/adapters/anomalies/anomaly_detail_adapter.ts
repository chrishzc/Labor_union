/**
 * File: anomaly_detail_adapter.ts
 * Description: 將 typed detail／recovery 原樣投影為唯讀 Drawer view model。
 */
import type { AnomalyDetailView, AnomalyEvidenceField, AnomalyRecoveryContextView, AnomalySourceBinding } from '../../api/anomalies/anomaly_detail_schemas';

export interface EvidenceRowViewModel { key: string; kind: string; label: string; value: string }
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

export function visibleEvidenceItems<T extends { key: string; kind: string }>(items: readonly T[]): T[] {
  return items.filter((item) => (
    !/(identity|version|fingerprint|hash|correlation|(^|_)id$)/i.test(item.key)
    && !['code', 'code_list', 'identity', 'identity_list'].includes(item.kind)
  ));
}

function renderValue(field: AnomalyEvidenceField): string {
  if (Array.isArray(field.value)) return field.value.join(', ');
  if (field.kind === 'boolean') return field.value ? '是' : '否';
  return String(field.value);
}

const EVIDENCE_LABELS: Record<string, string> = {
  occurred_at: '偵測時間',
  amount_delta_ntd: '金額差異',
  case_no: '案件',
  holiday_date: '日期',
  staff_name: '月嫂',
  root_condition_active: '目前仍需處理',
  integrity_blocker_active: '目前阻擋作業',
};

function adaptEvidence(fields: AnomalyEvidenceField[]): EvidenceRowViewModel[] {
  return fields.map((field) => ({ key: field.key, kind: field.kind, label: EVIDENCE_LABELS[field.key] ?? '相關資料', value: renderValue(field) }));
}

function adaptTimeline(items: AnomalyDetailView['timeline']): TimelineRowViewModel[] {
  const actionLabels: Readonly<Record<string, string>> = {
    claim: '已進入人工確認',
    resolve: '已記錄處理進度',
    reopen: '根因仍存在，重新列入待辦',
    auto_resolve: '根因已自動排除',
  };
  return items.map((item) => ({ action: actionLabels[item.action] ?? '系統處理紀錄', actor: item.actor, reason: item.reason, correlationId: item.correlation_id, expectedVersion: item.expected_workflow_version, resultingVersion: item.resulting_workflow_version, createdAt: item.created_at }));
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
      { key: 'occurred_at', kind: 'datetime', label: '偵測時間', value: root.occurred_at },
      { key: 'source_version', kind: 'integer', label: '資料版本', value: String(root.source_version) },
      { key: 'finance_import_row_identity', kind: 'identity', label: '銀行流水資料', value: root.finance_import_row_identity },
      { key: 'finance_import_batch_identity', kind: 'identity', label: '匯入批次', value: root.finance_import_batch_identity },
      { key: 'original_refund_ledger_entry_identity', kind: 'identity', label: '原退款紀錄', value: root.original_refund_ledger_entry_identity ?? '—' },
      { key: 'amount_delta_ntd', kind: 'money_ntd', label: '金額差異', value: `NT$ ${root.amount_delta_ntd.toLocaleString('zh-TW')}` },
      { key: 'root_condition_active', kind: 'boolean', label: '目前仍需處理', value: root.root_condition_active ? '是' : '否' },
      { key: 'integrity_blocker_active', kind: 'boolean', label: '目前阻擋作業', value: root.integrity_blocker_active ? '是' : '否' },
      { key: 'affected_order_identities', kind: 'identity_list', label: '受影響案件', value: root.affected_order_identities.join(', ') || '—' },
      { key: 'affected_obligation_identities', kind: 'identity_list', label: '受影響收付款', value: root.affected_obligation_identities.join(', ') || '—' },
      { key: 'domain_blockers', kind: 'code_list', label: '阻擋原因', value: root.domain_blockers.join(', ') || '—' },
      { key: 'reason_codes', kind: 'code_list', label: '判斷原因', value: root.reason_codes.join(', ') || '—' },
    ] : [],
    occurrences: recovery?.occurrence_timeline.map((item) => ({ fingerprint: item.occurrence_fingerprint, occurredAt: item.occurred_at, evidence: adaptEvidence(item.bounded_snapshot.fields) })) ?? [],
    actions: recovery?.available_actions.map((action) => ({ key: action.action_key, label: action.label, owner: action.owning_domain, bindings: action.source_bindings.map(renderBinding), requiredInputs: action.required_operator_inputs, previewOperation: action.preview_operation, applyOperation: action.apply_operation, completionPredicate: action.completion_predicate, contractVersion: action.action_contract_version })) ?? [],
    projectionFreshness: recovery?.projection_freshness ?? 'unavailable',
    domainBlockerActive: recovery?.domain_blocker_active ?? false,
    recoveryAvailable: recovery !== null,
  };
}
