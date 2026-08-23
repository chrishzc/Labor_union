/**
 * File: order_mutation_adapter.ts
 * Description: Orders 安全變更 Adapter，區分 Apply 未明、receipt 已確定與後續觀察失敗，禁止偽造狀態。
 */
import {
  ordersMutationClient,
  type OrderMutationRequestOptions,
} from '../../api/orders/order_mutation_client';
import type {
  ServiceDateConfirmationQueryView,
  ServiceDateConfirmationPreviewView,
  ServiceDateConfirmationReceiptView,
  OrderReopenPreviewView,
  OrderReopenReceiptView,
} from '../../api/orders/order_mutation_schemas';
import {
  OrderMutationConflictError,
  OrderMutationValidationError,
  OrderMutationUnavailableError,
  OrderMutationError,
  type ApiError,
  ApiHttpError,
  ApiTimeoutError,
  ApiNetworkError,
  decodeMutationError,
} from '../../api/orders/order_mutation_errors';
import {
  orderMutationFlowStore,
  type ServiceDatesDraftState,
  type ReopenDraftState,
} from './order_mutation_flow_store';

// ============================================================================
// 1. Discriminated Union State Types (Section 5.1 & 5.2)
// ============================================================================

export type ServiceDatesMachineState =
  | { type: 'idle' }
  | { type: 'query_loading'; caseNo: string }
  | {
      type: 'query_ready';
      caseNo: string;
      queryView: ServiceDateConfirmationQueryView;
      selectedDates: string[];
    }
  | {
      type: 'draft_changed';
      caseNo: string;
      queryView: ServiceDateConfirmationQueryView;
      selectedDates: string[];
      canPreview: boolean;
    }
  | {
      type: 'preview_loading';
      caseNo: string;
      queryView: ServiceDateConfirmationQueryView;
      selectedDates: string[];
    }
  | {
      type: 'preview_ready';
      caseNo: string;
      queryView: ServiceDateConfirmationQueryView;
      selectedDates: string[];
      previewView: ServiceDateConfirmationPreviewView;
      reason: string;
    }
  | {
      type: 'apply_pending';
      caseNo: string;
      queryView: ServiceDateConfirmationQueryView;
      selectedDates: string[];
      previewView: ServiceDateConfirmationPreviewView;
      reason: string;
      idempotencyKey: string;
    }
  | {
      type: 'receipt_received';
      caseNo: string;
      receiptView: ServiceDateConfirmationReceiptView;
    }
  | {
      type: 'requery_loading';
      caseNo: string;
      receiptView: ServiceDateConfirmationReceiptView;
    }
  | {
      type: 'observation_failed';
      caseNo: string;
      receiptView: ServiceDateConfirmationReceiptView;
      error: OrderMutationError | ApiError;
    }
  | {
      type: 'observed';
      caseNo: string;
      queryView: ServiceDateConfirmationQueryView;
      confirmedVersion: number;
    }
  | {
      type: 'outcome_unknown';
      caseNo: string;
      queryView: ServiceDateConfirmationQueryView;
      selectedDates: string[];
      previewView: ServiceDateConfirmationPreviewView;
      reason: string;
      idempotencyKey: string;
      error: OrderMutationError | ApiError;
    }
  | {
      type: 'stale';
      caseNo: string;
      message: string;
      requiresRequery: true;
    }
  | {
      type: 'typed_error';
      caseNo: string;
      error: OrderMutationError | ApiError;
    };

export type ReopenMachineState =
  | { type: 'closed' }
  | { type: 'preview_loading'; caseNo: string }
  | {
      type: 'preview_ready';
      caseNo: string;
      previewView: OrderReopenPreviewView;
      reason: string;
    }
  | {
      type: 'apply_pending';
      caseNo: string;
      previewView: OrderReopenPreviewView;
      reason: string;
      idempotencyKey: string;
    }
  | {
      type: 'receipt_received';
      caseNo: string;
      receiptView: OrderReopenReceiptView;
    }
  | {
      type: 'requery_loading';
      caseNo: string;
      receiptView: OrderReopenReceiptView;
    }
  | {
      type: 'observation_failed';
      caseNo: string;
      receiptView: OrderReopenReceiptView;
      error: OrderMutationError | ApiError;
    }
  | {
      type: 'observed';
      caseNo: string;
      receiptView: OrderReopenReceiptView;
    }
  | {
      type: 'outcome_unknown';
      caseNo: string;
      previewView: OrderReopenPreviewView;
      reason: string;
      idempotencyKey: string;
      error: OrderMutationError | ApiError;
    }
  | {
      type: 'stale';
      caseNo: string;
      message: string;
      previewInvalidated: true;
    }
  | {
      type: 'typed_error';
      caseNo: string;
      error: OrderMutationError | ApiError;
    };

