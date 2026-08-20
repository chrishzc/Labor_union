/**
 * File: line_identity_contract_fixtures.ts
 * Description: 提供去敏且可重現的 LINE 身分管理嚴格契約測試資料，不供 production 使用。
 */
import type {
  LineIdentityBindingPageView,
  LineIdentityBindingView,
  LineIdentityRevocationApplyRequest,
  LineIdentityRevocationPreviewView,
  LineIdentityRevocationRequestView,
} from '../../../api/line_identity/line_identity_schemas';

export const FIXTURE_LINE_USER_ID = 'U1234567890abcdef1234567890abcdef';

export const BOUND_IDENTITY_FIXTURE: LineIdentityBindingView = {
  line_user_id: FIXTURE_LINE_USER_ID,
  status: 'bound',
  version: 7,
  subject_type: 'customer',
  subject_reference: 'CLIENT-FIXTURE-001',
  subject_name: '測試客戶甲',
  updated_at: '2026-08-16T02:30:00Z',
  revocation_request_id: null,
  revocation_status: null,
  revoked_at: null,
};

export const BINDING_PAGE_FIXTURE: LineIdentityBindingPageView = {
  items: [BOUND_IDENTITY_FIXTURE],
  total: 1,
  page: 1,
  page_size: 25,
};

export const REVOCATION_PREVIEW_FIXTURE: LineIdentityRevocationPreviewView = {
  binding: BOUND_IDENTITY_FIXTURE,
  default_menu_publication_id: 81,
  provider_menu_id: 'richmenu-provider-fixture-private',
  blockers: [],
};

export const BLOCKED_REVOCATION_PREVIEW_FIXTURE: LineIdentityRevocationPreviewView = {
  binding: BOUND_IDENTITY_FIXTURE,
  default_menu_publication_id: null,
  provider_menu_id: null,
  blockers: ['line_identity_default_menu_not_published'],
};

export const REVOCATION_APPLY_REQUEST_FIXTURE: LineIdentityRevocationApplyRequest = {
  expected_version: 7,
  reason: '  客戶已確認解除 LINE 身分綁定  ',
  idempotency_key: 'line-revoke-idempotency-fixture-001',
  correlation_id: 'line-revoke-correlation-fixture-001',
};

export const REVOCATION_REQUEST_FIXTURE: LineIdentityRevocationRequestView = {
  request_id: 901,
  line_user_id: FIXTURE_LINE_USER_ID,
  subject_type: 'customer',
  subject_reference: 'CLIENT-FIXTURE-001',
  status: 'pending_menu_reset',
  pending_binding_version: 8,
  publication_id: 81,
  provider_menu_id: 'richmenu-provider-fixture-private',
  requested_by_actor_id: 'actor-fixture-private',
  reason: 'restricted-reason-fixture-private',
  attempt_count: 0,
  last_error_code: null,
  last_error_message: null,
};

export function envelope<T>(data: T) {
  return {
    success: true,
    message: 'Success',
    data,
    error: null,
  };
}
