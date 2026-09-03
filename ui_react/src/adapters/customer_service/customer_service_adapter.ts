/**
 * File: customer_service_adapter.ts
 * Description: 將客服 typed DTO 轉為 UI 顯示模型，列表摘要缺值時引導操作者開啟 canonical 明細。
 */
import type {
  CustomerServiceCategory,
  CustomerServiceDetail,
  CustomerServiceEvent,
  CustomerServicePage,
  CustomerServiceReplyApply,
  CustomerServiceReplyPreview,
  CustomerServiceResolvePreview,
  CustomerServiceStatus,
  CustomerServiceSummary,
  CustomerServiceTicket,
  CustomerServiceUpdateApply,
} from '../../api/customer_service/customer_service_schemas';

export interface CustomerServiceSummaryModel {
  waiting: number;
  handling: number;
  resolvedToday: number;
}

export interface CustomerServiceTicketModel {
  ticketId: number;
  ticketIdText: string;
  lineUserId: string;
  category: CustomerServiceCategory;
  categoryLabel: string;
  status: CustomerServiceStatus;
  statusLabel: string;
  version: number;
  clientId: number | null;
  caseNo: string | null;
  clientName: string | null;
  clientPhone: string | null;
  assignedAdminUserId: number | null;
  internalNote: string | null;
  createdAt: string | null;
  updatedAt: string | null;
  issueSummary: null;
}

export interface CustomerServiceEventModel {
  id: number;
  eventType: string;
  messageText: string | null;
  actorId: string;
  createdAt: string;
}

export interface CustomerServiceDetailModel {
  ticket: CustomerServiceTicketModel;
  events: CustomerServiceEventModel[];
}

export interface CustomerServicePageModel {
  items: CustomerServiceTicketModel[];
  total: number;
  page: number;
  pageSize: number;
}

export interface CustomerServiceResolvePreviewModel {
  ticketId: number;
  beforeStatus: CustomerServiceStatus;
  beforeStatusLabel: string;
  afterStatus: CustomerServiceStatus;
  afterStatusLabel: string;
  currentVersion: number;
  expectedVersion: number;
  blockers: string[];
  previewFingerprint: string;
  applyReady: boolean;
}

export interface CustomerServiceReplyPreviewModel {
  ticketId: number;
  beforeStatusLabel: string;
  afterStatusLabel: string;
  currentVersion: number;
  expectedVersion: number;
  replyCharacterCount: number;
  willEnqueueDelivery: true;
  previewFingerprint: string;
  applyReady: true;
}

export interface CustomerServiceReplyReceiptModel {
  ticketId: number;
  resultingStatusLabel: string;
  resultingVersion: number;
  previewFingerprint: string;
  deliveryEnqueued: true;
  deliveryDelivered: false;
  replayed: boolean;
  readback: CustomerServiceDetailModel;
  notice: string;
}

export interface CustomerServiceUpdateReceiptModel {
  ticketId: number;
  resultingStatusLabel: string;
  resultingVersion: number;
  previewFingerprint: string;
  replayed: boolean;
  readback: CustomerServiceDetailModel;
}

export const CUSTOMER_SERVICE_LIST_SUMMARY_UNAVAILABLE =
  '請開啟明細查看訊息';

export function customerServiceCategoryLabel(
  category: CustomerServiceCategory
): string {
  switch (category) {
    case 'service_flow':
      return '服務流程';
    case 'payment_subsidy':
      return '收費與補助';
    case 'service_progress':
      return '進度查詢';
    case 'profile_update':
      return '修改登記資料';
    case 'contact_union':
      return '聯絡工會人員';
    case 'other':
      return '其他問題';
  }
}

export function customerServiceStatusLabel(
  status: CustomerServiceStatus
): string {
  switch (status) {
    case 'waiting':
      return '待處理';
    case 'handling':
      return '處理中';
    case 'resolved':
      return '已結案';
  }
}

export function adaptCustomerServiceSummary(
  summary: CustomerServiceSummary
): CustomerServiceSummaryModel {
  return {
    waiting: summary.waiting,
    handling: summary.handling,
    resolvedToday: summary.resolved_today,
  };
}