// ============================================================================
// 2. Error Categorization Helpers
// ============================================================================

const STALE_ERROR_CODES = new Set([
  'stale_order_version',
  'stale_scheduling_version',
  'service_date_confirmation_stale_version',
  'service_date_confirmation_preview_stale',
  'order_version_conflict',
  'client_finance_candidate_stale',
  'payroll_version_conflict',
  'stale_preview',
]);

function isStaleConflictError(error: unknown): boolean {
  return (
    (error instanceof OrderMutationConflictError || error instanceof ApiHttpError) &&
    STALE_ERROR_CODES.has(error.code)
  );
}

function isOutcomeUnknownError(error: unknown): boolean {
  if (
    error instanceof ApiTimeoutError ||
    error instanceof ApiNetworkError ||
    error instanceof OrderMutationUnavailableError
  ) {
    return true;
  }
  if (error instanceof OrderMutationError) {
    return error.retryable || error.status === 503;
  }
  if (error instanceof ApiHttpError) {
    return error.status === 503;
  }
  return false;
}

function normalizeFlowError(error: unknown, caseNo: string): OrderMutationError | ApiError {
  return decodeMutationError(error, { caseNo });
}

// ============================================================================
// 3. State Resolvers
// ============================================================================

export function resolveServiceDatesMachineState(
  draft: ServiceDatesDraftState | undefined
): ServiceDatesMachineState {
  if (!draft) return { type: 'idle' };

  switch (draft.status) {
    case 'idle':
      return { type: 'idle' };
    case 'query_loading':
      return { type: 'query_loading', caseNo: draft.caseNo };
    case 'query_ready':
      if (!draft.queryView) return { type: 'idle' };
      return {
        type: 'query_ready',
        caseNo: draft.caseNo,
        queryView: draft.queryView,
        selectedDates: draft.selectedDates,
      };
    case 'draft_changed':
      if (!draft.queryView) return { type: 'idle' };
      return {
        type: 'draft_changed',
        caseNo: draft.caseNo,
        queryView: draft.queryView,
        selectedDates: draft.selectedDates,
        canPreview:
          draft.selectedDates.length > 0 &&
          draft.selectedDates.length === draft.queryView.contracted_service_days,
      };
    case 'preview_loading':
      if (!draft.queryView) return { type: 'idle' };
      return {
        type: 'preview_loading',
        caseNo: draft.caseNo,
        queryView: draft.queryView,
        selectedDates: draft.selectedDates,
      };
    case 'preview_ready':
      if (!draft.queryView || !draft.previewView) return { type: 'idle' };
      return {
        type: 'preview_ready',
        caseNo: draft.caseNo,
        queryView: draft.queryView,
        selectedDates: draft.selectedDates,
        previewView: draft.previewView,
        reason: draft.reason,
      };
    case 'apply_pending':
      if (!draft.queryView || !draft.previewView) return { type: 'idle' };
      return {
        type: 'apply_pending',
        caseNo: draft.caseNo,
        queryView: draft.queryView,
        selectedDates: draft.selectedDates,
        previewView: draft.previewView,
        reason: draft.reason,
        idempotencyKey: draft.idempotencyKey,
      };
    case 'receipt_received':
      if (!draft.receiptView) return { type: 'idle' };
      return {
        type: 'receipt_received',
        caseNo: draft.caseNo,
        receiptView: draft.receiptView,
      };
    case 'requery_loading':
      if (!draft.receiptView) return { type: 'idle' };
      return {
        type: 'requery_loading',
        caseNo: draft.caseNo,
        receiptView: draft.receiptView,
      };
    case 'observation_failed':
      if (!draft.receiptView || !draft.error) return { type: 'idle' };
      return {
        type: 'observation_failed',
        caseNo: draft.caseNo,
        receiptView: draft.receiptView,
        error: draft.error,
      };
    case 'observed':
      if (!draft.queryView) return { type: 'idle' };
      return {
        type: 'observed',
        caseNo: draft.caseNo,
        queryView: draft.queryView,
        confirmedVersion: draft.queryView.current_version ?? 1,
      };
    case 'outcome_unknown':
      if (!draft.queryView || !draft.previewView || !draft.error) {
        return {
          type: 'typed_error',
          caseNo: draft.caseNo,
          error:
            draft.error ??
            new OrderMutationUnavailableError({
              code: 'outcome_unknown_fallback',
              message: '請求狀態未明，請重試',
              status: 503,
            }),
        };
      }
      return {
        type: 'outcome_unknown',
        caseNo: draft.caseNo,
        queryView: draft.queryView,
        selectedDates: draft.selectedDates,
        previewView: draft.previewView,
        reason: draft.reason,
        idempotencyKey: draft.idempotencyKey,
        error: draft.error,
      };
    case 'stale':
      return {
        type: 'stale',
        caseNo: draft.caseNo,
        message: draft.error?.message ?? '版本已過期，請重新查詢並預覽',
        requiresRequery: true,
      };
    case 'typed_error':
      return {
        type: 'typed_error',
        caseNo: draft.caseNo,
        error:
          draft.error ??
          new OrderMutationConflictError({
            code: 'unknown_error',
            message: '操作發生錯誤',
            status: 500,
          }),
      };
  }
}

