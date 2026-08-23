/**
 * File: leave_substitution_flow_adapter.ts
 * Description: 協調請假代班 Query、Preview、Apply、receipt 與 re-query，保留 typed 失敗邊界。
 */
import {
  leaveSubstitutionClient,
  type LeaveSubstitutionClient,
  type LeaveSubstitutionRequestOptions,
} from '../../api/scheduling/leave_substitution_client';
import {
  LeaveSubstitutionAbortedError,
  LeaveSubstitutionContractError,
  LeaveSubstitutionError,
  LeaveSubstitutionValidationError,
  mapLeaveSubstitutionError,
} from '../../api/scheduling/leave_substitution_errors';
import {
  LeaveSubstitutionPreviewRequestSchema,
  type LeaveSubstitutionApplyRequest,
  type LeaveSubstitutionAssignment,
  type LeaveSubstitutionPreview,
  type LeaveSubstitutionPreviewRequest,
  type LeaveSubstitutionReceipt,
} from '../../api/scheduling/leave_substitution_schemas';
import {
  leaveSubstitutionFlowStore,
  type LeaveSubstitutionFlowDraft,
} from './leave_substitution_flow_store';

export type LeaveSubstitutionMachineState =
  | { type: 'idle'; caseNo?: string }
  | { type: 'query_loading'; caseNo: string }
  | { type: 'query_ready'; caseNo: string; assignments: readonly LeaveSubstitutionAssignment[]; previewRequest: LeaveSubstitutionPreviewRequest | null }
  | { type: 'preview_loading'; caseNo: string; previewRequest: LeaveSubstitutionPreviewRequest }
  | { type: 'preview_ready'; caseNo: string; previewRequest: LeaveSubstitutionPreviewRequest; preview: LeaveSubstitutionPreview }
  | { type: 'apply_pending'; caseNo: string; preview: LeaveSubstitutionPreview; applyRequest: LeaveSubstitutionApplyRequest; idempotencyKey: string }
  | { type: 'receipt_received'; caseNo: string; receipt: LeaveSubstitutionReceipt }
  | { type: 'requery_loading'; caseNo: string; receipt: LeaveSubstitutionReceipt }
  | { type: 'observed'; caseNo: string; assignments: readonly LeaveSubstitutionAssignment[]; receipt: LeaveSubstitutionReceipt }
  | { type: 'typed_error'; caseNo: string; error: LeaveSubstitutionError }
  | { type: 'stale'; caseNo: string; error: LeaveSubstitutionError; requiresFreshPreview: true }
  | { type: 'outcome_unknown'; caseNo: string; preview: LeaveSubstitutionPreview; applyRequest: LeaveSubstitutionApplyRequest; idempotencyKey: string; error: LeaveSubstitutionError }
  | { type: 'observation_failed'; caseNo: string; receipt: LeaveSubstitutionReceipt; error: LeaveSubstitutionError };

export interface LeaveSubstitutionFlowOptions extends LeaveSubstitutionRequestOptions {
  readonly client?: LeaveSubstitutionClient;
}

const inFlightApplyByCase = new Map<string, Promise<LeaveSubstitutionReceipt>>();

function clientOf(options?: LeaveSubstitutionFlowOptions): LeaveSubstitutionClient {
  return options?.client ?? leaveSubstitutionClient;
}

function requestOptionsOf(
  options?: LeaveSubstitutionFlowOptions,
): LeaveSubstitutionRequestOptions | undefined {
  if (!options) return undefined;
  const { client: _client, ...requestOptions } = options;
  return requestOptions;
}

