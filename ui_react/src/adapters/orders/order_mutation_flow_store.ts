/**
 * File: order_mutation_flow_store.ts
 * Description: Orders 安全變更記憶體 Store，鎖定未決 payload，並區分 Apply 未明與 receipt 後觀察失敗。
 */
import type {
  ServiceDateConfirmationQueryView,
  ServiceDateConfirmationPreviewView,
  ServiceDateConfirmationReceiptView,
  OrderReopenPreviewView,
  OrderReopenReceiptView,
} from '../../api/orders/order_mutation_schemas';
import type { OrderMutationError, ApiError } from '../../api/orders/order_mutation_errors';

export type ServiceDatesFlowStatus =
  | 'idle'
  | 'query_loading'
  | 'query_ready'
  | 'draft_changed'
  | 'preview_loading'
  | 'preview_ready'
  | 'apply_pending'
  | 'receipt_received'
  | 'requery_loading'
  | 'observation_failed'
  | 'observed'
  | 'outcome_unknown'
  | 'stale'
  | 'typed_error';

export type ReopenFlowStatus =
  | 'closed'
  | 'preview_loading'
  | 'preview_ready'
  | 'apply_pending'
  | 'receipt_received'
  | 'requery_loading'
  | 'observation_failed'
  | 'observed'
  | 'outcome_unknown'
  | 'stale'
  | 'typed_error';

export interface ServiceDatesDraftState {
  caseNo: string;
  queryView: ServiceDateConfirmationQueryView | null;
  selectedDates: string[];
  reason: string;
  previewView: ServiceDateConfirmationPreviewView | null;
  idempotencyKey: string;
  receiptView: ServiceDateConfirmationReceiptView | null;
  outcomeUnknown: boolean;
  status: ServiceDatesFlowStatus;
  error: OrderMutationError | ApiError | null;
}

export interface ReopenDraftState {
  caseNo: string;
  reason: string;
  previewView: OrderReopenPreviewView | null;
  idempotencyKey: string;
  receiptView: OrderReopenReceiptView | null;
  outcomeUnknown: boolean;
  status: ReopenFlowStatus;
  error: OrderMutationError | ApiError | null;
}