export function resolveReopenMachineState(
  draft: ReopenDraftState | undefined
): ReopenMachineState {
  if (!draft) return { type: 'closed' };

  switch (draft.status) {
    case 'closed':
      return { type: 'closed' };
    case 'preview_loading':
      return { type: 'preview_loading', caseNo: draft.caseNo };
    case 'preview_ready':
      if (!draft.previewView) return { type: 'closed' };
      return {
        type: 'preview_ready',
        caseNo: draft.caseNo,
        previewView: draft.previewView,
        reason: draft.reason,
      };
    case 'apply_pending':
      if (!draft.previewView) return { type: 'closed' };
      return {
        type: 'apply_pending',
        caseNo: draft.caseNo,
        previewView: draft.previewView,
        reason: draft.reason,
        idempotencyKey: draft.idempotencyKey,
      };
    case 'receipt_received':
      if (!draft.receiptView) return { type: 'closed' };
      return {
        type: 'receipt_received',
        caseNo: draft.caseNo,
        receiptView: draft.receiptView,
      };
    case 'requery_loading':
      if (!draft.receiptView) return { type: 'closed' };
      return {
        type: 'requery_loading',
        caseNo: draft.caseNo,
        receiptView: draft.receiptView,
      };
    case 'observation_failed':
      if (!draft.receiptView || !draft.error) return { type: 'closed' };
      return {
        type: 'observation_failed',
        caseNo: draft.caseNo,
        receiptView: draft.receiptView,
        error: draft.error,
      };
    case 'observed':
      if (!draft.receiptView) {
        return {
          type: 'typed_error',
          caseNo: draft.caseNo,
          error: new OrderMutationUnavailableError({
            code: 'missing_reopen_receipt',
            message: '重開結果缺少伺服器 receipt，無法標示為已觀察',
            status: 503,
          }),
        };
      }
      return {
        type: 'observed',
        caseNo: draft.caseNo,
        receiptView: draft.receiptView,
      };
    case 'outcome_unknown':
      if (!draft.previewView || !draft.error) {
        return {
          type: 'typed_error',
          caseNo: draft.caseNo,
          error:
            draft.error ??
            new OrderMutationUnavailableError({
              code: 'outcome_unknown_fallback',
              message: '請求狀態未明，請重試',
              status: 503,
            }),
        };
      }
      return {
        type: 'outcome_unknown',
        caseNo: draft.caseNo,
        previewView: draft.previewView,
        reason: draft.reason,
        idempotencyKey: draft.idempotencyKey,
        error: draft.error,
      };
    case 'stale':
      return {
        type: 'stale',
        caseNo: draft.caseNo,
        message: draft.error?.message ?? '訂單版本已過期，預覽已失效',
        previewInvalidated: true,
      };
    case 'typed_error':
      return {
        type: 'typed_error',
        caseNo: draft.caseNo,
        error:
          draft.error ??
          new OrderMutationConflictError({
            code: 'unknown_error',
            message: '操作發生錯誤',
            status: 500,
          }),
      };
  }
}

// ============================================================================
// 4. Service Dates Flow Operations
// ============================================================================

