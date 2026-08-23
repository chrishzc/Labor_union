/**
 * File: leave_substitution_flow_store.ts
 * Description: 保存請假代班 typed flow 狀態，鎖定重試 payload 並保留 receipt 觀察結果。
 */
import type {
  LeaveSubstitutionApplyRequest,
  LeaveSubstitutionAssignment,
  LeaveSubstitutionPreview,
  LeaveSubstitutionPreviewRequest,
  LeaveSubstitutionReceipt,
} from '../../api/scheduling/leave_substitution_schemas';
import type { LeaveSubstitutionError } from '../../api/scheduling/leave_substitution_errors';

export type LeaveSubstitutionFlowStatus =
  | 'idle'
  | 'query_loading'
  | 'query_ready'
  | 'preview_loading'
  | 'preview_ready'
  | 'apply_pending'
  | 'receipt_received'
  | 'requery_loading'
  | 'observed'
  | 'typed_error'
  | 'stale'
  | 'outcome_unknown'
  | 'observation_failed';

export interface LeaveSubstitutionFlowDraft {
  readonly caseNo: string;
  readonly assignments: readonly LeaveSubstitutionAssignment[] | null;
  readonly previewRequest: LeaveSubstitutionPreviewRequest | null;
  readonly preview: LeaveSubstitutionPreview | null;
  readonly applyRequest: LeaveSubstitutionApplyRequest | null;
  readonly idempotencyKey: string;
  readonly correlationId: string;
  readonly receipt: LeaveSubstitutionReceipt | null;
  readonly status: LeaveSubstitutionFlowStatus;
  readonly error: LeaveSubstitutionError | null;
}

type MutableDraft = {
  caseNo: string;
  assignments: readonly LeaveSubstitutionAssignment[] | null;
  previewRequest: LeaveSubstitutionPreviewRequest | null;
  preview: LeaveSubstitutionPreview | null;
  applyRequest: LeaveSubstitutionApplyRequest | null;
  idempotencyKey: string;
  correlationId: string;
  receipt: LeaveSubstitutionReceipt | null;
  status: LeaveSubstitutionFlowStatus;
  error: LeaveSubstitutionError | null;
};

