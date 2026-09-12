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
import type { OrderServiceCompletionPreview, OrderServiceCompletionReceipt } from '../../api/orders/order_service_completion_client';
import type { ActualStartApplyPayload, ActualStartReceipt } from '../../api/orders/order_actual_start_client';
import type {
  AddCandidatesResult,
  CandidateAddCommand,
  CandidateInformationSendCommand,
  CandidateWillingnessResult,
  SendCandidateInformationResult,
} from '../../api/scheduling/candidate_contact_pool_client';
import type {
  AssignmentPlanCommandIdentity,
  AssignmentPlanJob,
  AssignmentPlanPreview,
  AssignmentPlanSegmentInput,
} from '../../api/scheduling/assignment_plan_mutation_client';
import type {
  IntakeClientNamePreview,
  IntakeClientNameReceipt,
  IntakeCompletionPreview,
  IntakeCompletionReceipt,
  IntakeTermsPreview,
  IntakeTermsReceipt,
} from '../../api/orders/order_intake_completion_client';
import type {
  CaregiverWillingnessReceipt,
  CustomerDecisionReceipt,
} from '../../api/scheduling/matching_plan_communication_client';
import type { FormalMatchingPlan, MatchingPlanSegmentInput } from '../../api/scheduling/matching_candidate_workflow_client';
import type {
  HistoricalClientPaymentIntent,
  HistoricalClientPaymentPreview,
  HistoricalClientPaymentReceipt,
} from '../../api/client_finance/historical_client_payment_client';
import type {
  HistoricalStaffPayoutIntent,
  HistoricalStaffPayoutPreview,
  HistoricalStaffPayoutReceipt,
} from '../../api/staff_payables/historical_staff_payout_client';
import type { MatchingScheduleState, MatchingScheduleManualPreview, ScheduleCommandIdentity } from '../../api/scheduling/matching_schedule_confirmation_client';
import type { OrderMutationError, ApiError } from '../../api/orders/order_mutation_errors';
import type { OrderCancellationApplyPayload, OrderCancellationReceipt } from '../../api/orders/order_cancellation_client';
import type { ExternalSigningCommandIdentity, PreparedUnsignedDocument } from '../../api/orders/contract_external_signing_client';

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

export type ScheduleMutationCommand = {
  caseNo: string;
  planId: number;
  identity: ScheduleCommandIdentity;
} & (
  | { kind: 'send' }
  | { kind: 'manual'; preview: MatchingScheduleManualPreview; reason: string }
  | { kind: 'recipient'; recipientId: number; reason: string }
);

export interface ScheduleMutationFlowState {
  status: 'applying' | 'outcome_unknown' | 'observation_failed' | 'observing';
  command: ScheduleMutationCommand;
  receipt: MatchingScheduleState | null;
  error: string | null;
}

export interface CompletionCommand {
  preview: OrderServiceCompletionPreview;
  reason: string;
  key: string;
}

export interface CompletionFlowState {
  status: 'applying' | 'outcome_unknown' | 'observation_failed' | 'observing' | 'completed';
  command: CompletionCommand | null;
  receipt: OrderServiceCompletionReceipt | null;
  error: string | null;
}

export interface ActualStartCommand {
  payload: ActualStartApplyPayload;
  idempotencyKey: string;
}

export interface ActualStartFlowState {
  status: 'applying' | 'outcome_unknown' | 'observation_failed' | 'observing' | 'observed';
  command: ActualStartCommand;
  receipt: ActualStartReceipt | null;
  error: string | null;
}

export interface CancellationCommand {
  caseNo: string;
  payload: OrderCancellationApplyPayload;
  idempotencyKey: string;
  actor: string;
}

export interface CancellationFlowState {
  status: 'applying' | 'outcome_unknown' | 'observation_failed' | 'observing' | 'observed';
  command: CancellationCommand;
  receipt: OrderCancellationReceipt | null;
  error: string | null;
}

export interface CandidatePoolAddFlowState {
  status: 'applying' | 'outcome_unknown' | 'observation_failed' | 'observing' | 'observed';
  command: CandidateAddCommand;
  receipt: AddCandidatesResult | null;
  readbackStaff: readonly { staffId: number; staffName: string }[];
  error: string | null;
}