export async function fetchServiceDatesQuery(
  caseNo: string,
  options?: OrderMutationRequestOptions
): Promise<ServiceDateConfirmationQueryView> {
  orderMutationFlowStore.setServiceDatesQueryLoading(caseNo);
  try {
    const queryView = await ordersMutationClient.getServiceDates(caseNo, options);
    orderMutationFlowStore.setServiceDatesQueryReady(caseNo, queryView);
    return queryView;
  } catch (err) {
    if (options?.signal?.aborted) throw err;
    const error = normalizeFlowError(err, caseNo);
    orderMutationFlowStore.setServiceDatesTypedError(caseNo, error);
    throw err;
  }
}

export function selectServiceDates(caseNo: string, dates: string[]): void {
  orderMutationFlowStore.updateServiceDatesSelection(caseNo, dates);
}

export function updateServiceDatesReason(caseNo: string, reason: string): void {
  orderMutationFlowStore.updateServiceDatesReason(caseNo, reason);
}

export async function previewServiceDatesFlow(
  caseNo: string,
  options?: OrderMutationRequestOptions
): Promise<ServiceDateConfirmationPreviewView> {
  const draft = orderMutationFlowStore.getOrCreateServiceDatesDraft(caseNo);
  if (draft.status === 'preview_loading' || draft.status === 'apply_pending') {
    throw new Error('正在處理中，請勿重複提交');
  }

  if (draft.selectedDates.length === 0) {
    const err = new OrderMutationValidationError({
      code: 'empty_dates',
      message: '請至少選擇一個服務日期',
    });
    orderMutationFlowStore.setServiceDatesTypedError(caseNo, err);
    throw err;
  }

  orderMutationFlowStore.setServiceDatesPreviewLoading(caseNo);
  try {
    const previewView = await ordersMutationClient.previewServiceDates(
      caseNo,
      { service_dates: draft.selectedDates },
      options
    );
    if (options?.signal?.aborted) throw new Error('Service Dates Preview已取消。');
    orderMutationFlowStore.setServiceDatesPreviewReady(caseNo, previewView);
    return previewView;
  } catch (err) {
    if (options?.signal?.aborted) throw err;
    const error = normalizeFlowError(err, caseNo);
    if (isStaleConflictError(error)) {
      orderMutationFlowStore.setServiceDatesStale(caseNo, error);
    } else {
      orderMutationFlowStore.setServiceDatesTypedError(caseNo, error);
    }
    throw err;
  }
}

export async function applyServiceDatesFlow(
  caseNo: string,
  options?: OrderMutationRequestOptions
): Promise<ServiceDateConfirmationReceiptView> {
  const draft = orderMutationFlowStore.getOrCreateServiceDatesDraft(caseNo);
  if (draft.status === 'apply_pending') {
    throw new Error('正在套用變更中，請勿重複提交');
  }

  if (!draft.previewView) {
    const err = new OrderMutationValidationError({
      code: 'missing_preview',
      message: '請先完成預覽後再進行確認套用',
    });
    orderMutationFlowStore.setServiceDatesTypedError(caseNo, err);
    throw err;
  }

  const trimmedReason = draft.reason.trim();
  if (trimmedReason.length < 1 || trimmedReason.length > 500) {
    const err = new OrderMutationValidationError({
      code: 'invalid_reason',
      message: '確認原因必須為 1 至 500 字元且不可為純空白',
    });
    orderMutationFlowStore.setServiceDatesTypedError(caseNo, err);
    throw err;
  }

  orderMutationFlowStore.setServiceDatesApplyPending(caseNo);

  let receipt: ServiceDateConfirmationReceiptView;
  try {
    receipt = await ordersMutationClient.applyServiceDates(
      caseNo,
      {
        service_dates: draft.selectedDates,
        expected_order_version: draft.previewView.order_version,
        expected_scheduling_version: draft.previewView.scheduling_version,
        preview_fingerprint: draft.previewView.preview_fingerprint,
        reason: draft.reason,
      },
      {
        ...options,
        idempotencyKey: draft.idempotencyKey,
      }
    );

  } catch (err) {
    const error = normalizeFlowError(err, caseNo);
    if (isOutcomeUnknownError(error)) {
      orderMutationFlowStore.setServiceDatesOutcomeUnknown(caseNo, error);
    } else if (isStaleConflictError(error)) {
      orderMutationFlowStore.setServiceDatesStale(caseNo, error);
    } else {
      orderMutationFlowStore.setServiceDatesTypedError(caseNo, error);
    }
    throw err;
  }

  if (receipt.preview_fingerprint !== draft.previewView.preview_fingerprint) {
    const mismatchErr = new OrderMutationConflictError({
      code: 'fingerprint_mismatch',
      message: '伺服器已回傳 receipt，但指紋與預覽不一致；已停止後續觀察並要求人工處理。',
      status: 409,
    });
    orderMutationFlowStore.setServiceDatesReceiptReceived(caseNo, receipt);
    orderMutationFlowStore.setServiceDatesObservationFailed(caseNo, mismatchErr);
    throw mismatchErr;
  }

  orderMutationFlowStore.setServiceDatesReceiptReceived(caseNo, receipt);
  orderMutationFlowStore.setServiceDatesRequeryLoading(caseNo);
  try {
    const freshQuery = await ordersMutationClient.getServiceDates(caseNo, options);
    orderMutationFlowStore.setServiceDatesObserved(caseNo, freshQuery);
    return receipt;
  } catch (err) {
    orderMutationFlowStore.setServiceDatesObservationFailed(
      caseNo,
      normalizeFlowError(err, caseNo)
    );
    throw err;
  }
}

