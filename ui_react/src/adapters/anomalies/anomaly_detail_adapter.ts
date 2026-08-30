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
  currentDetails: EvidenceRowViewModel[];
  actions: RecoveryActionViewModel[];
  currentIssueKey: string | null;
  blocking: boolean;
  recoveryAvailable: boolean;
}

type SafeEvidenceKind = AnomalyEvidenceField['kind'];

/**
 * API anomaly-safe.v1 fields that may be shown in the everyday detail view.
 * Identity-shaped values are safe only when their exact typed allowlist entry
 * is present; raw/private fields are deliberately absent from this map.
 */
const DAILY_DETAIL_SAFE_FIELDS: Readonly<Record<string, readonly SafeEvidenceKind[]>> = {
  occurred_at: ['datetime'],
  source_version: ['integer'],
  amount_delta_ntd: ['money_ntd'],
  case_no: ['identity'],
  holiday_date: ['date'],
  staff_name: ['masked_text'],
  root_condition_active: ['boolean'],
  integrity_blocker_active: ['boolean'],
  overdue_obligations: ['detail_list', 'identity_list'],
  resolution_condition: ['code'],
  issue_codes: ['code_list'],
  notification_reason: ['code'],
  domain_blockers: ['code_list'],
  reason_codes: ['code_list'],
  affected_order_identities: ['identity_list'],
  affected_obligation_identities: ['identity_list'],
  finance_import_row_id: ['identity'],
  finance_import_batch_id: ['identity'],
  original_refund_ledger_entry_id: ['identity'],
  finance_import_row_identity: ['identity'],
  finance_import_batch_identity: ['identity'],
  original_refund_ledger_entry_identity: ['identity'],
};

export function visibleEvidenceItems<T extends { key: string; kind: string }>(items: readonly T[]): T[] {
  return items.filter((item) => DAILY_DETAIL_SAFE_FIELDS[item.key]?.includes(item.kind as SafeEvidenceKind) ?? false);
}

function renderValue(field: AnomalyEvidenceField): string {
  if (Array.isArray(field.value)) return field.value.join(', ');
  if (field.kind === 'boolean') return field.value ? '是' : '否';
  return String(field.value);
}

const EVIDENCE_LABELS: Record<string, string> = {
  occurred_at: '偵測時間',
  source_version: '資料版本',
  amount_delta_ntd: '金額差異',
  case_no: '案件',
  holiday_date: '日期',
  staff_name: '月嫂',
  finance_import_row_id: '銀行流水資料',
  finance_import_batch_id: '匯入批次',
  original_refund_ledger_entry_id: '原退款紀錄',
  finance_import_row_identity: '銀行流水資料',
  finance_import_batch_identity: '匯入批次',
  original_refund_ledger_entry_identity: '原退款紀錄',
  affected_order_identities: '受影響案件',
  affected_obligation_identities: '受影響收付款',
  domain_blockers: '阻擋原因',
  reason_codes: '判斷原因',
  issue_codes: '問題代碼',
  notification_reason: '通知原因',
  root_condition_active: '目前仍需處理',
  integrity_blocker_active: '目前阻擋作業',
  overdue_obligations: '具體逾期義務',
  resolution_condition: '異常解除條件',
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
  if (recovery && (
    detail.summary.definition_code !== recovery.definition_code
  )) {
    throw new Error('detail 與 recovery identity 不一致');
  }
  const boundDetailActions = detail.available_actions.filter((action) => action.source_bindings !== null);
  const availableActions = recovery && recovery.available_actions.length > 0
    ? recovery.available_actions
    : boundDetailActions;
  return {
    fingerprint: detail.summary.fingerprint,
    definitionCode: detail.summary.definition_code,
    evidence: adaptEvidence(detail.summary.display_snapshot.fields),
    detailTimeline: adaptTimeline(detail.timeline),
    currentDetails: recovery ? adaptEvidence(recovery.details.fields) : [],
    actions: availableActions.map((action) => ({ key: action.action_key, label: action.label, owner: action.owning_domain, bindings: (action.source_bindings ?? []).map(renderBinding), requiredInputs: action.required_operator_inputs, previewOperation: action.preview_operation, applyOperation: action.apply_operation, completionPredicate: action.completion_predicate, contractVersion: action.action_contract_version })),
    currentIssueKey: recovery?.issue_key ?? null,
    blocking: recovery?.blocking ?? false,
    recoveryAvailable: recovery !== null || boundDetailActions.length > 0,
  };
}
