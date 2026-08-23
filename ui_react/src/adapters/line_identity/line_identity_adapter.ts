/**
 * File: line_identity_adapter.ts
 * Description: 將 LINE 身分查詢、更正、解除與維護 DTO 轉為遮罩展示模型，排除 provider 與原始錯誤。
 */
import type {
  LineBindingSubjectType,
  LineIdentityBindingPageView,
  LineIdentityBindingStatus,
  LineIdentityBindingView,
  LineIdentityReplacementPreviewView,
  LineIdentityRevocationPreviewView,
  LineIdentityRevocationRequestView,
  LineIdentityRevocationStatus,
} from '../../api/line_identity/line_identity_schemas';

export interface LineIdentityBindingRowViewModel {
  maskedLineUserId: string;
  status: LineIdentityBindingStatus;
  statusLabel: string;
  version: number;
  subjectType: LineBindingSubjectType;
  subjectTypeLabel: string;
  subjectName: string;
  updatedAt: string | null;
  revocationRequestId: number | null;
  revocationStatus: LineIdentityRevocationStatus | null;
  revocationStatusLabel: string;
  revokedAt: string | null;
}

export interface LineIdentityBindingPageViewModel {
  items: LineIdentityBindingRowViewModel[];
  total: number;
  page: number;
  pageSize: number;
}

export interface LineIdentityRevocationPreviewViewModel {
  binding: LineIdentityBindingRowViewModel;
  defaultMenuPublished: boolean;
  blockers: string[];
  hasBlockers: boolean;
}

export interface LineIdentityRevocationAcceptedViewModel {
  requestId: number;
  status: LineIdentityRevocationStatus;
  statusLabel: string;
  pendingBindingVersion: number;
  attemptCount: number;
  notice: string;
}

export interface LineIdentityReplacementPreviewViewModel {
  binding: LineIdentityBindingRowViewModel;
  targetSubjectName: string;
  blockers: string[];
  hasBlockers: boolean;
}

export interface LineIdentityMaintenanceResultViewModel {
  requestId: number;
  status: LineIdentityRevocationStatus;
  statusLabel: string;
  attemptCount: number;
  notice: string;
}

export function maskLineUserId(lineUserId: string): string {
  const value = lineUserId.trim();
  if (value.length <= 2) {
    return '••••';
  }
  if (value.length <= 8) {
    return `${value.slice(0, 1)}••••${value.slice(-1)}`;
  }
  return `${value.slice(0, 4)}••••${value.slice(-4)}`;
}

function subjectTypeLabel(subjectType: LineBindingSubjectType): string {
  switch (subjectType) {
    case 'customer':
      return '客戶';
    case 'staff':
      return '月嫂';
    case 'admin':
      return '內部人員';
  }
}

function bindingStatusLabel(status: LineIdentityBindingStatus): string {
  switch (status) {
    case 'unbound':
      return '未綁定';
    case 'pending_review':
      return '待人工審核';
    case 'bound':
      return '已綁定';
    case 'revocation_pending':
      return '解除處理中';
    case 'revoked':
      return '已解除';
  }
}

function revocationStatusLabel(status: LineIdentityRevocationStatus | null): string {
  switch (status) {
    case 'pending_menu_reset':
      return '等待 Rich Menu 回復';
    case 'menu_reset_failed':
      return 'Rich Menu 回復失敗';
    case 'completed':
      return '解除完成';
    case 'manual_completed':
      return '人工解除完成';
    case null:
      return '尚未申請解除';
  }
}

function blockerLabel(blocker: string): string {
  switch (blocker) {
    case 'line_identity_binding_not_bound':
      return '目前綁定狀態不允許解除';
    case 'line_identity_default_menu_not_published':
      return '預設 Rich Menu 尚未發布';
    default:
      return '伺服器回報未識別的解除阻擋原因';
  }
}

function replacementBlockerLabel(blocker: string): string {
  switch (blocker) {
    case 'line_identity_binding_not_bound':
      return '目前綁定狀態不允許更正對象';
    case 'line_identity_subject_unchanged':
      return '新對象與目前綁定對象相同';
    case 'line_identity_replacement_subject_not_found':
      return '找不到同角色的更正對象';
    case 'line_identity_replacement_subject_already_bound':
      return '更正對象已綁定其他 LINE 身分';
    default:
      return '伺服器回報未識別的更正阻擋原因';
  }
}

export function adaptLineIdentityBinding(
  binding: LineIdentityBindingView
): LineIdentityBindingRowViewModel {
  return {
    maskedLineUserId: maskLineUserId(binding.line_user_id),
    status: binding.status,
    statusLabel: bindingStatusLabel(binding.status),
    version: binding.version,
    subjectType: binding.subject_type,
    subjectTypeLabel: subjectTypeLabel(binding.subject_type),
    subjectName: binding.subject_name,
    updatedAt: binding.updated_at ?? null,
    revocationRequestId: binding.revocation_request_id ?? null,
    revocationStatus: binding.revocation_status ?? null,
    revocationStatusLabel: revocationStatusLabel(binding.revocation_status ?? null),
    revokedAt: binding.revoked_at ?? null,
  };
}

export function adaptLineIdentityBindingPage(
  page: LineIdentityBindingPageView
): LineIdentityBindingPageViewModel {
  return {
    items: page.items.map(adaptLineIdentityBinding),
    total: page.total,
    page: page.page,
    pageSize: page.page_size,
  };
}

export function adaptLineIdentityRevocationPreview(
  preview: LineIdentityRevocationPreviewView
): LineIdentityRevocationPreviewViewModel {
  return {
    binding: adaptLineIdentityBinding(preview.binding),
    defaultMenuPublished: preview.default_menu_publication_id != null,
    blockers: preview.blockers.map(blockerLabel),
    hasBlockers: preview.blockers.length > 0,
  };
}

export function adaptLineIdentityReplacementPreview(
  preview: LineIdentityReplacementPreviewView
): LineIdentityReplacementPreviewViewModel {
  return {
    binding: adaptLineIdentityBinding(preview.binding),
    targetSubjectName: preview.target_subject_name,
    blockers: preview.blockers.map(replacementBlockerLabel),
    hasBlockers: preview.blockers.length > 0,
  };
}

export function adaptLineIdentityReplacementResult(
  binding: LineIdentityBindingView
): LineIdentityBindingRowViewModel {
  return adaptLineIdentityBinding(binding);
}

export function adaptLineIdentityRevocationAccepted(
  request: LineIdentityRevocationRequestView
): LineIdentityRevocationAcceptedViewModel {
  return {
    requestId: request.request_id,
    status: request.status,
    statusLabel: revocationStatusLabel(request.status),
    pendingBindingVersion: request.pending_binding_version,
    attemptCount: request.attempt_count,
    // Apply 只代表 durable 解除申請已受理；完成必須以後續綁定／請求查詢為準。
    notice: '解除申請已受理；仍須重新查詢綁定狀態確認後續完成結果。',
  };
}

export function adaptLineIdentityMaintenanceResult(
  request: LineIdentityRevocationRequestView,
  operation: 'retry' | 'manual_complete'
): LineIdentityMaintenanceResultViewModel {
  return {
    requestId: request.request_id,
    status: request.status,
    statusLabel: revocationStatusLabel(request.status),
    attemptCount: request.attempt_count,
    notice:
      operation === 'retry'
        ? '已重新排入 Rich Menu 回復流程；請稍後重新查詢確認完成結果。'
        : '人工完成已受理；請重新查詢綁定狀態確認 owner projection 已清除。',
  };
}