function stableValue(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableValue).join(',')}]`;
  return `{${Object.keys(value as Record<string, unknown>).sort().map((key) => `${JSON.stringify(key)}:${stableValue((value as Record<string, unknown>)[key])}`).join(',')}}`;
}

function sameValue(left: unknown, right: unknown): boolean {
  return stableValue(left) === stableValue(right);
}

function normalize(error: unknown): LeaveSubstitutionError {
  return error instanceof LeaveSubstitutionError ? error : mapLeaveSubstitutionError(error);
}

function errorCode(error: LeaveSubstitutionError): string {
  return `${error.publicCode ?? ''} ${error.code}`.toLowerCase();
}

function isStale(error: LeaveSubstitutionError): boolean {
  const code = errorCode(error);
  return (
    (error.status === 409 && (code.includes('stale') || code.includes('version') || code.includes('generation'))) ||
    code.includes('scheduling_lock_set_stale')
  );
}

function isOutcomeUnknown(error: LeaveSubstitutionError): boolean {
  if (error instanceof LeaveSubstitutionAbortedError || error.code === 'LEAVE_SUBSTITUTION_ABORTED') return false;
  if (error.status === 503) return true;
  return error.code === 'LEAVE_SUBSTITUTION_TIMEOUT' || error.code === 'LEAVE_SUBSTITUTION_NETWORK';
}

function requireDraft(caseNo: string): LeaveSubstitutionFlowDraft {
  const draft = leaveSubstitutionFlowStore.get(caseNo);
  if (!draft) throw new LeaveSubstitutionValidationError('請先建立請假代班查詢狀態。');
  return draft;
}

function requirePreview(draft: LeaveSubstitutionFlowDraft): LeaveSubstitutionPreview {
  if (!draft.preview) throw new LeaveSubstitutionValidationError('請先取得最新請假代班 Preview。');
  return draft.preview;
}

function requireAssignments(draft: LeaveSubstitutionFlowDraft): readonly LeaveSubstitutionAssignment[] {
  if (!draft.assignments) throw new LeaveSubstitutionValidationError('請先取得最新請假代班 assignments。');
  return draft.assignments;
}

function assertApplyMatchesPreview(
  draft: LeaveSubstitutionFlowDraft,
  request: LeaveSubstitutionApplyRequest,
): void {
  const preview = requirePreview(draft);
  if (request.preview_fingerprint !== preview.preview_fingerprint) {
    throw new LeaveSubstitutionValidationError('Apply payload 的 preview fingerprint 已失效。');
  }
  if (request.expected_order_version !== preview.order_version || request.expected_scheduling_version !== preview.scheduling_version || request.expected_client_finance_version !== preview.client_finance_version || request.expected_payroll_version !== preview.payroll_version) {
    throw new LeaveSubstitutionValidationError('Apply payload 的 expected versions 必須來自最新 Preview。');
  }
  const {
    expected_order_version: _expectedOrderVersion,
    expected_scheduling_version: _expectedSchedulingVersion,
    expected_client_finance_version: _expectedClientFinanceVersion,
    expected_payroll_version: _expectedPayrollVersion,
    preview_fingerprint: _previewFingerprint,
    reason: _reason,
    ...previewIdentity
  } = request;
  if (!draft.previewRequest) {
    throw new LeaveSubstitutionValidationError('Apply payload identity 與 Preview request 不一致。');
  }
  const normalizedApplyIdentity = LeaveSubstitutionPreviewRequestSchema.safeParse(previewIdentity);
  const normalizedPreviewRequest = LeaveSubstitutionPreviewRequestSchema.safeParse(draft.previewRequest);
  if (
    !normalizedApplyIdentity.success ||
    !normalizedPreviewRequest.success ||
    !sameValue(normalizedApplyIdentity.data, normalizedPreviewRequest.data)
  ) {
    throw new LeaveSubstitutionValidationError('Apply payload identity 與 Preview request 不一致。');
  }
}

function assertReceiptObserved(
  draft: LeaveSubstitutionFlowDraft,
  assignments: readonly LeaveSubstitutionAssignment[],
): void {
  const receipt = draft.receipt;
  const request = draft.applyRequest;
  if (!receipt || !request) {
    throw new LeaveSubstitutionContractError('請假代班 receipt 觀察缺少 Apply identity。');
  }
  if (receipt.scheduling_version <= request.expected_scheduling_version) {
    throw new LeaveSubstitutionContractError('請假代班 receipt 未證明 scheduling version 已前進。');
  }
  if (assignments.some((assignment) => assignment.assignment_id === request.original_assignment_id)) {
    throw new LeaveSubstitutionContractError('請假代班 re-query 仍包含已取消的原始指派。');
  }
  const remainingScheduleIds = new Set(
    assignments.flatMap((assignment) => assignment.official_schedules.map((schedule) => schedule.schedule_id)),
  );
  if (request.items.some((item) => remainingScheduleIds.has(item.original_schedule_id))) {
    throw new LeaveSubstitutionContractError('請假代班 re-query 仍包含已取消的原始服務日。');
  }
  const observedStaffIds = new Set(assignments.map((assignment) => assignment.staff_id));
  if (
    request.items.some(
      (item) => item.resolution_type === 'substitute' &&
        (item.substitute_staff_id === null || !observedStaffIds.has(item.substitute_staff_id)),
    )
  ) {
    throw new LeaveSubstitutionContractError('請假代班 re-query 尚未觀察到核准的代班人員指派。');
  }
}

function requireMachineField<T>(value: T | null, message: string): T {
  if (value === null) throw new LeaveSubstitutionContractError(message);
  return value;
}

export function resolveLeaveSubstitutionMachineState(
  draft: LeaveSubstitutionFlowDraft | undefined,
): LeaveSubstitutionMachineState {
  if (!draft) return { type: 'idle' };
  switch (draft.status) {
    case 'idle': return { type: 'idle', caseNo: draft.caseNo };
    case 'query_loading': return { type: 'query_loading', caseNo: draft.caseNo };
    case 'query_ready': return { type: 'query_ready', caseNo: draft.caseNo, assignments: requireAssignments(draft), previewRequest: draft.previewRequest };
    case 'preview_loading': return { type: 'preview_loading', caseNo: draft.caseNo, previewRequest: requireMachineField(draft.previewRequest, '請假代班 Preview loading 缺少 request。') };
    case 'preview_ready': return { type: 'preview_ready', caseNo: draft.caseNo, previewRequest: requireMachineField(draft.previewRequest, '請假代班 Preview ready 缺少 request。'), preview: requirePreview(draft) };
    case 'apply_pending': return { type: 'apply_pending', caseNo: draft.caseNo, preview: requirePreview(draft), applyRequest: requireMachineField(draft.applyRequest, '請假代班 Apply pending 缺少 request。'), idempotencyKey: draft.idempotencyKey };
    case 'receipt_received': return { type: 'receipt_received', caseNo: draft.caseNo, receipt: requireMachineField(draft.receipt, '請假代班 receipt state 缺少 receipt。') };
    case 'requery_loading': return { type: 'requery_loading', caseNo: draft.caseNo, receipt: requireMachineField(draft.receipt, '請假代班 re-query 缺少 receipt。') };
    case 'observed': return { type: 'observed', caseNo: draft.caseNo, assignments: requireAssignments(draft), receipt: requireMachineField(draft.receipt, '請假代班 observed state 缺少 receipt。') };
    case 'typed_error': return { type: 'typed_error', caseNo: draft.caseNo, error: draft.error ?? new LeaveSubstitutionContractError('請假代班 typed error 缺少錯誤內容。') };
    case 'stale': return { type: 'stale', caseNo: draft.caseNo, error: draft.error ?? new LeaveSubstitutionContractError('請假代班 Preview 已失效。'), requiresFreshPreview: true };
    case 'outcome_unknown': return { type: 'outcome_unknown', caseNo: draft.caseNo, preview: requirePreview(draft), applyRequest: requireMachineField(draft.applyRequest, '請假代班 outcome unknown 缺少 request。'), idempotencyKey: draft.idempotencyKey, error: draft.error ?? new LeaveSubstitutionContractError('請假代班 Apply 結果未明。') };
    case 'observation_failed': return { type: 'observation_failed', caseNo: draft.caseNo, receipt: requireMachineField(draft.receipt, '請假代班 observation failure 缺少 receipt。'), error: draft.error ?? new LeaveSubstitutionContractError('請假代班 receipt 觀察失敗。') };
  }
}

export function setLeaveSubstitutionDraft(caseNo: string, request: LeaveSubstitutionPreviewRequest): LeaveSubstitutionFlowDraft {
  return leaveSubstitutionFlowStore.setDraft(caseNo, request);
}

export async function queryLeaveSubstitutionFlow(caseNo: string, options?: LeaveSubstitutionFlowOptions): Promise<readonly LeaveSubstitutionAssignment[]> {
  const client = clientOf(options);
  leaveSubstitutionFlowStore.setQueryLoading(caseNo);
  try {
    const assignments = await client.listAssignments(caseNo, requestOptionsOf(options));
    leaveSubstitutionFlowStore.setQueryReady(caseNo, assignments);
    return assignments;
  } catch (error) {
    const typed = normalize(error);
    leaveSubstitutionFlowStore.setTypedError(caseNo, typed);
    throw typed;
  }
}

export async function previewLeaveSubstitutionFlow(caseNo: string, options?: LeaveSubstitutionFlowOptions): Promise<LeaveSubstitutionPreview> {
  const draft = requireDraft(caseNo);
  const request = draft.previewRequest;
  if (!request) throw new LeaveSubstitutionValidationError('請先提供完整請假代班 request。');
  const assignments = requireAssignments(draft);
  if (assignments.length === 0) {
    throw new LeaveSubstitutionValidationError('此訂單沒有可建立 Preview 的正式服務指派。');
  }
  leaveSubstitutionFlowStore.setPreviewLoading(caseNo);
  try {
    const preview = await clientOf(options).preview(caseNo, request, {
      ...requestOptionsOf(options),
      correlationId: draft.correlationId,
    });
    leaveSubstitutionFlowStore.setPreviewReady(caseNo, preview);
    return preview;
  } catch (error) {
    const typed = normalize(error);
    if (isStale(typed)) leaveSubstitutionFlowStore.setStale(caseNo, typed);
    else leaveSubstitutionFlowStore.setTypedError(caseNo, typed);
    throw typed;
  }
}

async function requeryAfterReceipt(caseNo: string, options?: LeaveSubstitutionFlowOptions): Promise<readonly LeaveSubstitutionAssignment[]> {
  const draft = requireDraft(caseNo);
  const receipt = draft.receipt;
  if (!receipt) throw new LeaveSubstitutionContractError('收到的請假代班 receipt 不存在。');
  leaveSubstitutionFlowStore.setRequeryLoading(caseNo);
  try {
    const assignments = await clientOf(options).listAssignments(
      caseNo,
      requestOptionsOf(options),
    );
    assertReceiptObserved(draft, assignments);
    leaveSubstitutionFlowStore.setObserved(caseNo, assignments);
    return assignments;
  } catch (error) {
    const typed = normalize(error);
    leaveSubstitutionFlowStore.setObservationFailed(caseNo, typed);
    throw typed;
  }
}

export async function applyLeaveSubstitutionFlow(caseNo: string, request?: LeaveSubstitutionApplyRequest, options?: LeaveSubstitutionFlowOptions): Promise<LeaveSubstitutionReceipt> {
  const draft = requireDraft(caseNo);
  const existing = inFlightApplyByCase.get(caseNo);
  if (existing) {
    if (request && draft.applyRequest && !sameValue(draft.applyRequest, request)) {
      throw new LeaveSubstitutionValidationError('Apply 執行中不得更換 payload。');
    }
    return existing;
  }
  const preview = requirePreview(draft);
  const isRetry = draft.status === 'outcome_unknown';
  const applyRequest = request ?? draft.applyRequest;
  if (!applyRequest) throw new LeaveSubstitutionValidationError('請先提供完整請假代班 Apply payload。');
  if (isRetry && draft.applyRequest && !sameValue(draft.applyRequest, applyRequest)) {
    throw new LeaveSubstitutionValidationError('結果未明時只能以完全相同 payload 重試。');
  }
  try {
    assertApplyMatchesPreview(draft, applyRequest);
  } catch (error) {
    const typed = normalize(error);
    leaveSubstitutionFlowStore.setTypedError(caseNo, typed);
    throw typed;
  }
  const operation = (async () => {
    leaveSubstitutionFlowStore.setApplyPending(caseNo, applyRequest);
    try {
      const receipt = await clientOf(options).apply(caseNo, applyRequest, {
        ...requestOptionsOf(options),
        correlationId: draft.correlationId,
        idempotencyKey: draft.idempotencyKey,
      });
      if (receipt.case_no !== caseNo || receipt.preview_fingerprint !== preview.preview_fingerprint) {
        throw new LeaveSubstitutionContractError('請假代班 receipt 與 request／Preview identity 不一致。');
      }
      leaveSubstitutionFlowStore.setReceiptReceived(caseNo, receipt);
      await requeryAfterReceipt(caseNo, options);
      return receipt;
    } catch (error) {
      const typed = normalize(error);
      const current = leaveSubstitutionFlowStore.get(caseNo);
      if (current?.receipt) {
        leaveSubstitutionFlowStore.setObservationFailed(caseNo, typed);
      } else if (isStale(typed)) {
        leaveSubstitutionFlowStore.setStale(caseNo, typed);
      } else if (isOutcomeUnknown(typed)) {
        leaveSubstitutionFlowStore.setOutcomeUnknown(caseNo, typed);
      } else {
        leaveSubstitutionFlowStore.setTypedError(caseNo, typed);
      }
      throw typed;
    }
  })();
  inFlightApplyByCase.set(caseNo, operation);
  try {
    return await operation;
  } finally {
    if (inFlightApplyByCase.get(caseNo) === operation) inFlightApplyByCase.delete(caseNo);
  }
}

export async function retryLeaveSubstitutionApplyFlow(caseNo: string, options?: LeaveSubstitutionFlowOptions): Promise<LeaveSubstitutionReceipt> {
  const draft = requireDraft(caseNo);
  if (draft.status !== 'outcome_unknown' || !draft.applyRequest) throw new LeaveSubstitutionValidationError('只有結果未明的 Apply 可以重試。');
  return applyLeaveSubstitutionFlow(caseNo, draft.applyRequest, options);
}

export async function retryLeaveSubstitutionObservationFlow(caseNo: string, options?: LeaveSubstitutionFlowOptions): Promise<readonly LeaveSubstitutionAssignment[]> {
  const draft = requireDraft(caseNo);
  if (draft.status !== 'observation_failed' || !draft.receipt) throw new LeaveSubstitutionValidationError('只有 receipt 觀察失敗可以重試觀察。');
  return requeryAfterReceipt(caseNo, options);
}