function newIdempotencyKey(): string {
  if (typeof globalThis.crypto !== 'undefined') {
    if (typeof globalThis.crypto.randomUUID === 'function') {
      return globalThis.crypto.randomUUID();
    }
    if (typeof globalThis.crypto.getRandomValues === 'function') {
      const bytes = new Uint8Array(16);
      globalThis.crypto.getRandomValues(bytes);
      bytes[6] = (bytes[6] & 0x0f) | 0x40;
      bytes[8] = (bytes[8] & 0x3f) | 0x80;
      const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
      return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    }
  }
  return `leave-substitution-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
}

function newCorrelationId(): string {
  return `scheduling-leave-substitution-${newIdempotencyKey()}`;
}

function copyPreviewRequest(
  request: LeaveSubstitutionPreviewRequest,
): LeaveSubstitutionPreviewRequest {
  return { ...request, items: request.items.map((item) => ({ ...item })) };
}

function copyApplyRequest(
  request: LeaveSubstitutionApplyRequest,
): LeaveSubstitutionApplyRequest {
  return { ...request, items: request.items.map((item) => ({ ...item })) };
}

function copyAssignments(
  assignments: readonly LeaveSubstitutionAssignment[],
): LeaveSubstitutionAssignment[] {
  return assignments.map((assignment) => ({ ...assignment }));
}

export class LeaveSubstitutionFlowStore {
  private readonly drafts = new Map<string, MutableDraft>();
  private readonly listeners = new Set<() => void>();

  public subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    for (const listener of this.listeners) {
      listener();
    }
  }

  public get(caseNo: string): LeaveSubstitutionFlowDraft | undefined {
    return this.drafts.get(caseNo);
  }

  private getOrCreate(caseNo: string): MutableDraft {
    const existing = this.drafts.get(caseNo);
    if (existing) return existing;
    const draft: MutableDraft = {
      caseNo,
      assignments: null,
      previewRequest: null,
      preview: null,
      applyRequest: null,
      idempotencyKey: newIdempotencyKey(),
      correlationId: newCorrelationId(),
      receipt: null,
      status: 'idle',
      error: null,
    };
    this.drafts.set(caseNo, draft);
    return draft;
  }

  public setQueryLoading(caseNo: string): LeaveSubstitutionFlowDraft {
    const draft = this.getOrCreate(caseNo);
    draft.assignments = null;
    draft.previewRequest = null;
    draft.preview = null;
    draft.applyRequest = null;
    draft.receipt = null;
    draft.idempotencyKey = newIdempotencyKey();
    draft.status = 'query_loading';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setQueryReady(
    caseNo: string,
    assignments: readonly LeaveSubstitutionAssignment[],
  ): LeaveSubstitutionFlowDraft {
    const draft = this.getOrCreate(caseNo);
    draft.assignments = copyAssignments(assignments);
    draft.status = 'query_ready';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setDraft(
    caseNo: string,
    request: LeaveSubstitutionPreviewRequest,
  ): LeaveSubstitutionFlowDraft {
    const draft = this.getOrCreate(caseNo);
    if (
      draft.status === 'apply_pending' ||
      draft.status === 'outcome_unknown' ||
      draft.status === 'receipt_received' ||
      draft.status === 'requery_loading' ||
      draft.status === 'observation_failed'
    ) {
      return draft;
    }
    draft.previewRequest = copyPreviewRequest(request);
    draft.preview = null;
    draft.applyRequest = null;
    draft.receipt = null;
    draft.idempotencyKey = newIdempotencyKey();
    draft.status = draft.assignments ? 'query_ready' : 'idle';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setPreviewLoading(caseNo: string): LeaveSubstitutionFlowDraft {
    const draft = this.getOrCreate(caseNo);
    draft.status = 'preview_loading';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setPreviewReady(
    caseNo: string,
    preview: LeaveSubstitutionPreview,
  ): LeaveSubstitutionFlowDraft {
    const draft = this.getOrCreate(caseNo);
    draft.preview = preview;
    draft.status = 'preview_ready';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setApplyPending(
    caseNo: string,
    request: LeaveSubstitutionApplyRequest,
  ): LeaveSubstitutionFlowDraft {
    const draft = this.getOrCreate(caseNo);
    draft.applyRequest = copyApplyRequest(request);
    draft.status = 'apply_pending';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setReceiptReceived(
    caseNo: string,
    receipt: LeaveSubstitutionReceipt,
  ): LeaveSubstitutionFlowDraft {
    const draft = this.getOrCreate(caseNo);
    draft.receipt = receipt;
    draft.status = 'receipt_received';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setRequeryLoading(caseNo: string): LeaveSubstitutionFlowDraft {
    const draft = this.getOrCreate(caseNo);
    draft.status = 'requery_loading';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setObserved(
    caseNo: string,
    assignments: readonly LeaveSubstitutionAssignment[],
  ): LeaveSubstitutionFlowDraft {
    const draft = this.getOrCreate(caseNo);
    draft.assignments = copyAssignments(assignments);
    draft.status = 'observed';
    draft.error = null;
    this.notify();
    return draft;
  }

  public setTypedError(
    caseNo: string,
    error: LeaveSubstitutionError,
  ): LeaveSubstitutionFlowDraft {
    const draft = this.getOrCreate(caseNo);
    draft.status = 'typed_error';
    draft.error = error;
    this.notify();
    return draft;
  }

  public setStale(
    caseNo: string,
    error: LeaveSubstitutionError,
  ): LeaveSubstitutionFlowDraft {
    const draft = this.getOrCreate(caseNo);
    draft.preview = null;
    draft.applyRequest = null;
    draft.status = 'stale';
    draft.error = error;
    this.notify();
    return draft;
  }

  public setOutcomeUnknown(
    caseNo: string,
    error: LeaveSubstitutionError,
  ): LeaveSubstitutionFlowDraft {
    const draft = this.getOrCreate(caseNo);
    draft.status = 'outcome_unknown';
    draft.error = error;
    this.notify();
    return draft;
  }

  public setObservationFailed(
    caseNo: string,
    error: LeaveSubstitutionError,
  ): LeaveSubstitutionFlowDraft {
    const draft = this.getOrCreate(caseNo);
    draft.status = 'observation_failed';
    draft.error = error;
    this.notify();
    return draft;
  }

  public clear(caseNo: string): void {
    this.drafts.delete(caseNo);
    this.notify();
  }

  public clearAll(): void {
    this.drafts.clear();
    this.notify();
  }
}

export const leaveSubstitutionFlowStore = new LeaveSubstitutionFlowStore();
