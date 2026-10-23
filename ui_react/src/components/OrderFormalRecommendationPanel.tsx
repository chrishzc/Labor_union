import { useUnsavedDraft } from './UnsavedChanges';
import { useSaveValidation } from './useSaveValidation';
import { useStaffIdentityLabels } from './StaffIdentityProvider';
import { loadActiveStaffIds } from '../api/staff_directory/staff_directory_client';
import { useEffect, useRef, useState, useSyncExternalStore, type FC } from 'react';
import { candidateContactPoolClient, type CandidateContactPool } from '../api/scheduling/candidate_contact_pool_client';
import { matchingCandidateWorkflowClient, defaultMatchingFilterPolicy } from '../api/scheduling/matching_candidate_workflow_client';
import { matchingPlanCommunicationClient, type CustomerConfirmationPreview, type FormalPlanContactState } from '../api/scheduling/matching_plan_communication_client';
import { waitingDepositLockClient, type ActiveWaitingDepositPlan } from '../api/scheduling/waiting_deposit_lock_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { sessionClient } from '../api/auth/session_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { OrderMultiCaregiverPlanPanel } from './OrderMultiCaregiverPlanPanel';
import { CandidateInquiryDialog } from './CandidateInquiryDialog';
import { OrderRecommendationReplacementPanel } from './OrderRecommendationReplacementPanel';
import { compareStaffUnionNumbers, staffDisplayLabel } from '../adapters/staff/staff_directory_adapter';
import {
  orderMutationFlowStore,
  type FormalPlanCreationFlowState,
  type FormalManualResponseCommand,
  type FormalManualResponseFlowState,
} from '../adapters/orders/order_mutation_flow_store';

interface OrderFormalRecommendationPanelProps {
  caseNo: string;
  revision?: number;
  onObserved?: () => void;
  onOpenServiceDates?: () => void;
  onEditStateChange?: (state: { dirty: boolean; busy: boolean }) => void;
  initialCandidateId?: number;
  openReplacementRequest?: number;
  includeMultiCaregiver?: boolean;
  onOpenCandidates?: () => void;
  assignmentExists?: boolean;
}

type ReadState<T> =
  | { status: 'idle' | 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string };
type CurrentPlan = { plan: ActiveWaitingDepositPlan; contact: FormalPlanContactState };
type CandidateContact = CandidateContactPool['candidates'][number];
const subscribeFormalManualResponse = (listener: () => void) => orderMutationFlowStore.subscribe(listener);
const subscribeFormalPlanCreation = (listener: () => void) => orderMutationFlowStore.subscribe(listener);
const subscribeReplacement = (listener: () => void) => orderMutationFlowStore.subscribe(listener);

function hasExactPlanSegments(
  actual: CurrentPlan['plan']['segments'],
  expected: ReadonlyArray<{ staff_id: number; start_date: string; end_date: string }>,
): boolean {
  const ordered = [...(actual ?? [])].sort((left, right) => left.sequence - right.sequence);
  return ordered.length === expected.length && ordered.every((segment, index) => (
    segment.staffId === expected[index]?.staff_id
    && segment.assignedStartDate === expected[index]?.start_date
    && segment.assignedEndDate === expected[index]?.end_date
  ));
}

function hasExactPlanReceiptSegments(
  receiptSegments: ReadonlyArray<{ segment_order: number; staff_id: number; assigned_start_date: string; assigned_end_date: string }>,
  expected: ReadonlyArray<{ staff_id: number; start_date: string; end_date: string }>,
): boolean {
  const ordered = [...receiptSegments].sort((left, right) => left.segment_order - right.segment_order);
  return ordered.length === expected.length && ordered.every((segment, index) => (
    segment.staff_id === expected[index]?.staff_id
    && segment.assigned_start_date === expected[index]?.start_date
    && segment.assigned_end_date === expected[index]?.end_date
  ));
}

function profileStatusLabel(status: string | null): string {
  if (status === null) return '尚未寄送';
  if (status === 'pending') return '等待系統寄送';
  if (status === 'processing') return '寄送中';
  if (status === 'sent' || status === 'manually_confirmed') return '確認資訊已送達';
  if (status === 'retryable_failed') return '寄送暫時失敗';
  if (status === 'failed') return '寄送失敗';
  if (status === 'cancelled') return '寄送已取消';
  return status;
}

function decisionLabel(decision: FormalPlanContactState['customer_decision']): string {
  if (decision === 'accepted') return '客戶已接受';
  if (decision === 'declined') return '客戶已拒絕';
  if (decision === 'contact_requested') return '客戶希望進一步聯絡';
  return '等待客戶回覆';
}

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim() ? error.message.trim() : '正式媒合操作失敗';
}

function isDefinitivePlanRejection(error: unknown): boolean {
  return error instanceof ApiHttpError && error.status >= 400 && error.status < 500
    && error.status !== 408 && error.status !== 429 && !error.retryable;
}

/** The active-plan GET, not a create receipt held in component state, owns continuation. */
async function readCurrentPlan(caseNo: string, expectedPlanId?: number): Promise<CurrentPlan | null> {
  let plan: ActiveWaitingDepositPlan;
  try {
    plan = await waitingDepositLockClient.queryPlan(caseNo);
  } catch (error) {
    if (expectedPlanId === undefined && error instanceof ApiHttpError && error.status === 404) return null;
    throw error;
  }
  if (expectedPlanId !== undefined && plan.planId !== expectedPlanId) {
    throw new Error('目前有效方案已變更，請重新載入；不對其他方案執行操作。');
  }
  const contact = await matchingPlanCommunicationClient.queryContactState(caseNo, plan.planId);
  if (contact.plan.id !== plan.planId || contact.plan.case_no !== caseNo) {
    throw new Error('正式方案與聯繫狀態回讀不一致，請重新載入。');
  }
  return { plan, contact };
}

