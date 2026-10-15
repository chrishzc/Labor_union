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
import { LeaveSubstitutionUnavailableError } from '../../api/scheduling/leave_substitution_errors';
import { sessionClient } from '../../api/auth/session_client';
import { z } from 'zod';
import {
  LeaveSubstitutionAssignmentSchema, LeaveSubstitutionPreviewRequestSchema,
  LeaveSubstitutionPreviewSchema, LeaveSubstitutionApplyRequestSchema,
} from '../../api/scheduling/leave_substitution_schemas';

const recoveryPrefix = 'union_leave_pending_v1:';
const RecoverySchema = z.strictObject({
  caseNo: z.string().min(1).max(50),
  assignments: z.array(LeaveSubstitutionAssignmentSchema),
  previewRequest: LeaveSubstitutionPreviewRequestSchema,
  preview: LeaveSubstitutionPreviewSchema,
  applyRequest: LeaveSubstitutionApplyRequestSchema,
  idempotencyKey: z.string().min(1).max(191),
  correlationId: z.string().min(1).max(191),
});
function draftKey(caseNo: string): string {
  const user = sessionClient.getUser();
  return `${recoveryPrefix}${encodeURIComponent(user?.username ?? '')}:${encodeURIComponent(caseNo)}`;
}
function forgetRecovery(caseNo: string): void {
  try { globalThis.localStorage?.removeItem(draftKey(caseNo)); } catch { /* Storage may be disabled. */ }
}

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
    const key = draftKey(caseNo);
    const existing = this.drafts.get(key);
    if (existing) return existing;
    if (!sessionClient.getUser()) return undefined;
    try {
      const raw = globalThis.localStorage?.getItem(key);
      if (!raw) return undefined;
      const saved = RecoverySchema.parse(JSON.parse(raw));
      if (saved.caseNo !== caseNo || saved.preview.case_no !== caseNo) return undefined;
      const draft: MutableDraft = { ...saved, receipt: null, status: 'outcome_unknown',
        error: new LeaveSubstitutionUnavailableError('上次代班儲存結果尚未確認。請按「再次確認變更結果」，以原操作查核；確認完成前不要重新建立代班。') };
      this.drafts.set(key, draft);
      return draft;
    } catch { return undefined; }
  }

  private getOrCreate(caseNo: string): MutableDraft {
    const existing = this.get(caseNo);
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
    this.drafts.set(draftKey(caseNo), draft);
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
    if (sessionClient.getUser()) {
      try {
        const { caseNo: savedCase, assignments, previewRequest, preview, applyRequest, idempotencyKey, correlationId } = draft;
        const saved = RecoverySchema.parse({ caseNo: savedCase, assignments, previewRequest, preview, applyRequest, idempotencyKey, correlationId });
        globalThis.localStorage?.setItem(draftKey(caseNo), JSON.stringify(saved));
      } catch { /* The in-page same-key recovery remains available. */ }
    }
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
    forgetRecovery(caseNo);
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
    forgetRecovery(caseNo);
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
    forgetRecovery(caseNo);
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
    this.drafts.delete(draftKey(caseNo));
    forgetRecovery(caseNo);
    this.notify();
  }

  public clearAll(): void {
    for (const draft of this.drafts.values()) forgetRecovery(draft.caseNo);
    this.drafts.clear();
    this.notify();
  }
}

export const leaveSubstitutionFlowStore = new LeaveSubstitutionFlowStore();