export async function retryServiceDatesApplyFlow(
  caseNo: string,
  options?: OrderMutationRequestOptions
): Promise<ServiceDateConfirmationReceiptView> {
  const draft = orderMutationFlowStore.getOrCreateServiceDatesDraft(caseNo);
  if (draft.status !== 'outcome_unknown') {
    throw new Error('僅能在狀態未明 (outcome_unknown) 時進行重試');
  }
  return applyServiceDatesFlow(caseNo, options);
}

export async function retryServiceDatesObservationFlow(
  caseNo: string,
  options?: OrderMutationRequestOptions
): Promise<ServiceDateConfirmationQueryView> {
  const draft = orderMutationFlowStore.getOrCreateServiceDatesDraft(caseNo);
  if (draft.status !== 'observation_failed' || !draft.receiptView) {
    throw new Error('僅能在 receipt 已收到但重新查詢失敗時重試觀察');
  }
  orderMutationFlowStore.setServiceDatesRequeryLoading(caseNo);
  try {
    const freshQuery = await ordersMutationClient.getServiceDates(caseNo, options);
    orderMutationFlowStore.setServiceDatesObserved(caseNo, freshQuery);
    return freshQuery;
  } catch (err) {
    orderMutationFlowStore.setServiceDatesObservationFailed(
      caseNo,
      normalizeFlowError(err, caseNo)
    );
    throw err;
  }
}

// ============================================================================
// 5. Controlled Reopen Flow Operations
// ============================================================================

export async function previewReopenFlow(
  caseNo: string,
  options?: OrderMutationRequestOptions
): Promise<OrderReopenPreviewView> {
  const draft = orderMutationFlowStore.getOrCreateReopenDraft(caseNo);
  if (draft.status === 'preview_loading' || draft.status === 'apply_pending') {
    throw new Error('正在處理中，請勿重複提交');
  }

  orderMutationFlowStore.setReopenPreviewLoading(caseNo);
  try {
    const preview = await ordersMutationClient.previewReopen(caseNo, options);
    if (options?.signal?.aborted) throw new Error('Controlled Reopen Preview已取消。');

    // Fail closed on restored lists drift
    if (
      preview.restored_assignment_ids.length > 0 ||
      preview.restored_schedule_ids.length > 0 ||
      preview.restored_lock_ids.length > 0
    ) {
      const driftErr = new OrderMutationConflictError({
        code: 'contract_drift_detected',
        message: '伺服器返回非空的 restored 列表，拒絕重開操作',
        status: 409,
      });
      orderMutationFlowStore.setReopenTypedError(caseNo, driftErr);
      throw driftErr;
    }

    orderMutationFlowStore.setReopenPreviewReady(caseNo, preview);
    return preview;
  } catch (err) {
    if (options?.signal?.aborted) throw err;
    const error = normalizeFlowError(err, caseNo);
    if (isStaleConflictError(error)) {
      orderMutationFlowStore.setReopenStale(caseNo, error);
    } else {
      orderMutationFlowStore.setReopenTypedError(caseNo, error);
    }
    throw err;
  }
}

export function updateReopenReason(caseNo: string, reason: string): void {
  orderMutationFlowStore.updateReopenReason(caseNo, reason);
}