export const OrderFormalRecommendationPanel: FC<OrderFormalRecommendationPanelProps> = ({ caseNo, onObserved, onOpenServiceDates, revision = 0, onEditStateChange, initialCandidateId, includeMultiCaregiver = false, onOpenCandidates, openReplacementRequest = 0, assignmentExists = false }) => {
  const staffIdentity = useStaffIdentityLabels();
  const [candidates, setCandidates] = useState<ReadState<CandidateContactPool>>({ status: 'idle' });
  const [active, setActive] = useState<ReadState<CurrentPlan | null>>({ status: 'loading' });
  const [busy, setBusy] = useState(false);
  const [multiBusy, setMultiBusy] = useState(false);
  const [replacementState, setReplacementState] = useState({ dirty: false, busy: false });
  const [replacementOpen, setReplacementOpen] = useState(false);
  useEffect(() => { if (openReplacementRequest > 0) setReplacementOpen(true); }, [openReplacementRequest]);
  const [showManualDecision, setShowManualDecision] = useState(false);
  const [informationTab, setInformationTab] = useState<0 | 1 | 2 | null>(null);
  const [changingSegmentId, setChangingSegmentId] = useState<number | null>(null);
  const [willingnessChoice, setWillingnessChoice] = useState<'willing' | 'unwilling' | ''>('');
  const busyRef = useRef(false);
  const sequence = useRef(0);
  const activeCase = useRef<string | null>(null);
  const candidateQueryController = useRef<AbortController | null>(null);
  const [willingnessReason, setWillingnessReason] = useState('');
  const willingnessValidation = useSaveValidation();
  const willingnessChoiceRef = useRef<HTMLInputElement>(null);
  const willingnessReasonRef = useRef<HTMLTextAreaElement>(null);
  const decisionReasonRef = useRef<HTMLTextAreaElement>(null);
  const [decisionReason, setDecisionReason] = useState('');
  const [resumeNote, setResumeNote] = useState('請查收正式推薦月嫂的完整確認資訊。');
  const [confirmationPreview, setConfirmationPreview] = useState<ReadState<CustomerConfirmationPreview>>({ status: 'idle' });
  const [confirmationPreviewGeneration, setConfirmationPreviewGeneration] = useState(0);
  const confirmationActionIdentity = useRef<{ signature: string; key: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const formalManualResponse = useSyncExternalStore(
    subscribeFormalManualResponse,
    () => orderMutationFlowStore.getFormalManualResponse(caseNo),
  );
  const formalPlanCreation = useSyncExternalStore(
    subscribeFormalPlanCreation,
    () => orderMutationFlowStore.getFormalPlanCreation(caseNo, 'single'),
  );
  const replacementFlow = useSyncExternalStore(subscribeReplacement, () => orderMutationFlowStore.getRecommendationReplacement(caseNo));
  const replacementVisible = replacementOpen || replacementFlow !== undefined;
  const formalManualProtected = formalManualResponse?.status === 'applying'
    || formalManualResponse?.status === 'outcome_unknown'
    || formalManualResponse?.status === 'observation_failed'
    || formalManualResponse?.status === 'observing';
  const formalPlanCreationProtected = formalPlanCreation?.status === 'applying'
    || formalPlanCreation?.status === 'outcome_unknown'
    || formalPlanCreation?.status === 'observation_failed'
    || formalPlanCreation?.status === 'observing';
  const hasDraft = willingnessChoice !== '' || willingnessReason.trim().length > 0 || decisionReason.trim().length > 0
    || resumeNote !== '請查收正式推薦月嫂的完整確認資訊。';
  const protectedOperation = busy || formalManualProtected || formalPlanCreationProtected || replacementState.busy || replacementFlow !== undefined;
  useEffect(() => { onEditStateChange?.({ dirty: hasDraft || replacementState.dirty, busy: protectedOperation || multiBusy }); }, [hasDraft, replacementState.dirty, protectedOperation, multiBusy, onEditStateChange]);
  useEffect(() => () => { onEditStateChange?.({ dirty: false, busy: false }); }, [onEditStateChange]);

  useEffect(() => {
    const request = ++sequence.current;
    activeCase.current = caseNo;
    setActive({ status: 'loading' });
    setCandidates({ status: 'idle' });
    setWillingnessReason('');
    setWillingnessChoice('');
    setDecisionReason('');
    setResumeNote('請查收正式推薦月嫂的完整確認資訊。');
    setConfirmationPreview({ status: 'idle' });
    setConfirmationPreviewGeneration(0);
    confirmationActionIdentity.current = null;
    setError(null);
    setNotice(null);
    setReplacementOpen(openReplacementRequest > 0); setShowManualDecision(false); setInformationTab(null); setChangingSegmentId(null);
    void readCurrentPlan(caseNo)
      .then((data) => { if (sequence.current === request) setActive({ status: 'ready', data }); })
      .catch((caught) => { if (sequence.current === request) setActive({ status: 'error', message: errorMessage(caught) }); });
    return () => {
      candidateQueryController.current?.abort();
      candidateQueryController.current = null;
      activeCase.current = null;
      sequence.current += 1;
    };
  }, [caseNo]);

  const reload = async () => {
    if (busyRef.current) return;
    const request = ++sequence.current;
    setActive({ status: 'loading' });
    setCandidates({ status: 'idle' });
    setError(null);
    try {
      const data = await readCurrentPlan(caseNo);
      if (sequence.current === request) setActive({ status: 'ready', data });
    } catch (caught) {
      if (sequence.current === request) setActive({ status: 'error', message: errorMessage(caught) });
    }
  };

  const observedRevision = useRef(revision);
  useEffect(() => {
    if (observedRevision.current === revision || busy || formalManualProtected || formalPlanCreationProtected || replacementState.busy) return;
    observedRevision.current = revision;
    void reload();
    // Preserve form input and unresolved commands while refreshing owner projections.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revision, busy, formalManualProtected, formalPlanCreationProtected, replacementState.busy]);

  const loadCandidates = async () => {
    candidateQueryController.current?.abort();
    const controller = new AbortController();
    candidateQueryController.current = controller;
    const request = sequence.current;
    setCandidates({ status: 'loading' });
    try {
      const [data, activeStaffIds] = await Promise.all([
        candidateContactPoolClient.query(caseNo, { signal: controller.signal }),
        loadActiveStaffIds({ signal: controller.signal }),
      ]);
      if (data.case_no !== caseNo) throw new Error('候選池案件識別不一致。');
      if (!controller.signal.aborted && sequence.current === request) setCandidates({ status: 'ready', data: { ...data, candidates: data.candidates.filter((candidate) => activeStaffIds.has(candidate.staff_id)) } });
    } catch (caught) {
      if (!controller.signal.aborted && sequence.current === request) setCandidates({ status: 'error', message: errorMessage(caught) });
    } finally {
      if (candidateQueryController.current === controller) candidateQueryController.current = null;
    }
  };

  const current = replacementFlow ? { plan: replacementFlow.command.originalPlan, contact: replacementFlow.command.originalContact } : active.status === 'ready' ? active.data : null;
  const currentSegments = current?.plan.segments ?? [];
  const canCreate = active.status === 'ready' && (current === null
    || (current.plan.activeLockId === null && current.plan.status === 'proposed' && current.contact.customer_decision !== 'accepted'));
  useEffect(() => {
    if (canCreate && current === null && candidates.status === 'idle') void loadCandidates();
    // Read candidates once when the current plan allows a recommendation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canCreate, current, candidates.status]);
  const canCommunicate = current !== null && current.plan.activeLockId === null
    && current.contact.plan.status === 'proposed' && current.contact.customer_decision === 'pending';
  const confirmationPreviewEligible = current !== null;
  const confirmationPlanId = current?.plan.planId ?? null;
  const confirmationVersion = current?.contact.plan.communication_version ?? null;

  useEffect(() => {
    if (!confirmationPreviewEligible || confirmationPlanId === null || confirmationVersion === null) {
      setConfirmationPreview({ status: 'idle' });
      return undefined;
    }
    const controller = new AbortController();
    setConfirmationPreview({ status: 'loading' });
    void matchingPlanCommunicationClient.previewCustomerConfirmation(
      caseNo, confirmationPlanId, confirmationVersion, { signal: controller.signal },
    )
      .then((data) => {
        if (!controller.signal.aborted) setConfirmationPreview({ status: 'ready', data });
      })
      .catch((caught) => {
        if (!controller.signal.aborted) setConfirmationPreview({ status: 'error', message: errorMessage(caught) });
      });
    return () => controller.abort();
  }, [
    caseNo,
    confirmationPreviewEligible,
    confirmationPreviewGeneration,
    confirmationPlanId,
    confirmationVersion,
  ]);

  const perform = async (operation: () => Promise<void>, invalidateActiveOnError = true) => {
    if (busyRef.current || activeCase.current !== caseNo) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    setNotice(null);
    const request = sequence.current;
    try {
      await operation();
    } catch (caught) {
      if (sequence.current === request) {
        setError(errorMessage(caught));
        if (invalidateActiveOnError) {
          // No blind retry after a write or a failed readback. Reload the owner first.
          setActive({ status: 'error', message: '請重新讀取目前正式方案後再操作。' });
        }
      }
    } finally {
      busyRef.current = false;
      if (sequence.current === request) setBusy(false);
    }
  };

  const freshVisiblePlan = async (): Promise<CurrentPlan> => {
    if (current === null) throw new Error('請先讀取目前正式方案。');
    const request = sequence.current;
    const fresh = await readCurrentPlan(caseNo, current.plan.planId);
    if (activeCase.current !== caseNo || sequence.current !== request) throw new Error('案件畫面已切換，未送出操作。');
    if (fresh === null || fresh.contact.plan.communication_version !== current.contact.plan.communication_version) {
      throw new Error('正式方案版本已變更，請重新讀取後確認。');
    }
    return fresh;
  };

  const observe = async (planId: number, validate: (data: CurrentPlan) => boolean, message: string) => {
    if (activeCase.current !== caseNo) return;
    const request = sequence.current;
    const data = await readCurrentPlan(caseNo, planId);
    if (data === null || !validate(data)) throw new Error('操作後正式方案回讀尚未確認預期結果，請重新讀取；不重送操作。');
    if (activeCase.current !== caseNo || sequence.current !== request) return;
    setActive({ status: 'ready', data });
    setNotice(message);
    onObserved?.();
  };

  const observeFormalManualResponse = async (state: FormalManualResponseFlowState, request: number) => {
    const { command, receipt } = state;
    if (receipt === null) throw new Error('正式人工回覆尚未收到收據，不能只讀取結果。');
    orderMutationFlowStore.setFormalManualResponse(caseNo, { ...state, status: 'observing', error: null });
    const data = await readCurrentPlan(command.caseNo, command.planId);
    const receivedVersion = receipt.communication_version;
    const observed = data !== null && data.contact.plan.communication_version >= receivedVersion
      && (command.kind === 'willingness'
        ? data.contact.segments.some((segment) => segment.segment_id === command.segmentId && segment.willingness === (command.willingness ?? 'willing'))
        : data.contact.customer_decision === command.decision);
    if (!observed) throw new Error('正式人工回覆已收到收據，但目前方案回讀尚未確認相同版本與結果；只能重新讀取。');
    if (activeCase.current !== caseNo || sequence.current !== request) {
      throw new Error('案件已切換；保留收據，只能重新讀取原案件結果。');
    }
    setActive({ status: 'ready', data });
    setNotice(command.kind === 'willingness' ? '月嫂意願變更已儲存並完成回讀。' : '客戶決定已完成正式回讀。');
    if (command.kind === 'willingness') { setWillingnessReason(''); setWillingnessChoice(''); setChangingSegmentId(null); }
    else { setDecisionReason(''); setShowManualDecision(false); }
    orderMutationFlowStore.clearFormalManualResponse(caseNo);
    onObserved?.();
  };

  const isDefinitiveManualRejection = (caught: unknown) => caught instanceof ApiHttpError
    && caught.status >= 400 && caught.status < 500 && caught.status !== 408 && caught.status !== 429;

  const formalManualActor = (): string => {
    const actor = sessionClient.getUser()?.username.trim() ?? '';
    if (!actor) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
    return actor;
  };

  const submitFormalManualResponse = async (command: FormalManualResponseCommand, recovery: boolean) => {
    orderMutationFlowStore.setFormalManualResponse(caseNo, { status: 'applying', command, receipt: null, error: null });
    const request = sequence.current;
    let receipt: FormalManualResponseFlowState['receipt'];
    try {
      receipt = command.kind === 'willingness'
        ? await matchingPlanCommunicationClient.recordFormalPlanWillingness(
          command.caseNo, command.planId, command.segmentId, command.expectedVersion, command.reason, command.key, command.actor, command.willingness ?? 'willing',
        )
        : await matchingPlanCommunicationClient.recordCustomerDecision(
          command.caseNo, command.planId, command.expectedVersion, command.decision, command.reason, command.key, command.actor,
        );
    } catch (caught) {
      if (isDefinitiveManualRejection(caught) && !recovery) {
        orderMutationFlowStore.clearFormalManualResponse(caseNo);
        if (activeCase.current === caseNo && sequence.current === request) setError(errorMessage(caught));
      } else {
        const message = recovery
          ? '正式人工回覆結果仍未確認；請恢復權限後使用原操作重新確認。'
          : '正式人工回覆結果尚未確認；請使用原操作重新確認。';
        orderMutationFlowStore.setFormalManualResponse(caseNo, { status: 'outcome_unknown', command, receipt: null, error: message });
        if (activeCase.current === caseNo && sequence.current === request) setError(message);
      }
      return;
    }
    const received: FormalManualResponseFlowState = { status: 'observation_failed', command, receipt, error: null };
    orderMutationFlowStore.setFormalManualResponse(caseNo, received);
    try {
      await observeFormalManualResponse(received, request);
    } catch (caught) {
      const message = errorMessage(caught);
      const saved = orderMutationFlowStore.getFormalManualResponse(caseNo);
      if (saved?.receipt) orderMutationFlowStore.setFormalManualResponse(caseNo, { ...saved, status: 'observation_failed', error: message });
      if (activeCase.current === caseNo && sequence.current === request) setError(message);
    }
  };

  const runFormalManualResponse = async (operation: () => Promise<void>) => {
    if (busyRef.current || activeCase.current !== caseNo) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await operation();
    } catch (caught) {
      if (activeCase.current === caseNo) setError(errorMessage(caught));
    } finally {
      busyRef.current = false;
      if (activeCase.current === caseNo) setBusy(false);
    }
  };

  const observeFormalPlanCreation = async (state: FormalPlanCreationFlowState, request: number) => {
    const { command, receipt } = state;
    const observationToken = crypto.randomUUID();
    const ownsObservation = () => orderMutationFlowStore.getFormalPlanCreation(caseNo, 'single')?.observationToken === observationToken;
    orderMutationFlowStore.setFormalPlanCreation(caseNo, { ...state, status: 'observing', error: null, observationToken });
    try {
      if (receipt === null || receipt.case_no !== command.caseNo || receipt.actor !== command.actor
        || receipt.as_of !== command.asOf || receipt.event_key !== command.key
        || !hasExactPlanReceiptSegments(receipt.segments, command.segments)) {
        throw new Error('正式媒合方案建立收據 identity 不一致；只能重新讀取。');
      }
      const data = await readCurrentPlan(command.caseNo, receipt.plan_id);
      if (!ownsObservation()) return;
      if (data === null || data.plan.planVersion === undefined || data.plan.planVersion < receipt.version
        || !hasExactPlanSegments(data.plan.segments, command.segments)) {
        throw new Error('正式媒合方案建立收據與目前方案分段不一致；只能重新讀取。');
      }
      if (activeCase.current !== caseNo || sequence.current !== request) {
        orderMutationFlowStore.setFormalPlanCreation(caseNo, { ...state, status: 'observation_failed', error: '案件畫面已切換；保留收據，只能重新讀取原案件結果。' });
        return;
      }
      setActive({ status: 'ready', data });
      setNotice(`正式媒合方案已建立：#${receipt.plan_id}`);
      orderMutationFlowStore.clearFormalPlanCreation(caseNo, 'single');
      onObserved?.();
    } catch (caught) {
      if (ownsObservation()) {
        orderMutationFlowStore.setFormalPlanCreation(caseNo, {
          ...state,
          status: 'observation_failed',
          error: errorMessage(caught),
        });
      }
      throw caught;
    }
  };

  const createPlan = (candidate: CandidateContact) => {
    if (busyRef.current || formalPlanCreationProtected || activeCase.current !== caseNo) return;
    void (async () => {
      busyRef.current = true;
      setBusy(true);
      setError(null);
      setNotice(null);
      const request = sequence.current;
      let command: FormalPlanCreationFlowState['command'] | null = null;
      try {
    if (!canCreate || candidate.status !== 'active' || candidate.willingness !== 'willing') return;
    const [existing, detail] = await Promise.all([readCurrentPlan(caseNo), ordersQueryClient.getOrderDetail(caseNo)]);
    if (activeCase.current !== caseNo || sequence.current !== request) return;
    if (detail.case_no !== caseNo || !['洽談中', '訂單成立'].includes(detail.order_status)
      || (existing !== null && (existing.plan.activeLockId !== null || existing.plan.status === 'accepted'
        || existing.contact.customer_decision === 'accepted'))) {
      throw new Error('目前案件或正式方案已鎖定，不可重新建立媒合方案。');
    }
    const segments = [{
      staff_id: candidate.staff_id,
      start_date: candidate.service_start_date,
      end_date: candidate.service_end_date,
    }];
    command = {
      caseNo,
      kind: 'single',
      actor: sessionClient.getUser()?.username.trim() ?? '',
      asOf: new Date().toISOString().slice(0, 10),
      key: `orders-single-plan-${crypto.randomUUID()}`,
      segments,
    };
    if (!command.actor) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
    orderMutationFlowStore.setFormalPlanCreation(caseNo, { status: 'applying', command, receipt: null, error: null });
    let receipt: FormalPlanCreationFlowState['receipt'];
    try {
      receipt = await matchingCandidateWorkflowClient.createSingleCaregiverPlan(command);
    } catch (caught) {
      const message = errorMessage(caught);
      if (isDefinitivePlanRejection(caught)) orderMutationFlowStore.clearFormalPlanCreation(caseNo, 'single');
      else orderMutationFlowStore.setFormalPlanCreation(caseNo, { status: 'outcome_unknown', command, receipt: null, error: message });
      throw caught;
    }
    const saved: FormalPlanCreationFlowState = { status: 'observation_failed', command, receipt, error: null };
    orderMutationFlowStore.setFormalPlanCreation(caseNo, saved);
    if (activeCase.current !== caseNo || sequence.current !== request) return;
    await observeFormalPlanCreation(saved, request);
      } catch (caught) {
        const message = errorMessage(caught);
        if (activeCase.current === caseNo && sequence.current === request) setError(message);
      } finally {
        busyRef.current = false;
        if (activeCase.current === caseNo && sequence.current === request) setBusy(false);
      }
    })();
  };

  const retryFormalPlanCreationReadback = () => {
    const saved = orderMutationFlowStore.getFormalPlanCreation(caseNo, 'single');
    if ((saved?.status !== 'observation_failed' && saved?.status !== 'observing') || saved.receipt === null) return;
    const request = sequence.current;
    void runFormalManualResponse(async () => {
      try {
        await observeFormalPlanCreation(saved, request);
      } catch (caught) {
        const message = errorMessage(caught);
        if (activeCase.current === caseNo && sequence.current === request) setError(message);
      }
    });
  };

  const confirmOriginalFormalPlanCreation = () => {
    const saved = orderMutationFlowStore.getFormalPlanCreation(caseNo, 'single');
    if (saved?.status !== 'outcome_unknown') return;
    void runFormalManualResponse(async () => {
      const request = sequence.current;
      let originalNotRecorded = false;
      try {
        let receipt: FormalPlanCreationFlowState['receipt'];
        try {
          receipt = await matchingCandidateWorkflowClient.queryMatchingPlanReceipt(saved.command);
        } catch (caught) {
          if (!(caught instanceof ApiHttpError) || caught.status !== 404) throw caught;
          originalNotRecorded = true;
          receipt = await matchingCandidateWorkflowClient.createSingleCaregiverPlan(saved.command);
        }
        const received: FormalPlanCreationFlowState = { ...saved, status: 'observation_failed', receipt, error: null };
        orderMutationFlowStore.setFormalPlanCreation(caseNo, received);
        await observeFormalPlanCreation(received, request);
      } catch (caught) {
        const message = errorMessage(caught);
        const current = orderMutationFlowStore.getFormalPlanCreation(caseNo, 'single');
        if (current && !current.receipt && originalNotRecorded && isDefinitivePlanRejection(caught)) {
          orderMutationFlowStore.clearFormalPlanCreation(caseNo, 'single');
        } else if (current) {
          orderMutationFlowStore.setFormalPlanCreation(caseNo, { ...current, status: current.receipt ? 'observation_failed' : 'outcome_unknown', error: message });
        }
        if (activeCase.current === caseNo && sequence.current === request) setError(message);
      }
    });
  };

  const sendProfiles = () => perform(async () => {
    const fresh = await freshVisiblePlan();
    if (fresh.plan.activeLockId !== null || fresh.contact.plan.status !== 'proposed'
      || fresh.contact.customer_decision !== 'pending' || !fresh.contact.all_willing
      || fresh.contact.customer_profiles_status !== null || !resumeNote.trim()) {
      throw new Error('目前方案尚不可寄送或已有確認資訊任務，請依正式聯繫狀態續辦。');
    }
    if (confirmationPreview.status !== 'ready'
      || confirmationPreview.data.plan_id !== fresh.plan.planId
      || confirmationPreview.data.expected_version !== fresh.contact.plan.communication_version) {
      throw new Error('確認資訊檢查結果已過期，請重新檢查後再寄送。');
    }
    if (!confirmationPreview.data.send_allowed) {
      throw new Error(confirmationPreview.data.blockers[0] ?? '確認資訊尚未完整，不能寄送。');
    }
    const signature = `${caseNo}:${fresh.plan.planId}:${fresh.contact.plan.communication_version}:${resumeNote.trim()}`;
    if (confirmationActionIdentity.current?.signature !== signature) {
      confirmationActionIdentity.current = {
        signature,
        key: `orders-customer-confirmation-${fresh.plan.planId}-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`,
      };
    }
    const receipt = await matchingPlanCommunicationClient.sendCustomerConfirmation(
      caseNo, fresh.plan.planId, fresh.contact.plan.communication_version, resumeNote.trim(),
      confirmationActionIdentity.current.key,
    );
    await observe(fresh.plan.planId, (data) => data.contact.customer_profiles_status !== null,
      `確認資訊發送工作已建立：#${receipt.intent_id}（狀態：${profileStatusLabel(receipt.delivery_status)}）；尚不代表 LINE 已送達。`);

  });

  const recordWillingness = (segmentId: number) => {
    if (protectedOperation || !willingnessValidation.validate([
      { value: willingnessChoice, label: '接案意願', ref: willingnessChoiceRef },
    ])) return;
    return runFormalManualResponse(async () => {
      const fresh = await freshVisiblePlan();
      const assignment = await ordersQueryClient.getAssignmentPlan(caseNo);
      if (assignment.service_started || assignment.assignments.length > 0) throw new Error('本案已有正式指派，請由換人或請假代班記錄人員異動。');
      if (!fresh.contact.segments.some((segment) => segment.segment_id === segmentId)
        || !willingnessChoice) throw new Error('目前區段不可補登意願。');
      await submitFormalManualResponse({
        kind: 'willingness', caseNo, planId: fresh.plan.planId, segmentId,
        willingness: willingnessChoice,
        expectedVersion: fresh.contact.plan.communication_version, reason: willingnessReason.trim(),
        key: `orders-formal-manual-willingness-${fresh.plan.planId}-${segmentId}-${crypto.randomUUID()}`,
        actor: formalManualActor(),
      }, false);
    });
  };

  const recordDecision = (decision: 'accepted' | 'declined') => {
    if (protectedOperation) return;
    return runFormalManualResponse(async () => {
      const fresh = await freshVisiblePlan();
      if (fresh.plan.activeLockId !== null || fresh.contact.plan.status !== 'proposed'
        || !['pending', 'contact_requested'].includes(fresh.contact.customer_decision) || !fresh.contact.all_willing) {
        throw new Error('目前正式方案不可記錄客戶決定。');
      }
      await submitFormalManualResponse({
        kind: 'customer_decision', caseNo, planId: fresh.plan.planId,
        expectedVersion: fresh.contact.plan.communication_version, decision, reason: decisionReason.trim(),
        key: `orders-formal-manual-customer-decision-${fresh.plan.planId}-${crypto.randomUUID()}`,
        actor: formalManualActor(),
      }, false);
    });
  };

  const retryFormalManualResponse = () => {
    const saved = orderMutationFlowStore.getFormalManualResponse(caseNo);
    if (saved?.status !== 'outcome_unknown') return;
    void runFormalManualResponse(() => submitFormalManualResponse(saved.command, true));
  };

  const retryFormalManualReadback = () => {
    const saved = orderMutationFlowStore.getFormalManualResponse(caseNo);
    if (saved?.status !== 'observation_failed' || saved.receipt === null) return;
    const request = sequence.current;
    void runFormalManualResponse(async () => {
      try {
        await observeFormalManualResponse(saved, request);
      } catch (caught) {
        const message = errorMessage(caught);
        const currentSaved = orderMutationFlowStore.getFormalManualResponse(caseNo);
        if (currentSaved?.receipt) orderMutationFlowStore.setFormalManualResponse(caseNo, { ...currentSaved, status: 'observation_failed', error: message });
        if (activeCase.current === caseNo && sequence.current === request) {
          setError(message);
        }
      }
    });
  };

  const pendingWillingnessCount = current?.contact.segments.filter(segment => segment.willingness === 'pending').length ?? 0;
  const confirmationDeliveryStatus = current?.contact.customer_confirmation_status
    ?? current?.contact.customer_profiles_status
    ?? null;
  const visibleStatus = current?.contact.segments.some(segment => segment.willingness === 'unwilling') ? '需要換人' : current === null
    ? '尚未選定月嫂'
    : current.contact.customer_decision !== 'pending'
      ? decisionLabel(current.contact.customer_decision)
      : pendingWillingnessCount > 0
        ? `待確認 ${pendingWillingnessCount} 位月嫂意願`
        : profileStatusLabel(confirmationDeliveryStatus);

  const informationLabels = ['服務條件與費用', '照護與飲食需求', '每週服務說明'] as const;
  const segmentName = (segmentId: number, staffId: number) => {
    const candidate = candidates.status === 'ready' ? candidates.data.candidates.find(value => value.staff_id === staffId) : undefined;
    const segment = current?.contact.segments.find(value => value.segment_id === segmentId);
    return staffDisplayLabel(segment?.staff_union_no ?? candidate?.staff_union_no, segment?.staff_name ?? candidate?.staff_name ?? '姓名未設定');
  };
  const informationReady = confirmationPreview.status === 'ready' ? [confirmationPreview.data.order_information_1_ready, confirmationPreview.data.order_information_2_ready, confirmationPreview.data.weekly_service_ready] : [false, false, false];
  useUnsavedDraft('正式推薦確認', { '接案意願': willingnessChoice, '意願原因': willingnessReason, '確認原因': decisionReason, '傳送備註': resumeNote }, { busy: protectedOperation || multiBusy, resetKey: revision });


  return (
    <section className="formal-recommendation" aria-label={`案件 ${caseNo} 正式推薦媒合方案`}>
      {active.status === 'loading' && <p role="status">讀取目前正式方案中…</p>}
      {active.status === 'error' && <div role="alert"><strong>目前無法讀取推薦進度</strong><p>{active.message}</p><button type="button" disabled={protectedOperation} onClick={() => void reload()}>再試一次</button></div>}
      {active.status === 'ready' && current === null && <section className="formal-recommendation-selection">
        <header className="formal-recommendation-summary"><div><h3>選定推薦月嫂</h3><p>只列出已願意承接的人選；選定後即可準備客戶確認資訊。</p></div><button type="button" disabled={protectedOperation || candidates.status === 'loading'} onClick={() => void loadCandidates()}>更新人選</button></header>
        {candidates.status === 'loading' && <p role="status">讀取候選人中…</p>}
        {candidates.status === 'error' && <div role="alert">{candidates.message}</div>}
        {candidates.status === 'ready' && candidates.data.candidates.filter(candidate => candidate.status === 'active' && candidate.willingness === 'willing').sort((left, right) => compareStaffUnionNumbers({ id: left.staff_id, unionNo: left.staff_union_no }, { id: right.staff_id, unionNo: right.staff_union_no })).map(candidate => <article className={`formal-recommendation-candidate${candidate.id === initialCandidateId ? ' highlighted' : ''}`} key={candidate.id}>
          <div><strong>{staffDisplayLabel(candidate.staff_union_no, candidate.staff_name)}</strong>{candidate.id === initialCandidateId && <small>從詢問清單帶入的人選</small>}<span>{candidate.service_start_date} ～ {candidate.service_end_date}</span><span>已願意承接</span></div>
          <button className="formal-recommendation-primary" type="button" aria-label={`以 ${candidate.staff_name} 建立正式媒合方案`} disabled={protectedOperation || !canCreate} onClick={() => void createPlan(candidate)}>選定為推薦月嫂</button>
        </article>)}
        {candidates.status === 'ready' && !candidates.data.candidates.some(candidate => candidate.status === 'active' && candidate.willingness === 'willing') && <p>目前沒有已願意承接的候選月嫂，請先回到「尋找月嫂與詢問意願」完成詢問。</p>}
        <p className="formal-recommendation-hint">接案同意沿用前一步紀錄，無須再次人工確認。</p>
        {onOpenCandidates && <button type="button" disabled={protectedOperation} onClick={onOpenCandidates}>返回尋找人選</button>}
      </section>}
      {current !== null && <div className="formal-recommendation-plan">
        <header className="formal-recommendation-summary"><div><h3>{replacementVisible ? '原推薦方案' : currentSegments.length > 1 ? '推薦方案・多月嫂分段' : '推薦方案'}</h3><p>接案同意沿用前一步紀錄；月嫂通知變更時另行記錄。</p></div><div className="formal-recommendation-actions"><span className="formal-recommendation-status" role="status">{visibleStatus}</span><button type="button" disabled={protectedOperation} onClick={() => setReplacementOpen(value => !value)}>{replacementVisible ? '收合換人' : '更換月嫂'}</button></div></header>
        <div className="formal-recommendation-people">{currentSegments.map(segment => {
          const willingness = current.contact.segments.find(item => item.segment_id === segment.segmentId)?.willingness ?? 'pending';
          return <article className="formal-recommendation-person" key={segment.segmentId}><div className="formal-recommendation-person-details"><div><strong>{segmentName(segment.segmentId, segment.staffId)}</strong><small>{currentSegments.length > 1 ? `第 ${segment.sequence} 段` : '推薦月嫂'}</small></div><div className="formal-recommendation-period">{segment.assignedStartDate} ～ {segment.assignedEndDate}</div></div><div><span className={`formal-recommendation-person-status ${willingness === 'willing' ? 'ready' : ''}`}>{willingness === 'willing' ? '已同意承接' : willingness === 'unwilling' ? '已通知不承接' : '尚未同意承接'}</span>{!replacementVisible && <button className="formal-recommendation-text-action" type="button" disabled={protectedOperation} onClick={() => { setChangingSegmentId(id => id === segment.segmentId ? null : segment.segmentId); setWillingnessChoice(''); setWillingnessReason(''); }}>手動修改月嫂意願</button>}</div></article>;
        })}</div>
        {changingSegmentId !== null && !replacementVisible && <section className="formal-recommendation-inline-form" aria-label="手動修改月嫂意願">
          <h4>手動修改月嫂意願</h4><p>請選擇月嫂最新通知的接案意願，原因可留空。</p>
          <fieldset disabled={protectedOperation}><legend>接案意願（必選）</legend>
            <label><input ref={willingnessChoiceRef} type="radio" name="formal-willingness" value="willing" checked={willingnessChoice === 'willing'} onChange={() => setWillingnessChoice('willing')} />願意承接</label>
            <label><input type="radio" name="formal-willingness" value="unwilling" checked={willingnessChoice === 'unwilling'} onChange={() => setWillingnessChoice('unwilling')} />不承接</label>
          </fieldset>
          <label>修改原因（選填）<textarea ref={willingnessReasonRef} value={willingnessReason} maxLength={500} disabled={protectedOperation} onChange={event => setWillingnessReason(event.target.value)} /></label>{willingnessValidation.feedback}
          <div className="formal-recommendation-actions">
            <button className="formal-recommendation-primary" type="button" disabled={protectedOperation} onClick={() => void recordWillingness(changingSegmentId)}>儲存意願變更</button>
            <button type="button" disabled={protectedOperation} onClick={() => { setChangingSegmentId(null); setWillingnessChoice(''); setWillingnessReason(''); }}>取消</button>
          </div>
        </section>}
        {replacementVisible ? <OrderRecommendationReplacementPanel caseNo={caseNo} plan={current.plan} contact={current.contact} onOpenCandidates={onOpenCandidates} onEditStateChange={setReplacementState} onClose={() => setReplacementOpen(false)} onReplacementStarted={async () => {
          const fresh = await readCurrentPlan(caseNo);
          if (fresh !== null) throw new Error('換人已登記，但原推薦仍為有效方案；請重新讀取，不重送換人。');
          setActive({ status: 'ready', data: null }); setCandidates({ status: 'idle' }); setReplacementOpen(false);
          setNotice('換人已啟動，請選定新月嫂並重新交由客戶確認。'); onObserved?.();
        }} onObserved={() => { setReplacementOpen(false); setNotice('新推薦已建立並完成正式回讀，請重新交由客戶確認。'); void reload(); onObserved?.(); }} /> : <>
          {!current.contact.all_willing && <div className="formal-recommendation-blockers" role="alert">{current.contact.segments.some(segment => segment.willingness === 'unwilling') ? <><strong>推薦月嫂已通知不承接</strong><p>請更換推薦人選，再重新交由客戶確認。</p></> : <><strong>仍有月嫂尚未同意本次服務</strong><p>請先在「尋找月嫂與詢問意願」記錄接案同意，或更換推薦人選。</p>{onOpenCandidates && <button type="button" disabled={protectedOperation} onClick={onOpenCandidates}>前往詢問人選</button>}</>}</div>}
          {current.contact.customer_decision === 'declined' && <div role="alert"><strong>客戶未接受本次推薦</strong><p>請確認客戶需求後，在上方「更換月嫂」選擇新的人選。</p></div>}
          {current.contact.customer_decision === 'contact_requested' && <div role="status"><strong>客戶希望進一步聯絡</strong><p>請查看客戶留言並回覆；客戶仍可由原 LINE 卡片接受配對，也可由人員記錄決定。</p></div>}
          {current.contact.customer_decision !== 'accepted' && <section className="formal-recommendation-customer-info" aria-label="客戶確認資訊"><div className="formal-recommendation-summary"><div><h4>客戶確認資訊</h4><p>本次推薦方案的確認內容與寄送狀態。</p></div><span>{profileStatusLabel(confirmationDeliveryStatus)}</span></div>
            {confirmationPreview.status === 'loading' && <p role="status">正在檢查確認資訊…</p>}
            {confirmationPreview.status === 'error' && <div role="alert"><p>目前無法檢查確認資訊：{confirmationPreview.message}</p><button type="button" disabled={protectedOperation} onClick={() => setConfirmationPreviewGeneration(value => value + 1)}>重新檢查</button></div>}
            <div className="formal-recommendation-sheets">{informationLabels.map((label, index) => <article key={label}><strong>{label}</strong><small>{confirmationPreview.status === 'loading' ? '正在檢查' : informationReady[index] ? index === 2 && confirmationPreview.status === 'ready' ? `${confirmationPreview.data.weekly_service_row_count} 週已就緒` : '已就緒' : '尚未就緒'}</small><button type="button" aria-label={`查看${label}`} disabled={confirmationPreview.status !== 'ready'} onClick={() => setInformationTab(index as 0 | 1 | 2)}>查看</button></article>)}</div>
            {confirmationPreview.status === 'ready' && confirmationPreview.data.caregiver_resumes.some(resume => !resume.ready) && <p className="formal-recommendation-hint">{confirmationPreview.data.caregiver_resumes.filter(resume => !resume.ready).map(resume => staffIdentity.label(resume.staff_id, resume.staff_name)).join('、')}履歷 PDF 未附；可先寄送確認資訊，履歷由工會另行提供。</p>}
            {confirmationPreview.status === 'ready' && confirmationDeliveryStatus === null && confirmationPreview.data.blockers.length > 0 && <div className="formal-recommendation-blockers" role="alert"><strong>尚不能寄送</strong><ul>{confirmationPreview.data.blockers.map(blocker => <li key={blocker}>{blocker}</li>)}</ul></div>}
            {canCommunicate && current.contact.all_willing && current.contact.customer_profiles_status === null && <>
              <details><summary>調整寄送訊息</summary><label>確認資訊備註<textarea aria-label={`方案 ${current.plan.planId} 確認資訊備註`} value={resumeNote} maxLength={1000} disabled={protectedOperation} onChange={event => setResumeNote(event.target.value)} /></label></details>
              <button className="formal-recommendation-primary" type="button" disabled={protectedOperation || confirmationPreview.status !== 'ready' || !confirmationPreview.data.send_allowed || !resumeNote.trim()} onClick={() => void sendProfiles()}>寄送確認資訊給客戶</button>
            </>}
            {confirmationDeliveryStatus !== null && <p className="formal-recommendation-hint">{['pending', 'processing'].includes(confirmationDeliveryStatus) ? '已建立寄送工作，等待系統送出；尚不代表 LINE 已送達。' : `確認資訊狀態：${profileStatusLabel(confirmationDeliveryStatus)}。`}</p>}
            {current.contact.all_willing && current.contact.customer_decision !== 'declined' && current.plan.activeLockId === null && <><button className="formal-recommendation-text-action" type="button" disabled={protectedOperation} onClick={() => setShowManualDecision(value => !value)}>手動記錄客戶決定</button>{showManualDecision && <section className="formal-recommendation-inline-form" aria-label="手動記錄客戶決定"><h4>手動記錄客戶決定</h4><p>客戶透過電話、面談或其他方式確認時，在此記錄；不會將人工紀錄標示為 LINE 送達。</p><label>客戶回覆依據（選填）<textarea ref={decisionReasonRef} aria-label={`方案 ${current.plan.planId} 客戶決策依據`} value={decisionReason} maxLength={500} disabled={protectedOperation} onChange={event => setDecisionReason(event.target.value)} /></label><div className="formal-recommendation-actions"><button className="formal-recommendation-primary" type="button" aria-label={`記錄方案 ${current.plan.planId} 客戶接受`} disabled={protectedOperation} onClick={() => void recordDecision('accepted')}>客戶接受</button><button type="button" aria-label={`記錄方案 ${current.plan.planId} 客戶拒絕`} disabled={protectedOperation} onClick={() => void recordDecision('declined')}>客戶拒絕</button><button type="button" disabled={protectedOperation} onClick={() => setShowManualDecision(false)}>取消</button></div></section>}</>}
          </section>}
            {current.contact.all_willing && current.contact.customer_decision === 'accepted' && <section className="formal-recommendation-customer-info" aria-label={`方案 ${current.plan.planId} 等待訂金鎖`}><p>客戶已接受配對，請接續辦理雙方簽約；完成簽約後再建立本案服務群組。</p><h4>{assignmentExists ? '已轉為正式班表' : current.plan.activeLockId === null ? '等待服務日期確認' : '推薦已確認・檔期已自動保留'}</h4>{assignmentExists ? <p>等待訂金鎖已轉為正式排班，無須再次保留檔期。</p> : current.plan.activeLockId !== null ? <p>配對及服務日期已確認，系統已自動建立等待訂金鎖；契約與排班依後續步驟辦理。</p> : <p>配對及服務日期確認後，系統會自動保留月嫂檔期，不需另行操作。</p>}{onOpenServiceDates && <button type="button" disabled={protectedOperation} onClick={onOpenServiceDates}>{current.plan.activeLockId === null && !assignmentExists ? '前往確認服務日期' : '接續服務日期與排班'}</button>}</section>}
          <footer className="formal-recommendation-footer"><small>本案推薦、寄送及客戶回覆狀態</small><button className="formal-recommendation-text-action" type="button" aria-label={`重新讀取方案 ${current.plan.planId} 確認資訊送達狀態`} disabled={protectedOperation} onClick={() => void reload()}>更新狀態</button></footer>
        </>}
      </div>}
      {informationTab !== null && confirmationPreview.status === 'ready' && <CandidateInquiryDialog title="客戶確認資訊" wide onClose={() => setInformationTab(null)}><div className="formal-confirmation-dialog-body"><nav className="order-case-subnav" aria-label="確認資訊種類">{informationLabels.map((label, index) => <button type="button" aria-pressed={informationTab === index} key={label} onClick={() => setInformationTab(index as 0 | 1 | 2)}>{label}</button>)}</nav><h3>{informationLabels[informationTab]}</h3>{informationTab < 2 ? (informationTab === 0 ? confirmationPreview.data.order_information_1 : confirmationPreview.data.order_information_2).map(item => <article key={item.segment_id}><h4>{staffIdentity.label(item.staff_id, item.staff_name)}</h4><pre>{item.text}</pre></article>) : <div className="formal-recommendation-weekly-preview"><table><thead><tr><th>週次</th><th>月嫂</th><th>期間</th><th>工作日</th><th>時數</th></tr></thead><tbody>{confirmationPreview.data.weekly_service_rows.map(item => <tr key={item.serial_number}><td>第 {item.serial_number} 週</td><td>{staffIdentity.label(item.staff_id, item.staff_name)}</td><td>{item.week_start_date} ～ {item.week_end_date}</td><td>{item.weekly_work_days} 日</td><td>{item.weekly_hours} 小時</td></tr>)}</tbody></table></div>}</div></CandidateInquiryDialog>}

      {includeMultiCaregiver && active.status === 'ready' && current === null && <details className="order-case-secondary-actions"><summary>多月嫂接續方案</summary>
        <p>指定接續人選並核對分段日期；這會建立正式推薦方案。</p><OrderMultiCaregiverPlanPanel caseNo={caseNo} filters={defaultMatchingFilterPolicy}
          onObserved={onObserved} onBusyChange={setMultiBusy} />
      </details>}
      {formalManualResponse?.status === 'outcome_unknown' && (
        <section aria-label="正式人工回覆結果未明" className="formal-recommendation-next">
          <p role="alert">正式人工回覆結果尚未確認；請恢復權限後使用原操作重新確認。</p>
          <button type="button" data-control-id="orders.formal-manual-response.reconcile-original" onClick={retryFormalManualResponse}>
            以原操作重新確認正式人工回覆
          </button>
        </section>
      )}
      {formalManualResponse?.status === 'observation_failed' && (
        <section aria-label="正式人工回覆回讀失敗" className="formal-recommendation-next">
          <p role="alert">正式人工回覆已收到收據，但回讀尚未確認；只能重新讀取。</p>
          <button type="button" data-control-id="orders.formal-manual-response.readback" onClick={retryFormalManualReadback}>
            只重新讀取正式人工回覆結果
          </button>
        </section>
      )}
      {formalPlanCreation?.status === 'outcome_unknown' && (
        <section aria-label="正式媒合方案建立結果未確定" className="formal-recommendation-next">
          <p role="alert">尚未確認是否建立成功。</p>
          {formalPlanCreation.error && <p role="alert">原因：{formalPlanCreation.error}</p>}
          <button type="button" data-control-id="orders.formal-plan-creation.reconcile-original" onClick={confirmOriginalFormalPlanCreation}>
            確認建立結果
          </button>
        </section>
      )}
      {(formalPlanCreation?.status === 'observation_failed' || formalPlanCreation?.status === 'observing') && (
        <section aria-label="正式媒合方案建立回讀失敗" className="formal-recommendation-next">
          <p role="alert">方案已建立，請重新讀取最新狀態。</p>
          {formalPlanCreation.error && <p role="alert">原因：{formalPlanCreation.error}</p>}
          <button type="button" data-control-id="orders.formal-plan-creation.readback" onClick={retryFormalPlanCreationReadback}>
            重新讀取
          </button>
        </section>
      )}
      {busy && <p role="status">正式媒合操作／回讀中…</p>}
      {notice && <p role="status">{notice}</p>}
      {error && !formalPlanCreation?.error && <p role="alert">{error}</p>}
    </section>
  );
};

export default OrderFormalRecommendationPanel;
