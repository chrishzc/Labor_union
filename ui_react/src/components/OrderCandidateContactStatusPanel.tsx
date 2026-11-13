import { useUnsavedChanges } from './UnsavedChanges';
import { useSaveValidation } from './useSaveValidation';
import { useEffect, useId, useRef, useState, type FC } from 'react';
import {
  candidateContactPoolClient,
  createCandidateInformationSendCommand,
  createCandidateWillingnessCommand,
  type CandidateContactPool,
  type CandidateInformationSendCommand,
  type CandidateInformationKind,
  type CandidateInformationPackagePreview,
  type CaseInformationPreview,
  type CaseWeeklyServicePreview,
} from '../api/scheduling/candidate_contact_pool_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { defaultMatchingFilterPolicy, matchingCandidateWorkflowClient, type MatchingAvailability } from '../api/scheduling/matching_candidate_workflow_client';
import { subscribeStaffAvailabilityChanges } from '../api/staff_availability/staff_availability_changes';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { CandidateInformationPages, CandidateWeeklyServiceTable, OrderCandidateInformationPanel, OrderCandidateInformationSendPanel, CANDIDATE_INFORMATION_LABELS } from './OrderCandidateInformationPanel';
import { CandidatePlannedServiceDates } from './CandidatePlannedServiceDates';
import { compareStaffUnionNumbers, staffDisplayLabel } from '../adapters/staff/staff_directory_adapter';
import { CaregiverCommuteQuery } from './CaregiverCommute';
import { CandidateAvailabilityNotice } from './CandidateAvailabilityNotice';

interface OrderCandidateContactStatusPanelProps {
  caseNo: string;
  onObserved?: () => void;
  onAddCandidates?: () => void;
  focusWillingness?: boolean;
  revision?: number;
  onEditStateChange?: (state: { dirty: boolean; busy: boolean }) => void;
  presentation?: 'legacy' | 'workbench';
  onOpenCustomerConfirmation?: (candidateId: number) => void;
  focusedCandidateId?: number;
  visible?: boolean;
}

type ContactStatusState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: CandidateContactPool }
  | { status: 'error'; message: string };

type CandidateContact = CandidateContactPool['candidates'][number];

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '候選聯絡狀態查詢失敗';
}

function deliveryStatus(
  delivery: CandidateContact['information']['1'] | CandidateContact['information']['2'] | undefined,
  compact = false,
): string {
  if (delivery == null) return '尚無紀錄';
  const labels = { queued: '等待發送', pending: '處理中', sent: '已發送', manually_confirmed: '已人工確認', retryable_failed: '發送未完成', failed: '發送失敗', cancelled: '已取消發送' };
  return `${labels[delivery.status]} · ${compact ? delivery.sent_at.replace('T', ' ').slice(0, 16) : delivery.sent_at}`;
}