export function adaptCustomerServiceTicket(
  ticket: CustomerServiceTicket
): CustomerServiceTicketModel {
  return {
    ticketId: ticket.ticket_id,
    ticketIdText: String(ticket.ticket_id),
    lineUserId: ticket.line_user_id,
    category: ticket.category,
    categoryLabel: customerServiceCategoryLabel(ticket.category),
    status: ticket.status,
    statusLabel: customerServiceStatusLabel(ticket.status),
    version: ticket.version,
    clientId: ticket.client_id ?? null,
    caseNo: ticket.case_no ?? null,
    clientName: ticket.client_name ?? null,
    clientPhone: ticket.client_phone ?? null,
    assignedAdminUserId: ticket.assigned_admin_user_id ?? null,
    internalNote: ticket.internal_note ?? null,
    createdAt: ticket.created_at ?? null,
    updatedAt: ticket.updated_at ?? null,
    issueSummary: null,
  };
}

export function adaptCustomerServiceEvent(
  event: CustomerServiceEvent
): CustomerServiceEventModel {
  return {
    id: event.id,
    eventType: event.event_type,
    messageText: event.message_text ?? null,
    actorId: event.actor_id,
    createdAt: event.created_at,
  };
}

export function adaptCustomerServiceDetail(
  detail: CustomerServiceDetail
): CustomerServiceDetailModel {
  return {
    ticket: adaptCustomerServiceTicket(detail.ticket),
    events: detail.events.map(adaptCustomerServiceEvent),
  };
}

export function adaptCustomerServicePage(
  page: CustomerServicePage
): CustomerServicePageModel {
  return {
    items: page.items.map(adaptCustomerServiceTicket),
    total: page.total,
    page: page.page,
    pageSize: page.page_size,
  };
}

export function adaptCustomerServiceResolvePreview(
  preview: CustomerServiceResolvePreview
): CustomerServiceResolvePreviewModel {
  return {
    ticketId: preview.ticket_id,
    beforeStatus: preview.before_status,
    beforeStatusLabel: customerServiceStatusLabel(preview.before_status),
    afterStatus: preview.after_status,
    afterStatusLabel: customerServiceStatusLabel(preview.after_status),
    currentVersion: preview.current_version,
    expectedVersion: preview.expected_version,
    blockers: [...preview.blockers],
    previewFingerprint: preview.preview_fingerprint,
    applyReady: preview.apply_ready,
  };
}

export function adaptCustomerServiceReplyPreview(
  preview: CustomerServiceReplyPreview
): CustomerServiceReplyPreviewModel {
  return {
    ticketId: preview.ticket_id,
    beforeStatusLabel: customerServiceStatusLabel(preview.before_status),
    afterStatusLabel: customerServiceStatusLabel(preview.after_status),
    currentVersion: preview.current_version,
    expectedVersion: preview.expected_version,
    replyCharacterCount: preview.reply_character_count,
    willEnqueueDelivery: preview.will_enqueue_delivery,
    previewFingerprint: preview.preview_fingerprint,
    applyReady: preview.apply_ready,
  };
}

export function adaptCustomerServiceReplyReceipt(
  receipt: CustomerServiceReplyApply
): CustomerServiceReplyReceiptModel {
  return {
    ticketId: receipt.ticket_id,
    resultingStatusLabel: customerServiceStatusLabel(receipt.resulting_status),
    resultingVersion: receipt.resulting_version,
    previewFingerprint: receipt.preview_fingerprint,
    deliveryEnqueued: receipt.delivery_enqueued,
    deliveryDelivered: receipt.delivery_delivered,
    replayed: receipt.replayed,
    readback: adaptCustomerServiceDetail(receipt.readback),
    notice: '後端已建立 durable delivery task；排入佇列不等於 LINE provider 已送出、使用者已收件或已讀。',
  };
}

export function adaptCustomerServiceUpdateReceipt(
  receipt: CustomerServiceUpdateApply
): CustomerServiceUpdateReceiptModel {
  return {
    ticketId: receipt.ticket_id,
    resultingStatusLabel: customerServiceStatusLabel(receipt.resulting_status),
    resultingVersion: receipt.resulting_version,
    previewFingerprint: receipt.preview_fingerprint,
    replayed: receipt.replayed,
    readback: adaptCustomerServiceDetail(receipt.readback),
  };
}
