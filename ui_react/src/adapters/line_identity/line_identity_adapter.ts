/**
 * File: line_identity_adapter.ts
 * Description: 將 LINE 身分查詢、審核、更正、解除與維護 DTO 轉為遮罩展示模型，排除 provider 與原始錯誤。
 */
import type {
  LineBindingSubjectType,
  LineIdentityBindingPageView,
  LineIdentityBindingStatus,
  LineIdentityBindingView,
  LineIdentityReplacementPreviewView,
  LineIdentityReviewDecision,
  LineIdentityReviewApplyView,
  LineIdentityReviewPageView,
  LineIdentityReviewPreviewView,
  LineIdentityReviewStatus,
  LineIdentityReviewSummaryView,
  LineIdentityReviewType,
  LineIdentityReviewView,
  LineIdentityRevocationPreviewView,
  LineIdentityRevocationRequestView,
  LineIdentityRevocationStatus,
} from '../../api/line_identity/line_identity_schemas';

export interface LineIdentityBindingRowViewModel {
  lineUserId: string;
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

export interface LineIdentityReviewRowViewModel {
  requestId: number;
  reviewType: LineIdentityReviewType;
  reviewTypeLabel: string;
  status: LineIdentityReviewStatus;
  statusLabel: string;
  version: number;
  subjectTypeLabel: string;
  subjectReference: string | null;
  lineUserId: string;
  displayName: string;
  decisionReason: string | null;
  reviewedAt: string | null;
  createdAt: string | null;
}

export interface LineIdentityReviewPageViewModel {
  items: LineIdentityReviewRowViewModel[];
  page: number;
  pageSize: number;
  total: number;
}

export interface LineIdentityReviewSummaryViewModel {
  pendingTotal: number;
  staffPending: number;
  rebindPending: number;
  processedToday: number;
}

export interface LineIdentityReviewPreviewViewModel {
  requestId: number;
  decision: LineIdentityReviewDecision;
  decisionLabel: string;
  beforeStatusLabel: string;
  afterStatusLabel: string;
  expectedVersion: number;
  resultingVersion: number;
  subjectTypeLabel: string;
  subjectReference: string | null;
  lineUserId: string;
  previewFingerprint: string;
}

export interface LineIdentityReviewReceiptViewModel {
  requestId: number;
  status: LineIdentityReviewStatus;
  statusLabel: string;
  version: number;
  decisionReason: string | null;
  reviewedAt: string | null;
  outcomeLabel: string;
  receiptIdentity: string;
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

function reviewTypeLabel(reviewType: LineIdentityReviewType): string {
  switch (reviewType) {
    case 'client_rebind':
      return '客戶重新綁定';
    case 'staff_verification':
      return '月嫂身分驗證';
    case 'admin_binding':
      return '管理員綁定';
  }
}

function reviewStatusLabel(status: LineIdentityReviewStatus): string {
  switch (status) {
    case 'pending':
      return '待人工審核';
    case 'approved':
      return '已核准';
    case 'rejected':
      return '已拒絕';
    case 'cancelled':
      return '已取消';
    case 'expired':
      return '已失效';
  }
}

function reviewDecisionLabel(decision: LineIdentityReviewDecision): string {
  return decision === 'approve' ? '核准' : '拒絕';
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
    lineUserId: maskLineUserId(binding.line_user_id),
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

export function adaptLineIdentityReview(
  review: LineIdentityReviewView
): LineIdentityReviewRowViewModel {
  return {
    requestId: review.request_id,
    reviewType: review.review_type,
    reviewTypeLabel: reviewTypeLabel(review.review_type),
    status: review.status,
    statusLabel: reviewStatusLabel(review.status),
    version: review.version,
    subjectTypeLabel: review.subject_type === null ? '尚未連結對象' : subjectTypeLabel(review.subject_type),
    subjectReference: review.subject_reference,
    lineUserId: maskLineUserId(review.line_user_id),
    displayName: review.display_name,
    decisionReason: review.decision_reason,
    reviewedAt: review.reviewed_at,
    createdAt: review.created_at,
  };
}

export function adaptLineIdentityReviewPage(
  page: LineIdentityReviewPageView
): LineIdentityReviewPageViewModel {
  return {
    items: page.items.map(adaptLineIdentityReview),
    page: page.page,
    pageSize: page.page_size,
    total: page.total,
  };
}

export function adaptLineIdentityReviewSummary(
  summary: LineIdentityReviewSummaryView
): LineIdentityReviewSummaryViewModel {
  return {
    pendingTotal: summary.pending_total,
    staffPending: summary.staff_pending,
    rebindPending: summary.rebind_pending,
    processedToday: summary.processed_today,
  };
}

export function adaptLineIdentityReviewPreview(
  preview: LineIdentityReviewPreviewView
): LineIdentityReviewPreviewViewModel {
  return {
    requestId: preview.request_id,
    decision: preview.decision,
    decisionLabel: reviewDecisionLabel(preview.decision),
    beforeStatusLabel: reviewStatusLabel(preview.before_status),
    afterStatusLabel: reviewStatusLabel(preview.after_status),
    expectedVersion: preview.expected_version,
    resultingVersion: preview.resulting_version,
    subjectTypeLabel: preview.subject_type === null ? '尚未連結對象' : subjectTypeLabel(preview.subject_type),
    subjectReference: preview.subject_reference,
    lineUserId: maskLineUserId(preview.line_user_id),
    previewFingerprint: preview.preview_fingerprint,
  };
}

export function adaptLineIdentityReviewReceipt(
  review: LineIdentityReviewApplyView
): LineIdentityReviewReceiptViewModel {
  return {
    requestId: review.request_id,
    status: review.status,
    statusLabel: reviewStatusLabel(review.status),
    version: review.version,
    decisionReason: review.decision_reason,
    reviewedAt: review.reviewed_at,
    outcomeLabel: review.outcome === 'existing' ? '已存在（幂等回放）' : '已建立',
    receiptIdentity: review.receipt_identity,
    notice: '審核決定已由後端受理；此回應不代表任何 LINE provider 訊息已送達。',
  };
}