export interface CandidateInformationFlowState {
  status: 'applying' | 'outcome_unknown' | 'observation_failed' | 'observing';
  command: CandidateInformationSendCommand;
  receipt: SendCandidateInformationResult | null;
  error: string | null;
}

/** Keeps an uncertain manual candidate response tied to its original actor and event key. */
export interface CandidateWillingnessCommand {
  caseNo: string;
  candidateId: number;
  willingness: 'willing' | 'unwilling';
  reason: string;
  expectedActor: string;
  eventKey: string;
}

export interface CandidateWillingnessFlowState {
  status: 'applying' | 'outcome_unknown' | 'observation_failed' | 'observing';
  command: CandidateWillingnessCommand;
  receipt: CandidateWillingnessResult | null;
  error: string | null;
}

export type FormalManualResponseCommand =
  | {
    kind: 'willingness';
    caseNo: string;
    planId: number;
    segmentId: number;
    expectedVersion: number;
    reason: string;
    key: string;
    actor: string;
  }
  | {
    kind: 'customer_decision';
    caseNo: string;
    planId: number;
    expectedVersion: number;
    decision: 'accepted' | 'declined';
    reason: string;
    key: string;
    actor: string;
  };

export interface FormalManualResponseFlowState {
  status: 'applying' | 'outcome_unknown' | 'observation_failed' | 'observing';
  command: FormalManualResponseCommand;
  receipt: CaregiverWillingnessReceipt | CustomerDecisionReceipt | null;
  error: string | null;
}

export interface FormalPlanCreationCommand {
  caseNo: string;
  kind: 'single' | 'multi';
  actor: string;
  asOf: string;
  key: string;
  segments: MatchingPlanSegmentInput[];
}

/** Retains the immutable create identity through same-tab remount recovery. */
export interface FormalPlanCreationFlowState {
  status: 'applying' | 'outcome_unknown' | 'observation_failed' | 'observing';
  command: FormalPlanCreationCommand;
  receipt: FormalMatchingPlan | null;
  error: string | null;
  observationToken?: string;
}

/** Handoff recovery retains the original authenticated operator and full POST identity in memory per case. */
export interface ExternalSigningHandoffCommand {
  caseNo: string;
  sessionId: string;
  expectedStatusVersion: number;
  actor: string;
  identity: ExternalSigningCommandIdentity;
}

export interface ExternalSigningHandoffReceipt {
  session_id: string;
  resulting_status_version: number;
  replayed: boolean;
}

export interface ExternalSigningHandoffFlowState {
  status: 'applying' | 'outcome_unknown' | 'observation_failed' | 'observing';
  operationToken: number;
  command: ExternalSigningHandoffCommand;
  receipt: ExternalSigningHandoffReceipt | null;
  error: string | null;
}

/** Unsigned-PDF preparation keeps the exact original target and authenticated actor until its owner readback succeeds. */
export interface ExternalSigningUnsignedPreparationCommand {
  kind: 'client' | 'staff';
  caseNo: string;
  sessionId: string | null;
  segmentId: number | null;
  actor: string;
  identity: ExternalSigningCommandIdentity;
}

export interface ExternalSigningUnsignedPreparationFlowState {
  status: 'applying' | 'outcome_unknown' | 'observation_failed' | 'observing';
  operationToken: number;
  command: ExternalSigningUnsignedPreparationCommand;
  receipt: PreparedUnsignedDocument | null;
  error: string | null;
}

export interface HistoricalClientPaymentCommand {
  actor: string;
  intent: HistoricalClientPaymentIntent;
  preview: HistoricalClientPaymentPreview;
  reason: string;
  key: string;
}

export interface HistoricalClientPaymentFlowState {
  status: 'applying' | 'outcome_unknown' | 'observation_failed' | 'observing';
  command: HistoricalClientPaymentCommand;
  receipt: HistoricalClientPaymentReceipt | null;
  error: string | null;
}

export interface HistoricalStaffPayoutCommand {
  actor: string;
  intent: HistoricalStaffPayoutIntent;
  preview: HistoricalStaffPayoutPreview;
  reason: string;
  key: string;
}

export interface HistoricalStaffPayoutFlowState {
  status: 'applying' | 'outcome_unknown' | 'observation_failed' | 'observing';
  command: HistoricalStaffPayoutCommand;
  receipt: HistoricalStaffPayoutReceipt | null;
  error: string | null;
}

