/**
 * File: line_runtime_target_adapter.ts
 * Description: 將 LINE runtime target 與 receipt DTO 映射為去敏顯示模型，不暴露 recipient identity。
 */

import {
  LineRuntimeAdminCandidateSchema,
  LineRuntimeTargetReceiptSchema,
  LineRuntimeTargetSchema,
} from '../../api/line_runtime_targets/line_runtime_target_schemas';

export interface LineRuntimeTargetModel {
  targetId: number;
  targetKind: 'group' | 'admin_user';
  targetKindLabel: string;
  displayLabel: string;
  state: 'active' | 'disabled';
  stateLabel: string;
  minimumStatus: 'warning' | 'critical';
  minimumStatusLabel: string;
  currentVersion: string;
  updatedAt: string;
}

export interface LineRuntimeAdminCandidateModel {
  candidateId: number;
  displayLabel: string;
  lineLinked: boolean;
}

export interface LineRuntimeTargetReceiptModel {
  receiptId: string;
  operation: string;
  operationLabel: string;
  targetId: number;
  previousState: string;
  resultingState: string;
  currentVersion: string;
  replayed: boolean;
  correlationId: string;
  committedAt: string;
}

export function adaptLineRuntimeTarget(source: unknown): LineRuntimeTargetModel {
  const value = LineRuntimeTargetSchema.parse(source);
  return {
    targetId: value.target_id,
    targetKind: value.target_kind,
    targetKindLabel: value.target_kind === 'group' ? '群組' : '管理員',
    displayLabel: value.display_label,
    state: value.state,
    stateLabel: value.state === 'active' ? '啟用' : '停用',
    minimumStatus: value.minimum_status,
    minimumStatusLabel: value.minimum_status === 'warning' ? '警告以上' : '嚴重以上',
    currentVersion: value.current_version,
    updatedAt: value.updated_at,
  };
}

export function adaptLineRuntimeAdminCandidate(source: unknown): LineRuntimeAdminCandidateModel {
  const value = LineRuntimeAdminCandidateSchema.parse(source);
  return { candidateId: value.candidate_id, displayLabel: value.display_label, lineLinked: value.line_linked };
}

export function adaptLineRuntimeTargetReceipt(source: unknown): LineRuntimeTargetReceiptModel {
  const value = LineRuntimeTargetReceiptSchema.parse(source);
  const labels = { group_reset: '重設群組', enable: '啟用', disable: '停用', admin_target_add: '新增管理員對象' } as const;
  return {
    receiptId: value.receipt_id,
    operation: value.operation,
    operationLabel: labels[value.operation],
    targetId: value.target_id,
    previousState: value.previous_state,
    resultingState: value.resulting_state,
    currentVersion: value.current_version,
    replayed: value.replayed,
    correlationId: value.correlation_id,
    committedAt: value.committed_at,
  };
}
