/**
 * File: audit_query_adapter.ts
 * Description: 將遮罩稽核 list/detail 契約投影為 React 安全顯示資料。
 */
import type {
  AdminAuditMaskedDetail,
  AdminAuditMaskedItem,
  AdminAuditMaskedPage,
} from '../../api/access/audit_query_schemas';

export interface AuditRow {
  auditId: number;
  occurredAt: string;
  actorLabelMasked: string | null;
  actionFamily: string;
  targetLabelMasked: string | null;
  ipAddressMasked: string | null;
  outcome: string;
}

export interface AuditPageView {
  items: AuditRow[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

export interface AuditDetailView extends AuditRow {
  details: Array<{ key: string; valueMasked: string }>;
}

const ACTION_LABELS: Record<AdminAuditMaskedItem['action_family'], string> = {
  authentication: '登入驗證', account_security: '帳號安全', session: '登入階段',
  mfa: '動態碼驗證', system: '系統管理', other: '其他安全操作',
};
const OUTCOME_LABELS: Record<AdminAuditMaskedItem['outcome'], string> = {
  success: '成功', denied: '已拒絕', failed: '失敗', unknown: '結果待確認',
};
const DETAIL_LABELS: Record<AdminAuditMaskedDetail['details'][number]['key'], string> = {
  reason: '操作原因', mfa_method: '驗證方式', account: '帳號', enabled: '啟用狀態',
  source: '來源', subject: '影響對象',
};

function adaptAuditRow(item: AdminAuditMaskedItem): AuditRow {
  return {
    auditId: item.audit_id,
    occurredAt: item.occurred_at,
    actorLabelMasked: item.actor_label_masked,
    actionFamily: ACTION_LABELS[item.action_family],
    targetLabelMasked: item.target_label_masked,
    ipAddressMasked: item.ip_address_masked,
    outcome: OUTCOME_LABELS[item.outcome],
  };
}

export function adaptAuditPage(page: AdminAuditMaskedPage): AuditPageView {
  return {
    items: page.items.map(adaptAuditRow),
    page: page.page,
    pageSize: page.page_size,
    total: page.total,
    totalPages: page.total_pages,
  };
}

export function adaptAuditDetail(detail: AdminAuditMaskedDetail): AuditDetailView {
  return {
    ...adaptAuditRow(detail),
    details: detail.details.map((field) => ({ key: DETAIL_LABELS[field.key], valueMasked: field.value_masked })),
  };
}