export async function applyReopenFlow(
  caseNo: string,
  onRequery?: () => Promise<void>,
  options?: OrderMutationRequestOptions
): Promise<OrderReopenReceiptView> {
  const draft = orderMutationFlowStore.getOrCreateReopenDraft(caseNo);
  if (draft.status === 'apply_pending') {
    throw new Error('正在套用重開中，請勿重複提交');
  }

  if (!draft.previewView) {
    const err = new OrderMutationValidationError({
      code: 'missing_preview',
      message: '請先完成重開預覽後再進行確認',
    });
    orderMutationFlowStore.setReopenTypedError(caseNo, err);
    throw err;
  }

  const trimmedReason = draft.reason.trim();
  if (trimmedReason.length < 1 || trimmedReason.length > 500) {
    const err = new OrderMutationValidationError({
      code: 'invalid_reason',
      message: '重開原因必須為 1 至 500 字元且不可為純空白',
    });
    orderMutationFlowStore.setReopenTypedError(caseNo, err);
    throw err;
  }

  orderMutationFlowStore.setReopenApplyPending(caseNo);

  let receipt: OrderReopenReceiptView;
  try {
    receipt = await ordersMutationClient.applyReopen(
      caseNo,
      {
        expected_order_version: draft.previewView.order_version,
        expected_client_finance_version: draft.previewView.client_finance_version,
        expected_payroll_version: draft.previewView.payroll_version,
        preview_fingerprint: draft.previewView.preview_fingerprint,
        reason: draft.reason,
      },
      {
        ...options,
        idempotencyKey: draft.idempotencyKey,
      }
    );

  } catch (err) {
    const error = normalizeFlowError(err, caseNo);
    if (isOutcomeUnknownError(error)) {
      orderMutationFlowStore.setReopenOutcomeUnknown(caseNo, error);
    } else if (isStaleConflictError(error)) {
      orderMutationFlowStore.setReopenStale(caseNo, error);
    } else {
      orderMutationFlowStore.setReopenTypedError(caseNo, error);
    }
    throw err;
  }

  if (receipt.preview_fingerprint !== draft.previewView.preview_fingerprint) {
    const mismatchErr = new OrderMutationConflictError({
      code: 'fingerprint_mismatch',
      message: '伺服器已回傳重開 receipt，但指紋與預覽不一致；已停止後續觀察並要求人工處理。',
      status: 409,
    });
    orderMutationFlowStore.setReopenReceiptReceived(caseNo, receipt);
    orderMutationFlowStore.setReopenObservationFailed(caseNo, mismatchErr);
    throw mismatchErr;
  }


  orderMutationFlowStore.setReopenReceiptReceived(caseNo, receipt);
  orderMutationFlowStore.setReopenRequeryLoading(caseNo);
  try {
    if (onRequery) {
      await onRequery();
    }
    orderMutationFlowStore.setReopenObserved(caseNo);
    return receipt;
  } catch (err) {
    orderMutationFlowStore.setReopenObservationFailed(
      caseNo,
      normalizeFlowError(err, caseNo)
    );
    throw err;
  }
}

export async function retryReopenApplyFlow(
  caseNo: string,
  onRequery?: () => Promise<void>,
  options?: OrderMutationRequestOptions
): Promise<OrderReopenReceiptView> {
  const draft = orderMutationFlowStore.getOrCreateReopenDraft(caseNo);
  if (draft.status !== 'outcome_unknown') {
    throw new Error('僅能在狀態未明 (outcome_unknown) 時進行重試');
  }
  return applyReopenFlow(caseNo, onRequery, options);
}

export async function retryReopenObservationFlow(
  caseNo: string,
  onRequery?: () => Promise<void>
): Promise<void> {
  const draft = orderMutationFlowStore.getOrCreateReopenDraft(caseNo);
  if (draft.status !== 'observation_failed' || !draft.receiptView) {
    throw new Error('僅能在 receipt 已收到但重新查詢失敗時重試觀察');
  }
  orderMutationFlowStore.setReopenRequeryLoading(caseNo);
  try {
    if (onRequery) {
      await onRequery();
    }
    orderMutationFlowStore.setReopenObserved(caseNo);
  } catch (err) {
    orderMutationFlowStore.setReopenObservationFailed(
      caseNo,
      normalizeFlowError(err, caseNo)
    );
    throw err;
  }
}

export function closeReopenDialog(caseNo: string): void {
  orderMutationFlowStore.closeReopenDialog(caseNo);
}