export interface AssignmentPlanApplyCommand {
  caseNo: string;
  planId: number;
  segments: AssignmentPlanSegmentInput[];
  preview: AssignmentPlanPreview;
  reason: string;
  identity: AssignmentPlanCommandIdentity;
}

export interface AssignmentPlanFlowState {
  status: 'applying' | 'outcome_unknown' | 'receipt_received' | 'observing' | 'observation_failed' | 'observed';
  command: AssignmentPlanApplyCommand;
  acceptedJob: { job_id: string; status_url: string } | null;
  job: AssignmentPlanJob | null;
  readbackStatus: 'not_started' | 'observing' | 'failed' | 'observed';
  error: string | null;
}

export type IntakeRepairOperation = 'client_name' | 'terms' | 'completion';

export type IntakeRepairCommand =
  | {
    operation: 'client_name';
    preview: IntakeClientNamePreview;
    reason: string;
    idempotencyKey: string;
  }
  | {
    operation: 'terms';
    preview: IntakeTermsPreview;
    reason: string;
    idempotencyKey: string;
  }
  | {
    operation: 'completion';
    preview: IntakeCompletionPreview;
    reason: string;
    idempotencyKey: string;
  };

export type IntakeRepairReceipt = IntakeClientNameReceipt | IntakeTermsReceipt | IntakeCompletionReceipt;

export interface IntakeRepairFlowState {
  status: 'applying' | 'outcome_unknown' | 'observation_failed' | 'observing' | 'observed';
  command: IntakeRepairCommand;
  receipt: IntakeRepairReceipt | null;
  error: string | null;
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
  private completions = new Map<string, CompletionFlowState>();
  private actualStarts = new Map<string, ActualStartFlowState>();
  private cancellations = new Map<string, CancellationFlowState>();
  private candidatePoolAdds = new Map<string, CandidatePoolAddFlowState>();
  private candidateInformation = new Map<string, CandidateInformationFlowState>();
  private candidateWillingness = new Map<string, CandidateWillingnessFlowState>();
  private formalManualResponses = new Map<string, FormalManualResponseFlowState>();
  private formalPlanCreations = new Map<string, FormalPlanCreationFlowState>();
  private externalSigningHandoffs = new Map<string, ExternalSigningHandoffFlowState>();
  private externalSigningUnsignedPreparations = new Map<string, ExternalSigningUnsignedPreparationFlowState>();
  private historicalClientPayments = new Map<string, HistoricalClientPaymentFlowState>();
  private historicalStaffPayouts = new Map<string, HistoricalStaffPayoutFlowState>();
  private scheduleMutations = new Map<string, ScheduleMutationFlowState>();
  private assignmentPlans = new Map<string, AssignmentPlanFlowState>();
  private intakeRepairs = new Map<string, IntakeRepairFlowState>();
  private listeners: Set<() => void> = new Set();

  private intakeRepairKey(caseNo: string, operation: IntakeRepairOperation): string {
    return `${caseNo}:${operation}`;
  }

  private assignmentPlanKey(caseNo: string, planId: number): string {
    return `${caseNo}:${planId}`;
  }

  public getScheduleMutation(caseNo: string, planId: number): ScheduleMutationFlowState | undefined {
    return this.scheduleMutations.get(this.assignmentPlanKey(caseNo, planId));
  }

  public setScheduleMutation(caseNo: string, planId: number, state: ScheduleMutationFlowState): void {
    this.scheduleMutations.set(this.assignmentPlanKey(caseNo, planId), state);
    this.notify();
  }

  public clearScheduleMutation(caseNo: string, planId: number): void {
    this.scheduleMutations.delete(this.assignmentPlanKey(caseNo, planId));
    this.notify();
  }

  public getAssignmentPlan(caseNo: string, planId: number): AssignmentPlanFlowState | undefined {
    return this.assignmentPlans.get(this.assignmentPlanKey(caseNo, planId));
  }

  public setAssignmentPlan(caseNo: string, planId: number, state: AssignmentPlanFlowState): void {
    this.assignmentPlans.set(this.assignmentPlanKey(caseNo, planId), state);
    this.notify();
  }

  public clearAssignmentPlan(caseNo: string, planId: number): void {
    this.assignmentPlans.delete(this.assignmentPlanKey(caseNo, planId));
    this.notify();
  }