export const OrderCandidateContactStatusPanel: FC<OrderCandidateContactStatusPanelProps> = ({ caseNo, onObserved, onAddCandidates, focusWillingness = false, revision = 0, onEditStateChange, presentation = 'legacy', onOpenCustomerConfirmation, focusedCandidateId, visible = true }) => {
  const [state, setState] = useState<ContactStatusState>({ status: 'idle' });
  const [availability, setAvailability] = useState<MatchingAvailability | 'error' | null>(null);
  const [availabilityRevision, setAvailabilityRevision] = useState(0);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [reasonDrafts, setReasonDrafts] = useState<Record<number, string>>({});
  const [willingnessNotices, setWillingnessNotices] = useState<Record<number, string>>({});
  const [sharedInformation, setSharedInformation] = useState<{ kind?: CandidateInformationKind } | null>(null);
  const [informationTarget, setInformationTarget] = useState<{ candidateId: number; resend: boolean } | null>(null);
  const [datesReady, setDatesReady] = useState<boolean | null>(null);
  const [weeklyStartDate, setWeeklyStartDate] = useState<string | null>(null);
  const [weekly, setWeekly] = useState<CaseWeeklyServicePreview | null>(null);
  const [dateEdit, setDateEdit] = useState<{ dirty: boolean; busy: boolean } | null>(null);
  const [dateLoadError, setDateLoadError] = useState<string | null>(null);
  const [weeklyOpen, setWeeklyOpen] = useState(true);
  const [previewMode, setPreviewMode] = useState<'idle' | 'open' | 'collapsed'>('idle');
  const [selectionOpen, setSelectionOpen] = useState(true);
  const [previewDocuments, setPreviewDocuments] = useState<CaseInformationPreview[] | null>(null);
  const [previewReply, setPreviewReply] = useState<CandidateInformationPackagePreview | undefined>();
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [preparingSend, setPreparingSend] = useState<number | null>(null);
  const [sendError, setSendError] = useState<{ candidateId: number; message: string } | null>(null);
  const [informationRevision, setInformationRevision] = useState(0);
  const [responseTarget, setResponseTarget] = useState<{ id: number; name: string } | null>(null);
  const [responseChoice, setResponseChoice] = useState<'willing' | 'unwilling' | ''>('');
  const saveValidation = useSaveValidation();
  const responseChoiceRef = useRef<HTMLInputElement>(null);
  const responseReasonRef = useRef<HTMLTextAreaElement>(null);
  const [, setFlowRevision] = useState(0);
  const mounted = useRef(false);
  const activeCaseNo = useRef(caseNo);
  const statusQuerySequence = useRef(0);
  const poolPresentationGeneration = useRef(0);
  const statusQueryController = useRef<AbortController | null>(null);
  const willingnessReadbackControllers = useRef(new Map<string, {
    controller: AbortController;
    caseNo: string;
    candidateId: number;
  }>());
  const informationInFlight = useRef(new Set<string>());
  const preparingSendRef = useRef(false);
  const focusedCandidate = useRef<string | null>(null);
  const sectionId = useId();
  const workbench = presentation === 'workbench';
  useEffect(() => {
    const identity = `${caseNo}:${focusedCandidateId}`;
    if (presentation === 'workbench' && focusedCandidateId !== undefined && state.status === 'ready' && focusedCandidate.current !== identity) {
      const card = document.getElementById(`candidate-inquiry-${caseNo}-${focusedCandidateId}`);
      if (!card) return;
      if (!selectionOpen) {
        setSelectionOpen(true);
        return;
      }
      card.focus(); card.scrollIntoView({ block: 'nearest' }); focusedCandidate.current = identity;
    }
  }, [caseNo, focusedCandidateId, state, presentation, selectionOpen]);
  const candidateInformationFlows = orderMutationFlowStore.getCandidateInformationForCase(caseNo);
  const pendingStatus = (status: string) => ['applying', 'observing', 'outcome_unknown', 'observation_failed'].includes(status);
  const mutationPending = candidateInformationFlows.some((flow) => pendingStatus(flow.status))
    || orderMutationFlowStore.getCandidateWillingnessForCase(caseNo).some((flow) => pendingStatus(flow.status));
  const protectedOperation = mutationPending || preparingSend !== null;
  const hasDraft = Object.values(reasonDrafts).some((value) => value.trim().length > 0);
  const datesDirty = dateEdit?.dirty ?? false;
  const datesBusy = dateEdit?.busy ?? false;
  const previewOpen = previewMode === 'open';
  const previewRequested = previewMode !== 'idle';
  useEffect(() => { onEditStateChange?.({ dirty: hasDraft || datesDirty, busy: protectedOperation || datesBusy }); },
    [hasDraft, datesDirty, datesBusy, protectedOperation, onEditStateChange]);
  useEffect(() => () => { onEditStateChange?.({ dirty: false, busy: false }); }, [onEditStateChange]);
  const cancelWillingnessReadbacks = () => {
    willingnessReadbackControllers.current.forEach(({ controller, caseNo: pendingCaseNo, candidateId }) => {
      controller.abort();
      const current = orderMutationFlowStore.getCandidateWillingness(pendingCaseNo, candidateId);
      if (current?.status === 'observing' && current.receipt) {
        orderMutationFlowStore.setCandidateWillingness(pendingCaseNo, {
          ...current,
          status: 'observation_failed',
          error: '目前無法確認回覆是否已儲存，請重新讀取最新結果。',
        });
      }
    });
    willingnessReadbackControllers.current.clear();
  };
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      statusQueryController.current?.abort();
      cancelWillingnessReadbacks();
    };
  }, []);
  useEffect(() => {
    activeCaseNo.current = caseNo;
    cancelWillingnessReadbacks();
    setWillingnessNotices({});
    setMutationError(null);
    setInformationTarget(null);
    setSharedInformation(null);
    setWeeklyStartDate(null);
    setWeekly(null);
    setWeeklyOpen(true);
    setPreviewMode('idle');
    setSelectionOpen(true);
    setSendError(null);
  }, [caseNo]);
  useEffect(() => orderMutationFlowStore.subscribe(() => {
    if (mounted.current) setFlowRevision((value) => value + 1);
  }), []);

  const startStatusQuery = (requestedCaseNo: string) => {
    statusQueryController.current?.abort();
    const controller = new AbortController();
    const sequence = ++statusQuerySequence.current;
    const presentationGeneration = ++poolPresentationGeneration.current;
    statusQueryController.current = controller;
    setState({ status: 'loading' });
    void candidateContactPoolClient.query(requestedCaseNo, { signal: controller.signal, ...(workbench ? { compareSentInformation: true } : {}) })
      .then((data) => {
        if (
          !controller.signal.aborted
          && mounted.current
          && statusQuerySequence.current === sequence
          && poolPresentationGeneration.current === presentationGeneration
          && activeCaseNo.current === requestedCaseNo
        ) {
          setState({ status: 'ready', data });
        }
      })
      .catch((error) => {
        if (
          !controller.signal.aborted
          && mounted.current
          && statusQuerySequence.current === sequence
          && poolPresentationGeneration.current === presentationGeneration
          && activeCaseNo.current === requestedCaseNo
        ) {
          setState({ status: 'error', message: errorMessage(error) });
        }
      });
    return controller;
  };

  useEffect(() => {
    const controller = startStatusQuery(caseNo);
    return () => controller.abort();
  }, [caseNo, revision]);

  const hasActiveCandidates = state.status === 'ready' && state.data.case_no === caseNo
    && state.data.candidates.some(candidate => candidate.status === 'active');
  const currentAvailability = availability && availability !== 'error' && availability.case_no === caseNo ? availability : null;
  useEffect(() => {
    if (!workbench || !visible) return;
    return subscribeStaffAvailabilityChanges(() => setAvailabilityRevision(value => value + 1));
  }, [workbench, visible]);
  useEffect(() => {
    setAvailability(null);
    if (!workbench || !visible || !hasActiveCandidates) return;
    const controller = new AbortController();
    void matchingCandidateWorkflowClient.searchInquiryCandidates(caseNo, defaultMatchingFilterPolicy, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setAvailability(data); })
      .catch(() => { if (!controller.signal.aborted) setAvailability('error'); });
    return () => controller.abort();
  }, [caseNo, workbench, visible, hasActiveCandidates, availabilityRevision, revision]);

  useEffect(() => {
    if (presentation !== 'workbench') return;
    const controller = new AbortController();
    setDatesReady(null);
    setDateLoadError(null);
    void Promise.resolve().then(() => candidateContactPoolClient.previewCaseInformation(caseNo, 3, { signal: controller.signal }))
      .then(data => { if (!controller.signal.aborted) { setDatesReady(data.send_allowed); setWeeklyStartDate(data.start_date); } })
      .catch(reason => { if (!controller.signal.aborted) setDateLoadError(errorMessage(reason)); });
    return () => controller.abort();
  }, [caseNo, revision, informationRevision, presentation]);

  const representativeId = state.status === 'ready' ? state.data.candidates.find(candidate => candidate.status === 'active')?.id : undefined;
  useEffect(() => {
    setPreviewDocuments(null);
    setPreviewError(null);
    if (!previewRequested || datesReady !== true || presentation !== 'workbench') return;
    const controller = new AbortController();
    void Promise.all(([1, 2, 3] as const).map(kind =>
      candidateContactPoolClient.previewCaseInformation(caseNo, kind, { signal: controller.signal })))
      .then(data => { if (!controller.signal.aborted) setPreviewDocuments(data); })
      .catch(error => { if (!controller.signal.aborted) setPreviewError(errorMessage(error)); });
    return () => controller.abort();
  }, [caseNo, datesReady, informationRevision, previewRequested, presentation, revision]);

  useEffect(() => {
    setPreviewReply(undefined);
    if (!previewRequested || datesReady !== true || representativeId === undefined || presentation !== 'workbench') return;
    const controller = new AbortController();
    void candidateContactPoolClient.previewInformationPackage(caseNo, representativeId, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setPreviewReply(data); })
      .catch(() => { /* The case documents remain available if the optional reply card cannot be read. */ });
    return () => controller.abort();
  }, [caseNo, datesReady, informationRevision, previewRequested, presentation, representativeId, revision]);

  const loadStatus = () => {
    setInformationRevision(value => value + 1);
    startStatusQuery(caseNo);
  };

  const observeInformation = async (command: CandidateInformationSendCommand) => {
    const current = orderMutationFlowStore.getCandidateInformation(
      command.caseNo, command.candidateId,
    );
    if (!current?.receipt) return;
    if (!mounted.current || activeCaseNo.current !== command.caseNo) return;
    const presentationGeneration = ++poolPresentationGeneration.current;
    orderMutationFlowStore.setCandidateInformation(command.caseNo, {
      ...current, status: 'observing', error: null,
    });
    try {
      const readback = await candidateContactPoolClient.query(command.caseNo, workbench ? { compareSentInformation: true } : undefined);
      const candidates = readback.candidates.filter((candidate) => candidate.id === command.candidateId);
      const delivery = candidates[0]?.information.package;
      if (readback.case_no !== command.caseNo || candidates.length !== 1 || !delivery) {
        throw new Error('寄送任務回讀與本次操作不一致。');
      }
      const hasNewerPackage = command.resend && delivery.event_id != null && delivery.event_id > current.receipt.event_id;
      if (!hasNewerPackage && (
        delivery.event_id !== current.receipt.event_id
        || delivery.line_task_id !== current.receipt.line_task_id
      )) {
        throw new Error('寄送結果與剛才的寄送不一致；請重新讀取投遞狀態。');
      }
      orderMutationFlowStore.clearCandidateInformation(
        command.caseNo, command.candidateId,
      );
      if (mounted.current && activeCaseNo.current === command.caseNo) {
        if (poolPresentationGeneration.current === presentationGeneration) {
          setState({ status: 'ready', data: readback });
        }
        onObserved?.();
      }
    } catch (error) {
      const saved = orderMutationFlowStore.getCandidateInformation(
        command.caseNo, command.candidateId,
      );
      if (saved?.receipt) {
        orderMutationFlowStore.setCandidateInformation(command.caseNo, {
          ...saved, status: 'observation_failed', error: errorMessage(error),
        });
      }
    }
  };

  const submitInformation = async (command: CandidateInformationSendCommand) => {
    const key = command.eventKey;
    const current = orderMutationFlowStore.getCandidateInformation(
      command.caseNo, command.candidateId,
    );
    if (informationInFlight.current.has(key) || (current && (current.command.eventKey !== key || current.status !== 'outcome_unknown'))) return;
    const recoveringUnknown = current?.status === 'outcome_unknown';
    informationInFlight.current.add(key);
    if (mounted.current && activeCaseNo.current === command.caseNo) setMutationError(null);
    orderMutationFlowStore.setCandidateInformation(command.caseNo, {
      status: 'applying', command, receipt: null, error: null,
    });
    try {
      const receipt = await candidateContactPoolClient.sendInformation(command);
      orderMutationFlowStore.setCandidateInformation(command.caseNo, {
        status: 'observation_failed', command, receipt, error: null,
      });
      await observeInformation(command);
      return true;
    } catch (error) {
      const rejected = error instanceof ApiHttpError
        && error.status >= 400 && error.status < 500 && error.status !== 408 && error.status !== 429;
      if (rejected && !recoveringUnknown) {
        orderMutationFlowStore.clearCandidateInformation(command.caseNo, command.candidateId);
        if (mounted.current && activeCaseNo.current === command.caseNo) {
          if (presentation === 'workbench') {
            const stale = error.code === 'candidate_information_preview_stale';
            if (stale) setPreviewMode('idle');
            setSendError({ candidateId: command.candidateId, message: stale
              ? '訂單內容或月嫂的 LINE 綁定資料已更新。請重新開啟案件預覽，再確認寄送。'
              : errorMessage(error) });
          } else setMutationError(errorMessage(error));
        }
      } else {
        orderMutationFlowStore.setCandidateInformation(command.caseNo, {
          status: 'outcome_unknown', command, receipt: null,
          error: recoveringUnknown
            ? '目前無法確認寄送結果，請稍後重新讀取投遞狀態。'
            : '寄送結果尚未確認；請確認寄送結果。',
        });
      }
      return false;
    } finally {
      informationInFlight.current.delete(key);
    }
  };

  const retryInformation = (candidateId: number) => {
    const current = orderMutationFlowStore.getCandidateInformation(caseNo, candidateId);
    if (current?.status === 'outcome_unknown') void submitInformation(current.command);
  };

  const retryInformationReadback = (candidateId: number) => {
    const current = orderMutationFlowStore.getCandidateInformation(caseNo, candidateId);
    if (current?.status === 'observation_failed' && current.receipt) void observeInformation(current.command);
  };

  const observeWillingness = async (candidateId: number) => {
    const current = orderMutationFlowStore.getCandidateWillingness(caseNo, candidateId);
    if (!current?.receipt) return;
    const { command, receipt } = current;
    if (!mounted.current || activeCaseNo.current !== command.caseNo) return;
    const presentationGeneration = ++poolPresentationGeneration.current;
    const readbackKey = `${command.caseNo}:${candidateId}:${command.eventKey}`;
    const controller = new AbortController();
    willingnessReadbackControllers.current.get(readbackKey)?.controller.abort();
    willingnessReadbackControllers.current.set(readbackKey, {
      controller, caseNo: command.caseNo, candidateId,
    });
    orderMutationFlowStore.setCandidateWillingness(command.caseNo, {
      ...current, status: 'observing', error: null,
    });
    try {
      const readback = await candidateContactPoolClient.query(command.caseNo, { signal: controller.signal, ...(workbench ? { compareSentInformation: true } : {}) });
      if (
        controller.signal.aborted
        || !mounted.current
        || activeCaseNo.current !== command.caseNo
        || willingnessReadbackControllers.current.get(readbackKey)?.controller !== controller
      ) return;
      const candidates = readback.candidates.filter((candidate) => candidate.id === command.candidateId);
      if (
        readback.case_no !== command.caseNo
        || candidates.length !== 1
        || candidates[0]!.willingness !== command.willingness
        || candidates[0]!.latest_willingness_event_id !== receipt.event_id
      ) {
        throw new Error('最新結果與剛才儲存的回覆不一致，請重新讀取最新結果。');
      }
      if (mounted.current && activeCaseNo.current === command.caseNo) {
        if (poolPresentationGeneration.current === presentationGeneration) {
          setState({ status: 'ready', data: readback });
        }
        setWillingnessNotices((notices) => ({ ...notices, [command.candidateId]: '回覆已儲存。' }));
        setReasonDrafts((drafts) => { const next = { ...drafts }; delete next[command.candidateId]; return next; });
        onObserved?.();
      }
      orderMutationFlowStore.clearCandidateWillingness(command.caseNo, command.candidateId);
      return true;
    } catch {
      if (
        controller.signal.aborted
        || !mounted.current
        || activeCaseNo.current !== command.caseNo
        || willingnessReadbackControllers.current.get(readbackKey)?.controller !== controller
      ) return;
      const saved = orderMutationFlowStore.getCandidateWillingness(command.caseNo, command.candidateId);
      if (saved?.receipt) {
        orderMutationFlowStore.setCandidateWillingness(command.caseNo, {
          ...saved,
          status: 'observation_failed',
          error: '目前無法確認回覆是否已儲存，請重新讀取最新結果。',
        });
      }
    } finally {
      if (willingnessReadbackControllers.current.get(readbackKey)?.controller === controller) {
        willingnessReadbackControllers.current.delete(readbackKey);
      }
    }
  };

  const submitWillingness = async (
    candidateId: number,
    willingness: 'willing' | 'unwilling',
    reason: string,
  ) => {
    const currentCandidate = state.status === 'ready'
      ? state.data.candidates.find((candidate) => candidate.id === candidateId)
      : undefined;
    const saved = orderMutationFlowStore.getCandidateWillingness(caseNo, candidateId);
    if (saved?.status !== 'outcome_unknown' && currentCandidate?.willingness === willingness) {
      if (presentation === 'legacy') return;
      if ((currentCandidate.reason ?? '') === reason.trim()) {
        setMutationError('目前已記錄相同意願與備註。');
        return false;
      }
    }
    if (
      saved?.status === 'applying'
      || saved?.status === 'observing'
      || saved?.status === 'observation_failed'
    ) return;
    setMutationError(null);
    let command: NonNullable<typeof saved>['command'];
    try {
      command = saved?.status === 'outcome_unknown'
        ? saved.command
        : (() => {
          const created = createCandidateWillingnessCommand(caseNo, candidateId, willingness, reason);
          return {
            caseNo: created.caseNo,
            candidateId: created.candidateId,
            willingness: created.willingness,
            reason: created.reason,
            expectedActor: created.actor,
            eventKey: created.eventKey,
          };
        })();
    } catch (error) {
      setMutationError(errorMessage(error));
      return;
    }
    const recoveringUnknown = saved?.status === 'outcome_unknown';
    orderMutationFlowStore.setCandidateWillingness(command.caseNo, {
      status: 'applying', command, receipt: null, error: null,
    });
    try {
      const receipt = await candidateContactPoolClient.recordWillingness({
        caseNo: command.caseNo,
        candidateId: command.candidateId,
        willingness: command.willingness,
        reason: command.reason,
        actor: command.expectedActor,
        eventKey: command.eventKey,
      });
      orderMutationFlowStore.setCandidateWillingness(command.caseNo, {
        status: 'observation_failed', command, receipt, error: null,
      });
      return await observeWillingness(command.candidateId);
    } catch (error) {
      const rejected = error instanceof ApiHttpError
        && error.status >= 400 && error.status < 500 && error.status !== 408 && error.status !== 429;
      if (rejected && !recoveringUnknown) {
        orderMutationFlowStore.clearCandidateWillingness(command.caseNo, command.candidateId);
        if (mounted.current && activeCaseNo.current === command.caseNo) {
          setMutationError(errorMessage(error));
        }
      } else {
        orderMutationFlowStore.setCandidateWillingness(command.caseNo, {
          status: 'outcome_unknown', command, receipt: null,
          error: recoveringUnknown
            ? '目前無法確認意願結果，請稍後確認目前回覆。'
            : '意願結果尚未確認；請確認目前回覆。',
        });
      }
    }
  };

  const retryWillingness = (candidateId: number) => {
    const current = orderMutationFlowStore.getCandidateWillingness(caseNo, candidateId);
    if (current?.status === 'outcome_unknown') {
      void submitWillingness(candidateId, current.command.willingness, current.command.reason);
    }
  };

  const retryWillingnessReadback = (candidateId: number) => {
    const current = orderMutationFlowStore.getCandidateWillingness(caseNo, candidateId);
    if (current?.status === 'observation_failed' && current.receipt) void observeWillingness(candidateId);
  };
  const originalResponse = state.status === 'ready' && responseTarget ? state.data.candidates.find(candidate => candidate.id === responseTarget.id) : undefined;
  const willingnessText = (value: string | undefined) => value === 'willing' ? '願意承接' : value === 'unwilling' ? '無意願' : '未回覆';
  useUnsavedChanges('人選回覆', [
    ...Object.entries(reasonDrafts).flatMap(([id, value]) => {
      const candidate = state.status === 'ready' ? state.data.candidates.find(item => item.id === Number(id)) : undefined;
      return value === (candidate?.reason ?? '') ? [] : [{ label: `人選 ${id} 回覆原因`, before: candidate?.reason || '未填寫', after: value || '未填寫' }];
    }),
    ...(responseTarget && willingnessText(responseChoice) !== willingnessText(originalResponse?.willingness)
      ? [{ label: `${responseTarget.name} 接案意願`, before: willingnessText(originalResponse?.willingness), after: willingnessText(responseChoice) }] : []),
  ], { busy: protectedOperation });

  const canUseDates = datesReady === true && dateEdit !== null && !datesDirty && !datesBusy && !protectedOperation;
  const confirmCandidateSend = async (candidate: CandidateContact) => {
    if (!canUseDates || !previewRequested || !previewDocuments || preparingSendRef.current) return;
    preparingSendRef.current = true;
    setPreparingSend(candidate.id);
    setSendError(null);
    try {
      const preview = await candidateContactPoolClient.previewInformationPackage(caseNo, candidate.id);
      if (!mounted.current || activeCaseNo.current !== caseNo) return;
      if (!preview.preview_fingerprint) throw new Error('請先保存每週服務說明的日期。');
      const sameDocuments = previewDocuments.every(part => JSON.stringify(part.line_sections) ===
        JSON.stringify(preview.documents.find(document => document.info_type === part.info_type)?.line_sections));
      const sameReply = !previewReply ||
        JSON.stringify([previewReply.reply_text, previewReply.reply_actions]) === JSON.stringify([preview.reply_text, preview.reply_actions]);
      if (!sameDocuments || !sameReply) {
        setPreviewMode('idle');
        throw new Error('案件資訊已更新，請重新核對預覽後再確認寄送。');
      }
      await submitInformation(createCandidateInformationSendCommand(caseNo, candidate.id, preview.preview_fingerprint));
    } catch (error) {
      if (mounted.current && activeCaseNo.current === caseNo) setSendError({ candidateId: candidate.id, message: errorMessage(error) });
    } finally {
      preparingSendRef.current = false;
      if (mounted.current) setPreparingSend(null);
    }
  };

  const renderInformationHistory = (candidate: CandidateContact) => {
    const history = ([1, 2, 3] as const).filter(kind => candidate.information[kind]);
    return history.length > 0 && <details className="candidate-package-history">
      <summary>查看分開寄送紀錄</summary>
      <dl>{history.map(kind => <div key={kind}>
        <dt>{CANDIDATE_INFORMATION_LABELS[kind]}</dt><dd>{deliveryStatus(candidate.information[kind], presentation === 'workbench')}</dd>
      </div>)}</dl>
    </details>;
  };
  const openInformation = (candidate: CandidateContact, resend: boolean) => {
    setMutationError(null);
    setSendError(null);
    setInformationTarget({ candidateId: candidate.id, resend });
  };
  const renderSendPreview = (candidate: CandidateContact) => {
    const openerId = `candidate-package-${caseNo}-${candidate.id}${informationTarget?.resend ? '-resend' : ''}`;
    const candidateSend = orderMutationFlowStore.getCandidateInformation(caseNo, candidate.id);
    return informationTarget?.candidateId === candidate.id && <OrderCandidateInformationSendPanel
      key={openerId} caseNo={caseNo} candidate={candidate} revision={informationRevision}
      blocked={informationTarget.resend ? candidateSend !== undefined && pendingStatus(candidateSend.status) : protectedOperation}
      datesReady={informationTarget.resend || presentation !== 'workbench' || canUseDates}
      resend={informationTarget.resend} onSubmit={submitInformation}
      sendError={sendError?.candidateId === candidate.id ? sendError.message : mutationError}
      onClose={() => { setMutationError(null); setInformationTarget(null); document.getElementById(openerId)?.focus(); }}
      onViewDates={() => presentation === 'workbench' ? setWeeklyOpen(true) : setSharedInformation({ kind: 3 })} />;
  };
  const renderInformation = (candidate: CandidateContact) => {
    const expanded = informationTarget?.candidateId === candidate.id;
    const openerId = `candidate-package-${caseNo}-${candidate.id}`;
    return <>
      <div className="candidate-package-entry">
        <div>
          <strong>寄送案件資訊</strong>
          <p>訂單資訊一、訂單資訊二、每週服務說明、共用回覆卡</p>
          {candidate.information.package && <p>{deliveryStatus(candidate.information.package, true)}</p>}
        </div>
        {!candidate.information.package && <button id={openerId} type="button" className="btn-primary-action"
          aria-expanded={expanded && !informationTarget?.resend}
          aria-label={`預覽並寄送（${candidate.staff_name}）`}
          disabled={candidate.status !== 'active' || protectedOperation}
          onClick={() => openInformation(candidate, false)}>預覽並寄送</button>}
        <button id={`${openerId}-resend`} type="button" className="btn-primary-action"
          aria-expanded={expanded && informationTarget?.resend === true}
          aria-label={`再次寄送（${candidate.staff_name}）`}
          onClick={() => openInformation(candidate, true)}>再次寄送</button>
      </div>
      {renderSendPreview(candidate)}
      {renderInformationHistory(candidate)}
    </>;
  };

  return (
    <section className="order-candidate-list" aria-label={`案件 ${caseNo} 候選聯絡狀態`}>
      {workbench && <section className="candidate-inquiry-step" aria-label="設定每週服務說明">
        <header className="candidate-package-header candidate-inquiry-step-heading">
          <h3>1. 設定每週服務說明</h3>
          <button type="button" aria-expanded={weeklyOpen} aria-controls={`${sectionId}-weekly`}
            aria-label={`${weeklyOpen ? '收起' : '展開'}每週服務說明設定`}
            onClick={() => setWeeklyOpen(open => !open)}>{weeklyOpen ? '收起' : '展開'}</button>
        </header>
        <div id={`${sectionId}-weekly`} hidden={!weeklyOpen}>
        {weeklyStartDate ? <fieldset className="candidate-weekly-editor" disabled={protectedOperation}><CandidatePlannedServiceDates key={caseNo} caseNo={caseNo} startDate={weeklyStartDate}
          onSharedPreview={setWeekly} onEditStateChange={setDateEdit} onSaved={() => {
            setPreviewMode('idle');
            setInformationRevision(value => value + 1);
            onObserved?.();
          }} /></fieldset>
          : datesReady === null && !dateLoadError ? <p role="status">正在讀取服務日期…</p>
          : !dateLoadError && <p role="status">請先確認案件的約定服務開始日。</p>}
        {dateLoadError && <p role="alert">{dateLoadError} <button type="button"
          onClick={() => setInformationRevision(value => value + 1)}>重新讀取服務日期</button></p>}
        {weekly && <CandidateWeeklyServiceTable weekly={weekly} />}
        </div>
      </section>}
      {workbench && <section className="candidate-information-send" aria-label="預覽案件資訊">
        <header className="candidate-package-header candidate-inquiry-step-heading">
          <h3>2. 預覽案件資訊</h3>
          <button type="button" aria-expanded={previewOpen} aria-controls={`${sectionId}-preview`}
            aria-label={`${previewOpen ? '收起' : '展開'}案件資訊預覽`}
            onClick={() => {
              if (!previewOpen && previewError) setInformationRevision(value => value + 1);
              setPreviewMode(previewOpen ? 'collapsed' : 'open');
            }}>{previewOpen ? '收起' : '展開'}</button>
        </header>
        <div id={`${sectionId}-preview`} hidden={!previewOpen}>
          {datesReady === true && !datesDirty && !datesBusy
            ? previewDocuments ? <CandidateInformationPages documents={previewDocuments} reply={previewReply} />
              : previewError ? <p role="alert">{previewError}</p> : <p role="status">正在讀取案件資訊…</p>
            : <p>保存每週服務說明後，即可預覽案件資訊。</p>}
        </div>
      </section>}
      {workbench && <header className="candidate-package-header candidate-inquiry-step-heading">
        <h3>3. 選擇月嫂</h3>
        <button type="button" aria-expanded={selectionOpen} aria-controls={`${sectionId}-selection`}
          aria-label={`${selectionOpen ? '收起' : '展開'}月嫂選擇`}
          onClick={() => setSelectionOpen(open => !open)}>{selectionOpen ? '收起' : '展開'}</button>
      </header>}
      <div id={workbench ? `${sectionId}-selection` : undefined} className={workbench ? 'candidate-selection-body' : undefined}
        hidden={workbench && !selectionOpen}>
      <header className="order-candidate-list-heading">{!workbench && <h3>候選月嫂</h3>}
      <div className="order-case-action-row">
      {presentation === 'workbench' && onAddCandidates && <button type="button" className="btn-primary-action"
        disabled={!canUseDates} onClick={onAddCandidates}>新增候選月嫂</button>}
      {(presentation !== 'workbench' || state.status === 'error') &&
      <button
        type="button"
        className="order-v2-open-drawer"
        onClick={loadStatus}
        disabled={state.status === 'loading' || mutationPending}
      >
        {state.status === 'loading' ? '讀取中…' : presentation === 'workbench' ? '重試讀取人選' : '重新讀取候選清單'}
      </button>}
      </div>
      </header>
      {state.status === 'idle' && <div className="order-case-empty"><h4>查看已加入的人選</h4><p>讀取候選清單以查看意願與聯絡紀錄；要加入人選，請切換「新增候選月嫂」。</p></div>}

      {mutationError !== null && responseTarget === null && informationTarget === null && <p className="order-v2-drawer-error" role="alert">{mutationError}</p>}

      {state.status === 'error' && (
        <div className="order-v2-notice blocked" role="alert">
          <strong>候選聯絡狀態不可用</strong>
          <span>{state.message}</span>
        </div>
      )}

      {candidateInformationFlows.map((information) => {
        const { command } = information;
        const candidateName = state.status === 'ready'
          ? (() => { const candidate = state.data.candidates.find(value => value.id === command.candidateId); return candidate ? staffDisplayLabel(candidate.staff_union_no, candidate.staff_name) : undefined; })()
          : undefined;
        const deliveryLabel = `${candidateName ? `${candidateName}的` : ''}寄送案件資訊`;
        if (information.status === 'outcome_unknown') return <div key={command.eventKey} className="order-v2-notice blocked" role="alert">
          <strong>{deliveryLabel}</strong>
          <span>{information.error}</span>
          <button type="button" onClick={() => retryInformation(command.candidateId)}>確認{deliveryLabel}結果</button>
        </div>;
        if (information.status === 'observation_failed') return <div key={command.eventKey} className="order-v2-notice blocked" role="alert">
          <strong>{deliveryLabel}</strong>
          <span>{information.error ?? '寄送任務已建立，尚不代表月嫂已收到；請重新讀取投遞狀態。'}</span>
          <button type="button" onClick={() => retryInformationReadback(command.candidateId)}>重新讀取{deliveryLabel}投遞狀態</button>
        </div>;
        return information.status === 'applying' || information.status === 'observing'
          ? <p key={command.eventKey} role="status">正在建立並確認案件資訊投遞任務…</p>
          : null;
      })}

      {state.status === 'ready' && state.data.candidates.length === 0 && (
        <div className="order-case-review-note" role="status">
          <strong>尚未加入候選月嫂</strong>
          {presentation === 'legacy' && onAddCandidates && <button type="button" className="btn-primary-action"
            onClick={onAddCandidates}>尋找並新增候選月嫂</button>}
        </div>
      )}

      {presentation === 'workbench' && datesReady === false &&
        <p>請先保存每週服務說明的日期。</p>}
      {presentation === 'workbench' && state.status === 'loading' && <p role="status">正在讀取人選…</p>}
      {workbench && visible && hasActiveCandidates && (availability === 'error'
        ? <p className="order-case-review-note" role="alert">目前無法查詢候選月嫂的檔期。{' '}
          <button type="button" onClick={() => setAvailabilityRevision(value => value + 1)}>重新查詢檔期</button></p>
        : !currentAvailability && <p role="status">正在查詢候選月嫂的檔期…</p>)}
      {state.status === 'ready' && state.data.candidates.length > 0 && (
        <>
          <div className="order-candidate-cards" aria-label="候選聯絡正式狀態">
            {[...state.data.candidates].sort((left, right) => compareStaffUnionNumbers(
              { id: left.staff_id, unionNo: left.staff_union_no },
              { id: right.staff_id, unionNo: right.staff_union_no },
            )).map((candidate) => {
              const willingnessFlow = orderMutationFlowStore.getCandidateWillingness(caseNo, candidate.id);
              const willingnessProtected = willingnessFlow?.status === 'applying'
                || willingnessFlow?.status === 'outcome_unknown'
                || willingnessFlow?.status === 'observation_failed'
                || willingnessFlow?.status === 'observing';
              const plannedPeriod = candidate.status === 'active' ? currentAvailability : null;
              const inquiryPeriodChanged = plannedPeriod !== null && (
                candidate.service_start_date !== plannedPeriod.planned_start_date
                || candidate.service_end_date !== plannedPeriod.planned_end_date
              );
              if (presentation === 'workbench') return <article className="order-candidate-card compact" key={candidate.id} id={`candidate-inquiry-${caseNo}-${candidate.id}`} tabIndex={-1}>
                <div className="candidate-card-identity"><h4>{staffDisplayLabel(candidate.staff_union_no, candidate.staff_name)}</h4><p>
                  {plannedPeriod ? `預計服務期間：${plannedPeriod.planned_start_date} ～ ${plannedPeriod.planned_end_date}`
                    : `詢問期間：${candidate.service_start_date} ～ ${candidate.service_end_date}`}
                </p>
                  <div className="candidate-card-actions">
                  <button type="button" aria-label={`手動記錄接案意願（${candidate.staff_name}）`} aria-expanded={responseTarget?.id === candidate.id}
                    aria-controls={`candidate-willingness-${caseNo}-${candidate.id}`} disabled={candidate.status !== 'active' || protectedOperation} onClick={() => {
                    if (responseTarget?.id === candidate.id) { setResponseTarget(null); return; }
                    setResponseTarget({ id: candidate.id, name: staffDisplayLabel(candidate.staff_union_no, candidate.staff_name) });
                    setResponseChoice(candidate.willingness === 'pending' ? '' : candidate.willingness);
                    setReasonDrafts(drafts => ({ ...drafts, [candidate.id]: drafts[candidate.id] ?? candidate.reason ?? '' }));
                    setMutationError(null);
                  }}>手動記錄接案意願</button>
                  <span className={`order-candidate-willingness ${candidate.willingness}`}>{inquiryPeriodChanged && candidate.willingness !== 'pending' && '原期間・'}{candidate.status === 'withdrawn' ? '已退出' : candidate.status === 'selected' ? '已選定' : candidate.willingness === 'pending' && !candidate.information.package && !candidate.information['1'] && !candidate.information['2'] ? '尚未詢問' : ({ pending: '待回覆', willing: '願意承接', unwilling: '無意願' })[candidate.willingness]}</span>
                  </div>
                </div>
                {plannedPeriod && <CandidateAvailabilityNotice availability={plannedPeriod} staffId={candidate.staff_id} showAdvisories={false} />}
                <div className="candidate-card-operations">
                  <CaregiverCommuteQuery caseNo={caseNo} staffId={candidate.staff_id} staffName={candidate.staff_name} compact />
                  <div className="candidate-card-footer">
                    {candidate.information.package && <p>{deliveryStatus(candidate.information.package, true)}</p>}
                    {candidate.status === 'active' && <>
                      {candidate.willingness === 'willing' && <button type="button" className="candidate-confirmation-link" disabled={protectedOperation} onClick={() => onOpenCustomerConfirmation?.(candidate.id)}>前往客戶確認準備 →</button>}
                      {!candidate.information.package && <button type="button" className="btn-primary-action"
                        aria-label={`確認寄送（${candidate.staff_name}）`} disabled={!canUseDates || !previewRequested || !previewDocuments}
                        onClick={() => { void confirmCandidateSend(candidate); }}>{preparingSend === candidate.id ? '寄送處理中…' : '確認寄送'}</button>}
                    </>}
                    <button id={`candidate-package-${caseNo}-${candidate.id}-resend`}
                      type="button" className="btn-primary-action" aria-expanded={informationTarget?.candidateId === candidate.id}
                      aria-label={`再次寄送（${candidate.staff_name}）`}
                      onClick={() => openInformation(candidate, true)}>再次寄送</button>
                  </div>
                </div>
                {candidate.information_changes && candidate.information_changes.length > 0 && <div className="order-v2-drawer-error" role="status">
                  <strong>資料已改變，請重新寄送確認意願</strong>
                  <ul>{candidate.information_changes.map((change, index) => <li key={index}>
                    <strong>{change.document}／{change.section}／{change.field}</strong>{' '}
                    <span>{change.before ?? '未列出'} → {change.after ?? '未列出'}</span>
                  </li>)}</ul>
                </div>}
                {renderInformationHistory(candidate)}
                {renderSendPreview(candidate)}
                {candidate.reason && <p>詢問備註：{candidate.reason}</p>}
                {responseTarget?.id === candidate.id && <form noValidate className="candidate-willingness-form" id={`candidate-willingness-${caseNo}-${candidate.id}`}
                  aria-label={`手動記錄接案意願（${candidate.staff_name}）`} onSubmit={event => {
                    event.preventDefault();
                    if (protectedOperation || !saveValidation.validate([
                      { value: responseChoice, label: '初步接案意願', ref: responseChoiceRef },
                    ]) || !responseChoice) return;
                    void submitWillingness(candidate.id, responseChoice, reasonDrafts[candidate.id] ?? '').then(saved => { if (saved) setResponseTarget(null); });
                  }}>
                  <h4>手動記錄接案意願</h4>
                  <fieldset disabled={protectedOperation}><legend>初步接案意願</legend>
                    <label><input ref={responseChoiceRef} type="radio" name="candidate-response" value="willing" required checked={responseChoice === 'willing'} onChange={() => setResponseChoice('willing')} />願意承接</label>
                    <label><input type="radio" name="candidate-response" value="unwilling" required checked={responseChoice === 'unwilling'} onChange={() => setResponseChoice('unwilling')} />無意願</label>
                    <label className="candidate-willingness-note">詢問結果備註<textarea ref={responseReasonRef} rows={3} maxLength={500} value={reasonDrafts[candidate.id] ?? ''}
                      onChange={event => setReasonDrafts(drafts => ({ ...drafts, [candidate.id]: event.target.value }))} /></label>
                    <p>備註選填。只記錄初步意願，尚未形成正式指派。</p>
                  </fieldset>
                  {saveValidation.feedback}
                  {mutationError && <p role="alert">{mutationError}</p>}
                  <div className="order-case-action-row">
                    <button type="submit" className="btn-primary-action" disabled={protectedOperation}>儲存接案意願</button>
                    <button type="button" disabled={protectedOperation} onClick={() => setResponseTarget(null)}>收起填寫</button>
                  </div>
                </form>}
                {(willingnessFlow?.status === 'applying' || willingnessFlow?.status === 'observing') && <p role="status">正在保存與確認詢問結果…</p>}
                {willingnessFlow?.status === 'outcome_unknown' && <p role="alert">{willingnessFlow.error}<button type="button" onClick={() => retryWillingness(candidate.id)}>確認目前回覆</button></p>}
                {willingnessFlow?.status === 'observation_failed' && <p role="alert">{willingnessFlow.error}<button type="button" onClick={() => retryWillingnessReadback(candidate.id)}>重新讀取最新結果</button></p>}
                {willingnessNotices[candidate.id] && <p role="status">{willingnessNotices[candidate.id]}</p>}
                {sendError?.candidateId === candidate.id && <p className="order-v2-drawer-error" role="alert">{sendError.message}</p>}
              </article>;
              return (
                <article className="order-candidate-card" key={candidate.id}>
                  <header><h4>{staffDisplayLabel(candidate.staff_union_no, candidate.staff_name)}</h4><span className={`order-candidate-willingness ${candidate.willingness}`}>{candidate.status === 'withdrawn' ? '已退出' : candidate.status === 'selected' ? '已選定' : ({ pending: '待回覆', willing: '願意承接', unwilling: '不願承接' })[candidate.willingness]}</span></header>
                  <p>{candidate.service_start_date} ～ {candidate.service_end_date}</p>
                  {candidate.reason && <p>回覆說明：{candidate.reason}</p>}
                  {renderInformation(candidate)}
                  <details open={focusWillingness || willingnessProtected || willingnessNotices[candidate.id] !== undefined}>
                    <summary>記錄電話或現場詢問結果</summary>
                    <label htmlFor={`candidate-${candidate.id}-willingness-reason`}>
                      詢問結果備註（{staffDisplayLabel(candidate.staff_union_no, candidate.staff_name)}）
                    </label>
                    <input
                      id={`candidate-${candidate.id}-willingness-reason`}
                      value={reasonDrafts[candidate.id] ?? ''}
                      maxLength={500}
                      disabled={willingnessProtected}
                      onChange={(event) => setReasonDrafts((current) => ({
                        ...current,
                        [candidate.id]: event.target.value,
                      }))}
                      placeholder="詢問結果備註（選填）"
                    />
                    <div className="order-case-action-row">
                      <button
                        type="button"
                        className="order-v2-open-drawer"
                        aria-label={`記錄 ${candidate.staff_name} 願意`}
                        disabled={willingnessProtected || candidate.status !== 'active' || candidate.willingness === 'willing'}
                        onClick={() => void submitWillingness(candidate.id, 'willing', reasonDrafts[candidate.id] ?? '')}
                      >
                        記錄願意
                      </button>
                      <button
                        type="button"
                        className="order-v2-open-drawer"
                        aria-label={`記錄 ${candidate.staff_name} 無意願`}
                        disabled={willingnessProtected || candidate.status !== 'active' || candidate.willingness === 'unwilling'}
                        onClick={() => void submitWillingness(candidate.id, 'unwilling', reasonDrafts[candidate.id] ?? '')}
                      >
                        記錄無意願
                      </button>
                    </div>
                    {(willingnessFlow?.status === 'applying' || willingnessFlow?.status === 'observing') && <p role="status">記錄人工意願／回讀中…</p>}
                    {willingnessFlow?.status === 'outcome_unknown' && (
                      <p className="order-v2-drawer-error" role="alert">
                        {willingnessFlow.error}
                        <button type="button" onClick={() => retryWillingness(candidate.id)}>確認目前回覆</button>
                      </p>
                    )}
                    {willingnessFlow?.status === 'observation_failed' && (
                      <p className="order-v2-drawer-error" role="alert">
                        {willingnessFlow.error ?? '目前無法確認回覆是否已儲存，請重新讀取最新結果。'}
                        <button type="button" onClick={() => retryWillingnessReadback(candidate.id)}>重新讀取最新結果</button>
                      </p>
                    )}
                    {willingnessNotices[candidate.id] && <p role="status">{willingnessNotices[candidate.id]}</p>}
                  </details>
                </article>
              );
            })}
          </div>
        </>
      )}
      </div>
      {sharedInformation && <OrderCandidateInformationPanel caseNo={caseNo} initialKind={sharedInformation.kind}
        onDatesSaved={() => { setInformationRevision(value => value + 1); onObserved?.(); }}
        onClose={() => { setSharedInformation(null); setInformationRevision(value => value + 1); }} />}
    </section>
  );
};

export default OrderCandidateContactStatusPanel;
