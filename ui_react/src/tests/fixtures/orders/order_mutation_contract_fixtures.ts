/**
 * File: order_mutation_contract_fixtures.ts
 * Description: Phase 2B Orders 安全變更端點正向、反向與 Typed Error 契約測試固定資料集。
 */
import type {
  ServiceDateConfirmationQueryView,
  ServiceDateConfirmationPreviewView,
  ServiceDateConfirmationReceiptView,
  ServiceDateApplyPayload,
  ServiceDatePreviewPayload,
  OrderReopenPreviewView,
  OrderReopenReceiptView,
  OrderReopenApplyPayload,
} from '../../../api/orders/order_mutation_schemas';

// ============================================================================
// 1. Confirmed Service Dates Fixtures
// ============================================================================

export const realisticServiceDateQueryView: ServiceDateConfirmationQueryView = {
  case_no: 'ORD-2026-0801',
  order_version: 1,
  scheduling_version: 1,
  contracted_service_days: 3,
  suggested_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
  selectable_dates: [
    '2026-09-01',
    '2026-09-02',
    '2026-09-03',
    '2026-09-04',
    '2026-09-05',
  ],
  current_version: null,
  current_dates: [],
};

export const realisticServiceDateQueryViewConfirmed: ServiceDateConfirmationQueryView = {
  case_no: 'ORD-2026-0801',
  order_version: 2,
  scheduling_version: 2,
  contracted_service_days: 3,
  suggested_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
  selectable_dates: [
    '2026-09-01',
    '2026-09-02',
    '2026-09-03',
    '2026-09-04',
    '2026-09-05',
  ],
  current_version: 1,
  current_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
};

export const realisticServiceDatePreviewPayload: ServiceDatePreviewPayload = {
  service_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
};

export const realisticServiceDatePreviewView: ServiceDateConfirmationPreviewView = {
  case_no: 'ORD-2026-0801',
  order_version: 1,
  scheduling_version: 1,
  current_version: null,
  service_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
  weeks: [
    {
      week_number: 1,
      period_start: '2026-08-30',
      period_end: '2026-09-05',
      service_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
      service_day_count: 3,
    },
  ],
  preview_fingerprint: 'a'.repeat(64),
};

export const realisticServiceDateApplyPayload: ServiceDateApplyPayload = {
  service_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
  expected_order_version: 1,
  expected_scheduling_version: 1,
  preview_fingerprint: 'a'.repeat(64),
  reason: '客戶確認服務日期為 9/1 至 9/3',
};

export const realisticServiceDateReceiptView: ServiceDateConfirmationReceiptView = {
  case_no: 'ORD-2026-0801',
  confirmed_version: 1,
  order_version: 1,
  scheduling_version: 1,
  service_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
  preview_fingerprint: 'a'.repeat(64),
};

// ============================================================================
// 2. Controlled Order Reopen Fixtures
// ============================================================================

export const realisticOrderReopenPreviewView: OrderReopenPreviewView = {
  case_no: 'ORD-2026-0801',
  order_version: 3,
  client_finance_version: 2,
  payroll_version: 2,
  cancellation_event_id: 88,
  before_status: '訂單取消',
  after_status: '洽談中',
  requires_fresh_scheduling_preview: true,
  restored_assignment_ids: [],
  restored_schedule_ids: [],
  restored_lock_ids: [],
  preview_fingerprint: 'b'.repeat(64),
};

export const realisticOrderReopenApplyPayload: OrderReopenApplyPayload = {
  expected_order_version: 3,
  expected_client_finance_version: 2,
  expected_payroll_version: 2,
  preview_fingerprint: 'b'.repeat(64),
  reason: '客戶來電確認恢復需求，重新啟動案件流程',
};

export const realisticOrderReopenReceiptView: OrderReopenReceiptView = {
  case_no: 'ORD-2026-0801',
  order_version: 4,
  lifecycle_status: '洽談中',
  cancellation_event_id: 88,
  requires_fresh_scheduling_preview: true,
  preview_fingerprint: 'b'.repeat(64),
};

// ============================================================================
// 3. Typed Error & Backend Gap Fixtures
// ============================================================================

export const mockDomainBlockedErrorRaw = {
  detail: {
    error: {
      category: 'domain_blocked',
      code: 'reopen_blocked_by_financial_settlement',
      message: '訂單已有款項結清紀錄，禁止直接重開',
      correlation_id: 'corr-reopen-001',
      field_errors: [],
      domain_blockers: ['reopen_blocked_by_financial_settlement'],
      retryable: false,
      current_version: null,
    },
  },
};

export const mockConflictErrorRaw = {
  detail: {
    error: {
      category: 'conflict',
      code: 'stale_order_version',
      message: '訂單版本已過期，請重新整理並預覽',
      correlation_id: 'corr-reopen-002',
      field_errors: [],
      domain_blockers: [],
      retryable: false,
      current_version: 5,
    },
  },
};

export const mockValidationErrorRaw = {
  detail: {
    error: {
      category: 'validation',
      code: 'invalid_reason_length',
      message: '重開原因長度不符規範',
      correlation_id: 'corr-reopen-003',
      field_errors: [
        { field: 'reason', code: 'too_short', message: '原因不可為空白' },
      ],
      domain_blockers: [],
      retryable: false,
      current_version: null,
    },
  },
};

export const mockUnavailableErrorRaw = {
  detail: {
    error: {
      category: 'unavailable',
      code: 'order_reopen_transaction_temporarily_unavailable',
      message: '可使用相同冪等鍵重試這次受控重開。',
      correlation_id: 'corr-reopen-004',
      field_errors: [],
      domain_blockers: [],
      retryable: true,
      current_version: null,
    },
  },
};

export const mockIdempotencyMismatchErrorRaw = {
  detail: {
    error: {
      category: 'idempotency_mismatch',
      code: 'idempotency_payload_mismatch',
      message: '相同冪等鍵但請求內容不一致',
      correlation_id: 'corr-reopen-005',
      field_errors: [],
      domain_blockers: [],
      retryable: false,
      current_version: null,
    },
  },
};

export const mockFastApi401Raw = {
  detail: 'Not authenticated',
};

export const mockFastApi403Raw = {
  detail: 'Operation not permitted',
};

export const mockFastApi422Raw = {
  detail: [
    {
      loc: ['body', 'reason'],
      msg: 'field required',
      type: 'value_error.missing',
    },
  ],
};
