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
  actionFamily: AdminAuditMaskedItem['action_family'];
  targetLabelMasked: string | null;
  ipAddressMasked: string | null;
  outcome: AdminAuditMaskedItem['outcome'];
  reasonCode: string | null;
}

export interface AuditPageView {
  items: AuditRow[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

export interface AuditDetailView extends AuditRow {
  details: Array<{ key: AdminAuditMaskedDetail['details'][number]['key']; valueMasked: string }>;
}

function adaptAuditRow(item: AdminAuditMaskedItem): AuditRow {
  return {
    auditId: item.audit_id,
    occurredAt: item.occurred_at,
    actorLabelMasked: item.actor_label_masked,
    actionFamily: item.action_family,
    targetLabelMasked: item.target_label_masked,
    ipAddressMasked: item.ip_address_masked,
    outcome: item.outcome,
    reasonCode: item.reason_code,
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
    details: detail.details.map((field) => ({ key: field.key, valueMasked: field.value_masked })),
  };
}