  public getIntakeRepair(
    caseNo: string,
    operation: IntakeRepairOperation,
  ): IntakeRepairFlowState | undefined {
    return this.intakeRepairs.get(this.intakeRepairKey(caseNo, operation));
  }

  public setIntakeRepair(caseNo: string, state: IntakeRepairFlowState): void {
    this.intakeRepairs.set(this.intakeRepairKey(caseNo, state.command.operation), state);
    this.notify();
  }

  public clearIntakeRepair(caseNo: string, operation: IntakeRepairOperation): void {
    this.intakeRepairs.delete(this.intakeRepairKey(caseNo, operation));
    this.notify();
  }

  public getCompletion(caseNo: string): CompletionFlowState | undefined {
    return this.completions.get(caseNo);
  }

  public setCompletion(caseNo: string, state: CompletionFlowState): void {
    this.completions.set(caseNo, state);
    this.notify();
  }

  public clearCompletion(caseNo: string): void {
    this.completions.delete(caseNo);
    this.notify();
  }

  public getActualStart(caseNo: string): ActualStartFlowState | undefined {
    return this.actualStarts.get(caseNo);
  }

  public setActualStart(caseNo: string, state: ActualStartFlowState): void {
    this.actualStarts.set(caseNo, state);
    this.notify();
  }

  public clearActualStart(caseNo: string): void {
    this.actualStarts.delete(caseNo);
    this.notify();
  }

  public getCancellation(caseNo: string): CancellationFlowState | undefined {
    return this.cancellations.get(caseNo);
  }

  public setCancellation(caseNo: string, state: CancellationFlowState): void {
    this.cancellations.set(caseNo, state);
    this.notify();
  }

  public clearCancellation(caseNo: string): void {
    this.cancellations.delete(caseNo);
    this.notify();
  }

  public getCandidatePoolAdd(caseNo: string): CandidatePoolAddFlowState | undefined {
    return this.candidatePoolAdds.get(caseNo);
  }

  public setCandidatePoolAdd(caseNo: string, state: CandidatePoolAddFlowState): void {
    this.candidatePoolAdds.set(caseNo, state);
    this.notify();
  }

  public clearCandidatePoolAdd(caseNo: string): void {
    this.candidatePoolAdds.delete(caseNo);
    this.notify();
  }

  private candidateInformationKey(caseNo: string, candidateId: number, infoType: 1 | 2): string {
    return `${caseNo}:${candidateId}:${infoType}`;
  }

  private candidateWillingnessKey(caseNo: string, candidateId: number): string {
    return `${caseNo}:${candidateId}`;
  }

  public getCandidateWillingness(
    caseNo: string,
    candidateId: number,
  ): CandidateWillingnessFlowState | undefined {
    return this.candidateWillingness.get(this.candidateWillingnessKey(caseNo, candidateId));
  }

  public setCandidateWillingness(caseNo: string, state: CandidateWillingnessFlowState): void {
    this.candidateWillingness.set(
      this.candidateWillingnessKey(caseNo, state.command.candidateId),
      state,
    );
    this.notify();
  }

  public clearCandidateWillingness(caseNo: string, candidateId: number): void {
    this.candidateWillingness.delete(this.candidateWillingnessKey(caseNo, candidateId));
    this.notify();
  }

  public getCandidateInformation(
    caseNo: string,
    candidateId: number,
    infoType: 1 | 2,
  ): CandidateInformationFlowState | undefined {
    return this.candidateInformation.get(this.candidateInformationKey(caseNo, candidateId, infoType));
  }

  public setCandidateInformation(caseNo: string, state: CandidateInformationFlowState): void {
    const { candidateId, infoType } = state.command;
    this.candidateInformation.set(this.candidateInformationKey(caseNo, candidateId, infoType), state);
    this.notify();
  }

  public clearCandidateInformation(caseNo: string, candidateId: number, infoType: 1 | 2): void {
    this.candidateInformation.delete(this.candidateInformationKey(caseNo, candidateId, infoType));
    this.notify();
  }

  public getCandidateInformationForCase(caseNo: string): CandidateInformationFlowState[] {
    return [...this.candidateInformation.values()].filter((state) => state.command.caseNo === caseNo);
  }

  public getFormalManualResponse(caseNo: string): FormalManualResponseFlowState | undefined {
    return this.formalManualResponses.get(caseNo);
  }