export function generateIdempotencyKey(): string {
  if (typeof globalThis.crypto !== 'undefined' && typeof globalThis.crypto.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  // Fallback using crypto.getRandomValues if randomUUID is unavailable
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function areDateArraysEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const sortedA = [...a].sort();
  const sortedB = [...b].sort();
  return sortedA.every((val, idx) => val === sortedB[idx]);
}

export class OrderMutationFlowStore {
  private serviceDatesDrafts: Map<string, ServiceDatesDraftState> = new Map();
  private reopenDrafts: Map<string, ReopenDraftState> = new Map();
  private listeners: Set<() => void> = new Set();

  public subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notify(): void {
    this.listeners.forEach((listener) => {
      try {
        listener();
      } catch (err) {
        console.error('OrderMutationFlowStore listener error:', err);
      }
    });
  }

  // ==========================================================================
  // Service Dates State Management
  // ==========================================================================

  public getServiceDatesDraft(caseNo: string): ServiceDatesDraftState | undefined {
    return this.serviceDatesDrafts.get(caseNo);
  }

  public getOrCreateServiceDatesDraft(caseNo: string): ServiceDatesDraftState {
    const existing = this.serviceDatesDrafts.get(caseNo);
    if (existing) return existing;

    const initial: ServiceDatesDraftState = {
      caseNo,
      queryView: null,
      selectedDates: [],
      reason: '',
      previewView: null,
      idempotencyKey: generateIdempotencyKey(),
      receiptView: null,
      outcomeUnknown: false,
      status: 'idle',
      error: null,
    };
    this.serviceDatesDrafts.set(caseNo, initial);
    return initial;
  }

  public setServiceDatesQueryLoading(caseNo: string): ServiceDatesDraftState {
    const draft = this.getOrCreateServiceDatesDraft(caseNo);
    if (
      draft.status === 'observed' ||
      draft.status === 'receipt_received' ||
      draft.status === 'observation_failed' ||
      draft.status === 'stale'
    ) {
      draft.previewView = null;
      draft.receiptView = null;
      draft.reason = '';
      draft.idempotencyKey = generateIdempotencyKey();
    }
    draft.status = 'query_loading';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setServiceDatesQueryReady(
    caseNo: string,
    queryView: ServiceDateConfirmationQueryView
  ): ServiceDatesDraftState {
    const draft = this.getOrCreateServiceDatesDraft(caseNo);
    draft.queryView = queryView;
    // Default selection to current confirmed dates if any, or suggested dates
    if (draft.selectedDates.length === 0) {
      if (queryView.current_dates.length > 0) {
        draft.selectedDates = [...queryView.current_dates];
      } else if (queryView.suggested_dates.length > 0) {
        draft.selectedDates = [...queryView.suggested_dates];
      }
    }
    draft.status = 'query_ready';
    draft.error = null;
    this.notify();
    return draft;
  }

  public updateServiceDatesSelection(caseNo: string, dates: string[]): ServiceDatesDraftState {
    const draft = this.getOrCreateServiceDatesDraft(caseNo);
    if (
      draft.status === 'apply_pending' ||
      draft.status === 'outcome_unknown' ||
      draft.status === 'receipt_received' ||
      draft.status === 'requery_loading'
    ) {
      return draft;
    }
    const unchanged = areDateArraysEqual(draft.selectedDates, dates);
    if (!unchanged) {
      draft.selectedDates = [...dates];
      draft.previewView = null;
      draft.idempotencyKey = generateIdempotencyKey();
      draft.receiptView = null;
      draft.outcomeUnknown = false;
      draft.status = 'draft_changed';
      draft.error = null;
      this.notify();
    }
    return draft;
  }

  public updateServiceDatesReason(caseNo: string, reason: string): ServiceDatesDraftState {
    const draft = this.getOrCreateServiceDatesDraft(caseNo);
    if (
      draft.status === 'apply_pending' ||
      draft.status === 'outcome_unknown' ||
      draft.status === 'receipt_received' ||
      draft.status === 'requery_loading'
    ) {
      return draft;
    }
    draft.reason = reason;
    this.notify();
    return draft;
  }

  public setServiceDatesPreviewLoading(caseNo: string): ServiceDatesDraftState {
    const draft = this.getOrCreateServiceDatesDraft(caseNo);
    draft.status = 'preview_loading';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setServiceDatesPreviewReady(
    caseNo: string,
    previewView: ServiceDateConfirmationPreviewView
  ): ServiceDatesDraftState {
    const draft = this.getOrCreateServiceDatesDraft(caseNo);
    draft.previewView = previewView;
    draft.status = 'preview_ready';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setServiceDatesApplyPending(caseNo: string): ServiceDatesDraftState {
    const draft = this.getOrCreateServiceDatesDraft(caseNo);
    draft.status = 'apply_pending';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setServiceDatesReceiptReceived(
    caseNo: string,
    receiptView: ServiceDateConfirmationReceiptView
  ): ServiceDatesDraftState {
    const draft = this.getOrCreateServiceDatesDraft(caseNo);
    draft.receiptView = receiptView;
    draft.status = 'receipt_received';
    draft.outcomeUnknown = false;
    draft.error = null;
    this.notify();
    return draft;
  }

  public setServiceDatesRequeryLoading(caseNo: string): ServiceDatesDraftState {
    const draft = this.getOrCreateServiceDatesDraft(caseNo);
    draft.status = 'requery_loading';
    this.notify();
    return draft;
  }

  public setServiceDatesObservationFailed(
    caseNo: string,
    error: OrderMutationError | ApiError
  ): ServiceDatesDraftState {
    const draft = this.getOrCreateServiceDatesDraft(caseNo);
    draft.status = 'observation_failed';
    draft.outcomeUnknown = false;
    draft.error = error;
    this.notify();
    return draft;
  }

  public setServiceDatesObserved(
    caseNo: string,
    queryView: ServiceDateConfirmationQueryView
  ): ServiceDatesDraftState {
    const draft = this.getOrCreateServiceDatesDraft(caseNo);
    draft.queryView = queryView;
    draft.selectedDates = [...queryView.current_dates];
    draft.previewView = null;
    draft.status = 'observed';
    draft.outcomeUnknown = false;
    draft.error = null;
    this.notify();
    return draft;
  }

  public setServiceDatesOutcomeUnknown(
    caseNo: string,
    error: OrderMutationError | ApiError
  ): ServiceDatesDraftState {
    const draft = this.getOrCreateServiceDatesDraft(caseNo);
    draft.outcomeUnknown = true;
    draft.status = 'outcome_unknown';
    draft.error = error;
    this.notify();
    return draft;
  }

  public setServiceDatesStale(caseNo: string, error: OrderMutationError | ApiError): ServiceDatesDraftState {
    const draft = this.getOrCreateServiceDatesDraft(caseNo);
    draft.previewView = null;
    draft.idempotencyKey = generateIdempotencyKey();
    draft.status = 'stale';
    draft.error = error;
    this.notify();
    return draft;
  }

  public setServiceDatesTypedError(
    caseNo: string,
    error: OrderMutationError | ApiError
  ): ServiceDatesDraftState {
    const draft = this.getOrCreateServiceDatesDraft(caseNo);
    draft.status = 'typed_error';
    draft.error = error;
    this.notify();
    return draft;
  }

  public resetServiceDatesDraft(caseNo: string): void {
    this.serviceDatesDrafts.delete(caseNo);
    this.notify();
  }

  // ==========================================================================
  // Controlled Reopen State Management
  // ==========================================================================

  public getReopenDraft(caseNo: string): ReopenDraftState | undefined {
    return this.reopenDrafts.get(caseNo);
  }

  public getOrCreateReopenDraft(caseNo: string): ReopenDraftState {
    const existing = this.reopenDrafts.get(caseNo);
    if (existing) return existing;

    const initial: ReopenDraftState = {
      caseNo,
      reason: '',
      previewView: null,
      idempotencyKey: generateIdempotencyKey(),
      receiptView: null,
      outcomeUnknown: false,
      status: 'closed',
      error: null,
    };
    this.reopenDrafts.set(caseNo, initial);
    return initial;
  }

  public updateReopenReason(caseNo: string, reason: string): ReopenDraftState {
    const draft = this.getOrCreateReopenDraft(caseNo);
    if (
      draft.status === 'apply_pending' ||
      draft.status === 'outcome_unknown' ||
      draft.status === 'receipt_received' ||
      draft.status === 'requery_loading'
    ) {
      return draft;
    }
    draft.reason = reason;
    this.notify();
    return draft;
  }

  public setReopenPreviewLoading(caseNo: string): ReopenDraftState {
    const draft = this.getOrCreateReopenDraft(caseNo);
    draft.previewView = null;
    draft.receiptView = null;
    draft.reason = '';
    draft.idempotencyKey = generateIdempotencyKey();
    draft.status = 'preview_loading';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setReopenPreviewReady(
    caseNo: string,
    previewView: OrderReopenPreviewView
  ): ReopenDraftState {
    const draft = this.getOrCreateReopenDraft(caseNo);
    draft.previewView = previewView;
    draft.status = 'preview_ready';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setReopenApplyPending(caseNo: string): ReopenDraftState {
    const draft = this.getOrCreateReopenDraft(caseNo);
    draft.status = 'apply_pending';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setReopenReceiptReceived(
    caseNo: string,
    receiptView: OrderReopenReceiptView
  ): ReopenDraftState {
    const draft = this.getOrCreateReopenDraft(caseNo);
    draft.receiptView = receiptView;
    draft.status = 'receipt_received';
    draft.outcomeUnknown = false;
    draft.error = null;
    this.notify();
    return draft;
  }

  public setReopenRequeryLoading(caseNo: string): ReopenDraftState {
    const draft = this.getOrCreateReopenDraft(caseNo);
    draft.status = 'requery_loading';
    this.notify();
    return draft;
  }

  public setReopenObservationFailed(
    caseNo: string,
    error: OrderMutationError | ApiError
  ): ReopenDraftState {
    const draft = this.getOrCreateReopenDraft(caseNo);
    draft.status = 'observation_failed';
    draft.outcomeUnknown = false;
    draft.error = error;
    this.notify();
    return draft;
  }

  public setReopenObserved(caseNo: string): ReopenDraftState {
    const draft = this.getOrCreateReopenDraft(caseNo);
    draft.status = 'observed';
    draft.previewView = null;
    draft.outcomeUnknown = false;
    draft.error = null;
    this.notify();
    return draft;
  }

  public setReopenOutcomeUnknown(
    caseNo: string,
    error: OrderMutationError | ApiError
  ): ReopenDraftState {
    const draft = this.getOrCreateReopenDraft(caseNo);
    draft.outcomeUnknown = true;
    draft.status = 'outcome_unknown';
    draft.error = error;
    this.notify();
    return draft;
  }

  public setReopenStale(caseNo: string, error: OrderMutationError | ApiError): ReopenDraftState {
    const draft = this.getOrCreateReopenDraft(caseNo);
    draft.previewView = null;
    draft.idempotencyKey = generateIdempotencyKey();
    draft.status = 'stale';
    draft.error = error;
    this.notify();
    return draft;
  }

  public setReopenTypedError(caseNo: string, error: OrderMutationError | ApiError): ReopenDraftState {
    const draft = this.getOrCreateReopenDraft(caseNo);
    draft.status = 'typed_error';
    draft.error = error;
    this.notify();
    return draft;
  }

  public closeReopenDialog(caseNo: string): ReopenDraftState {
    const draft = this.getOrCreateReopenDraft(caseNo);
    // If not in outcome_unknown or in progress, close
    if (draft.status !== 'outcome_unknown' && draft.status !== 'apply_pending') {
      draft.status = 'closed';
      this.notify();
    }
    return draft;
  }

  public resetReopenDraft(caseNo: string): void {
    this.reopenDrafts.delete(caseNo);
    this.notify();
  }

  public clearAll(): void {
    this.serviceDatesDrafts.clear();
    this.reopenDrafts.clear();
    this.notify();
  }
}

export const orderMutationFlowStore = new OrderMutationFlowStore();
