/**
 * File: customer_service_contract_fixtures.ts
 * Description: 提供客服 Client 與 Adapter 契約測試的最小去敏固定資料。
 */
import type {
  CustomerServiceDetail,
  CustomerServiceDetailResponse,
  CustomerServicePage,
  CustomerServicePageResponse,
  CustomerServiceResolveApplyRequest,
  CustomerServiceResolvePreview,
  CustomerServiceResolvePreviewRequest,
  CustomerServiceResolvePreviewResponse,
  CustomerServiceSummary,
  CustomerServiceSummaryResponse,
  CustomerServiceTicket,
} from '../../../api/customer_service/customer_service_schemas';

export const CUSTOMER_SERVICE_TICKET_FIXTURE: CustomerServiceTicket = {
  ticket_id: 31,
  line_user_id_masked: 'U12***789',
  category: 'profile_update',
  status: 'handling',
  version: 4,
  client_id: 18,
  case_no: 'ORD-TEST-0031',
  client_name: '測試客戶',
  client_phone: '09**-***-321',
  assigned_admin_user_id: 7,
  internal_note: null,
  created_at: '2026-08-16T08:00:00+00:00',
  updated_at: '2026-08-16T09:00:00+00:00',
};

export const CUSTOMER_SERVICE_DETAIL_FIXTURE: CustomerServiceDetail = {
  ticket: CUSTOMER_SERVICE_TICKET_FIXTURE,
  events: [
    {
      id: 81,
      event_type: 'message_received',
      message_text: '請協助確認資料更新方式',
      actor_id: 'line-user:masked',
      created_at: '2026-08-16T08:00:00+00:00',
    },
  ],
};

export const CUSTOMER_SERVICE_PAGE_FIXTURE: CustomerServicePage = {
  items: [CUSTOMER_SERVICE_TICKET_FIXTURE],
  total: 1,
  page: 1,
  page_size: 25,
};

export const CUSTOMER_SERVICE_SUMMARY_FIXTURE: CustomerServiceSummary = {
  waiting: 2,
  handling: 1,
  resolved_today: 3,
};

export const CUSTOMER_SERVICE_RESOLVE_PREVIEW_REQUEST_FIXTURE: CustomerServiceResolvePreviewRequest = {
  status: 'resolved',
  internal_note: '已由工會人員確認處理完成',
  expected_version: 4,
};

export const CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE: CustomerServiceResolvePreview = {
  ticket_id: 31,
  before_status: 'handling',
  after_status: 'resolved',
  current_version: 4,
  expected_version: 4,
  blockers: [],
  preview_fingerprint:
    '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
  apply_ready: true,
};

export const CUSTOMER_SERVICE_RESOLVE_APPLY_REQUEST_FIXTURE: CustomerServiceResolveApplyRequest = {
  ...CUSTOMER_SERVICE_RESOLVE_PREVIEW_REQUEST_FIXTURE,
  preview_fingerprint:
    CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE.preview_fingerprint,
};

export const CUSTOMER_SERVICE_SUMMARY_RESPONSE_FIXTURE: CustomerServiceSummaryResponse = {
  success: true,
  message: 'Success',
  data: CUSTOMER_SERVICE_SUMMARY_FIXTURE,
  error: null,
};

export const CUSTOMER_SERVICE_PAGE_RESPONSE_FIXTURE: CustomerServicePageResponse = {
  success: true,
  message: 'Success',
  data: CUSTOMER_SERVICE_PAGE_FIXTURE,
  error: null,
};

export const CUSTOMER_SERVICE_DETAIL_RESPONSE_FIXTURE: CustomerServiceDetailResponse = {
  success: true,
  message: 'Success',
  data: CUSTOMER_SERVICE_DETAIL_FIXTURE,
  error: null,
};

export const CUSTOMER_SERVICE_RESOLVE_PREVIEW_RESPONSE_FIXTURE: CustomerServiceResolvePreviewResponse = {
  success: true,
  message: 'Success',
  data: CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE,
  error: null,
};