  public setFormalManualResponse(caseNo: string, state: FormalManualResponseFlowState): void {
    this.formalManualResponses.set(caseNo, state);
    this.notify();
  }

  public clearFormalManualResponse(caseNo: string): void {
    this.formalManualResponses.delete(caseNo);
    this.notify();
  }

  private formalPlanCreationKey(caseNo: string, kind: FormalPlanCreationCommand['kind']): string {
    return `${caseNo}:${kind}`;
  }

  public getFormalPlanCreation(
    caseNo: string,
    kind: FormalPlanCreationCommand['kind'],
  ): FormalPlanCreationFlowState | undefined {
    return this.formalPlanCreations.get(this.formalPlanCreationKey(caseNo, kind));
  }

  public setFormalPlanCreation(caseNo: string, state: FormalPlanCreationFlowState): void {
    this.formalPlanCreations.set(this.formalPlanCreationKey(caseNo, state.command.kind), state);
    this.notify();
  }

  public clearFormalPlanCreation(caseNo: string, kind: FormalPlanCreationCommand['kind']): void {
    this.formalPlanCreations.delete(this.formalPlanCreationKey(caseNo, kind));
    this.notify();
  }

  public getExternalSigningHandoff(caseNo: string): ExternalSigningHandoffFlowState | undefined {
    return this.externalSigningHandoffs.get(caseNo);
  }

  public setExternalSigningHandoff(caseNo: string, state: ExternalSigningHandoffFlowState): void {
    this.externalSigningHandoffs.set(caseNo, state);
    this.notify();
  }

  public clearExternalSigningHandoff(caseNo: string): void {
    this.externalSigningHandoffs.delete(caseNo);
    this.notify();
  }

  public getExternalSigningUnsignedPreparation(caseNo: string): ExternalSigningUnsignedPreparationFlowState | undefined {
    return this.externalSigningUnsignedPreparations.get(caseNo);
  }

  public setExternalSigningUnsignedPreparation(caseNo: string, state: ExternalSigningUnsignedPreparationFlowState): void {
    this.externalSigningUnsignedPreparations.set(caseNo, state);
    this.notify();
  }

  public clearExternalSigningUnsignedPreparation(caseNo: string): void {
    this.externalSigningUnsignedPreparations.delete(caseNo);
    this.notify();
  }

  public getHistoricalClientPayment(caseNo: string): HistoricalClientPaymentFlowState | undefined {
    return this.historicalClientPayments.get(caseNo);
  }

  public setHistoricalClientPayment(caseNo: string, state: HistoricalClientPaymentFlowState): void {
    this.historicalClientPayments.set(caseNo, state);
    this.notify();
  }

  public clearHistoricalClientPayment(caseNo: string): void {
    this.historicalClientPayments.delete(caseNo);
    this.notify();
  }

  private historicalStaffPayoutKey(caseNo: string, staffId: number): string {
    return `${caseNo}:${staffId}`;
  }

  public getHistoricalStaffPayout(caseNo: string, staffId: number): HistoricalStaffPayoutFlowState | undefined {
    return this.historicalStaffPayouts.get(this.historicalStaffPayoutKey(caseNo, staffId));
  }

  public setHistoricalStaffPayout(caseNo: string, staffId: number, state: HistoricalStaffPayoutFlowState): void {
    this.historicalStaffPayouts.set(this.historicalStaffPayoutKey(caseNo, staffId), state);
    this.notify();
  }

  public clearHistoricalStaffPayout(caseNo: string, staffId: number): void {
    this.historicalStaffPayouts.delete(this.historicalStaffPayoutKey(caseNo, staffId));
    this.notify();
  }

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
    this.completions.clear();
    this.actualStarts.clear();
    this.cancellations.clear();
    this.candidatePoolAdds.clear();
    this.candidateInformation.clear();
    this.candidateWillingness.clear();
    this.formalManualResponses.clear();
    this.formalPlanCreations.clear();
    this.externalSigningHandoffs.clear();
    this.externalSigningUnsignedPreparations.clear();
    this.historicalClientPayments.clear();
    this.historicalStaffPayouts.clear();
    this.scheduleMutations.clear();
    this.assignmentPlans.clear();
    this.intakeRepairs.clear();
    this.serviceDatesDrafts.clear();
    this.reopenDrafts.clear();
    this.notify();
  }
}

export const orderMutationFlowStore = new OrderMutationFlowStore();
