import { useUnsavedChanges } from './UnsavedChanges';
import { useSaveValidation } from './useSaveValidation';
import { useEffect, useRef, useState, type FC } from 'react';
import {
  candidateContactPoolClient,
  createCandidateInformationSendCommand,
  createCandidateWillingnessCommand,
  type CandidateContactPool,
  type CandidateInformationSendCommand,
  type CandidateInformationPreview,
  type CandidateInformationKind,
} from '../api/scheduling/candidate_contact_pool_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { OrderCandidateInformationPanel, OrderCandidateInformationSendPanel, CANDIDATE_INFORMATION_LABELS } from './OrderCandidateInformationPanel';
import { compareStaffUnionNumbers, staffDisplayLabel } from '../adapters/staff/staff_directory_adapter';
import { CaregiverCommuteQuery } from './CaregiverCommute';

interface OrderCandidateContactStatusPanelProps {
  caseNo: string;
  onObserved?: () => void;
  onAddCandidates?: () => void;
  focusWillingness?: boolean;
  onPreviewInformation?: (kind: 1 | 2) => void;
  revision?: number;
  onEditStateChange?: (state: { dirty: boolean; busy: boolean }) => void;
  presentation?: 'legacy' | 'workbench';
  onOpenCustomerConfirmation?: (candidateId: number) => void;
  focusedCandidateId?: number;
}

type ContactStatusState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: CandidateContactPool }
  | { status: 'error'; message: string };

type CandidateContact = CandidateContactPool['candidates'][number];

function CandidateInformationSend({ caseNo, candidateId, kind, recipientLabel, onClose, onSubmit }: {
  caseNo: string; candidateId: number; kind: 1 | 2; recipientLabel: string; onClose: () => void;
  onSubmit: (command: CandidateInformationSendCommand) => void;
}) {
  const [preview, setPreview] = useState<CandidateInformationPreview | null>(null);
  const [status, setStatus] = useState('loading');
  const [message, setMessage] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    candidateContactPoolClient.previewInformation(caseNo, candidateId, kind, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) {
        setPreview(data); setStatus('ready');
        onSubmit(createCandidateInformationSendCommand(caseNo, candidateId, kind, data.preview_fingerprint));
        onClose();
      } })
      .catch((error) => { if (!controller.signal.aborted) { setMessage(errorMessage(error)); setStatus('error'); } });
    return () => controller.abort();
  }, [caseNo, candidateId, kind]);
  return <section className="order-case-review-note" aria-label="寄送前確認">
    <h4>寄送訂單資訊－{kind}</h4>
    {status === 'loading' && <p role="status">正在讀取寄送內容…</p>}
    {preview && <><p>收件月嫂：{recipientLabel}；案件：{preview.case_no}</p><pre style={{ whiteSpace: 'pre-wrap', font: 'inherit' }}>{preview.text}</pre></>}
    {message && <p role={status === 'error' ? 'alert' : 'status'}>{message}</p>}
    <button type="button" onClick={onClose}>關閉</button>
  </section>;
}

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

export const OrderCandidateContactStatusPanel: FC<OrderCandidateContactStatusPanelProps> = ({ caseNo, onObserved, onAddCandidates, focusWillingness = false, revision = 0, onEditStateChange, presentation = 'legacy', onOpenCustomerConfirmation, focusedCandidateId }) => {
  const [state, setState] = useState<ContactStatusState>({ status: 'idle' });
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [sendPreview, setSendPreview] = useState<{ candidateId: number; kind: 1 | 2 } | null>(null);
  const [reasonDrafts, setReasonDrafts] = useState<Record<number, string>>({});
  const [willingnessNotices, setWillingnessNotices] = useState<Record<number, string>>({});
  const [sharedInformation, setSharedInformation] = useState<{ kind?: CandidateInformationKind } | null>(null);
  const [informationTarget, setInformationTarget] = useState<{ candidateId: number; kind: CandidateInformationKind } | null>(null);
  const [informationBusy, setInformationBusy] = useState(false);
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
  const focusedCandidate = useRef<string | null>(null);
  useEffect(() => {
    const identity = `${caseNo}:${focusedCandidateId}`;
    if (presentation === 'workbench' && focusedCandidateId !== undefined && state.status === 'ready' && focusedCandidate.current !== identity) {
      const card = document.getElementById(`candidate-inquiry-${caseNo}-${focusedCandidateId}`);
      if (card) { card.focus(); card.scrollIntoView({ block: 'nearest' }); focusedCandidate.current = identity; }
    }
  }, [caseNo, focusedCandidateId, state, presentation]);
  const candidateInformationFlows = orderMutationFlowStore.getCandidateInformationForCase(caseNo);
  const pendingStatus = (status: string) => ['applying', 'observing', 'outcome_unknown', 'observation_failed'].includes(status);
  const mutationPending = candidateInformationFlows.some((flow) => pendingStatus(flow.status))
    || orderMutationFlowStore.getCandidateWillingnessForCase(caseNo).some((flow) => pendingStatus(flow.status));
  const protectedOperation = mutationPending || informationBusy;
  const hasDraft = Object.values(reasonDrafts).some((value) => value.trim().length > 0);
  useEffect(() => { onEditStateChange?.({ dirty: hasDraft, busy: protectedOperation }); }, [hasDraft, protectedOperation, onEditStateChange]);
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
    void candidateContactPoolClient.query(requestedCaseNo, { signal: controller.signal })
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

  const loadStatus = () => {
    startStatusQuery(caseNo);
  };

  const observeInformation = async (command: CandidateInformationSendCommand) => {
    const current = orderMutationFlowStore.getCandidateInformation(
      command.caseNo, command.candidateId, command.infoType,
    );
    if (!current?.receipt) return;
    if (!mounted.current || activeCaseNo.current !== command.caseNo) return;
    const presentationGeneration = ++poolPresentationGeneration.current;
    orderMutationFlowStore.setCandidateInformation(command.caseNo, {
      ...current, status: 'observing', error: null,
    });
    try {
      const readback = await candidateContactPoolClient.query(command.caseNo);
      const candidates = readback.candidates.filter((candidate) => candidate.id === command.candidateId);
      const delivery = candidates[0]?.information[String(command.infoType) as '1' | '2' | '3'];
      if (readback.case_no !== command.caseNo || candidates.length !== 1 || !delivery) {
        throw new Error('寄送任務回讀與本次操作不一致。');
      }
      if (
        delivery.event_id !== current.receipt.event_id
        || delivery.line_task_id !== current.receipt.line_task_id
      ) {
        throw new Error('寄送結果與剛才的寄送不一致；請重新讀取投遞狀態。');
      }
      orderMutationFlowStore.clearCandidateInformation(
        command.caseNo, command.candidateId, command.infoType,
      );
      if (mounted.current && activeCaseNo.current === command.caseNo) {
        if (poolPresentationGeneration.current === presentationGeneration) {
          setState({ status: 'ready', data: readback });
        }
        onObserved?.();
      }
    } catch (error) {
      const saved = orderMutationFlowStore.getCandidateInformation(
        command.caseNo, command.candidateId, command.infoType,
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
      command.caseNo, command.candidateId, command.infoType,
    );
    if (informationInFlight.current.has(key) || current?.status === 'applying' || current?.status === 'observing') return;
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
        orderMutationFlowStore.clearCandidateInformation(command.caseNo, command.candidateId, command.infoType);
        if (mounted.current && activeCaseNo.current === command.caseNo) {
          setMutationError(errorMessage(error));
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

  const retryInformation = (candidateId: number, infoType: CandidateInformationKind) => {
    const current = orderMutationFlowStore.getCandidateInformation(caseNo, candidateId, infoType);
    if (current?.status === 'outcome_unknown') void submitInformation(current.command);
  };

  const retryInformationReadback = (candidateId: number, infoType: CandidateInformationKind) => {
    const current = orderMutationFlowStore.getCandidateInformation(caseNo, candidateId, infoType);
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
      const readback = await candidateContactPoolClient.query(command.caseNo, { signal: controller.signal });
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


  return (
    <section className="order-candidate-list" aria-label={`案件 ${caseNo} 候選聯絡狀態`}>
      <header className="order-candidate-list-heading"><div><h3>候選月嫂</h3><p>人選、聯絡紀錄與回覆集中在這裡。</p></div>
      <div className="order-case-action-row">{presentation === 'workbench' && <>
        <button type="button" disabled={protectedOperation} onClick={() => setSharedInformation({})}>查看訂單資訊</button>
        <button type="button" className="btn-primary-action" disabled={protectedOperation} onClick={onAddCandidates}>新增候選月嫂</button>
      </>}
      <button
        type="button"
        className="order-v2-open-drawer"
        onClick={loadStatus}
        disabled={state.status === 'loading' || sendPreview !== null}
      >
        {state.status === 'loading' ? '讀取中…' : '重新讀取候選清單'}
      </button>
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
        const deliveryLabel = `${candidateName ? `${candidateName}的` : ''}寄送資訊－${command.infoType}`;
        if (information.status === 'outcome_unknown') return <div key={command.eventKey} className="order-v2-notice blocked" role="alert">
          <strong>{deliveryLabel}</strong>
          <span>{information.error}</span>
          <button type="button" onClick={() => retryInformation(command.candidateId, command.infoType)}>確認{deliveryLabel}結果</button>
        </div>;
        if (information.status === 'observation_failed') return <div key={command.eventKey} className="order-v2-notice blocked" role="alert">
          <strong>{deliveryLabel}</strong>
          <span>{information.error ?? '寄送任務已建立，尚不代表月嫂已收到；請重新讀取投遞狀態。'}</span>
          <button type="button" onClick={() => retryInformationReadback(command.candidateId, command.infoType)}>重新讀取{deliveryLabel}投遞狀態</button>
        </div>;
        return information.status === 'applying' || information.status === 'observing'
          ? <p key={command.eventKey} role="status">寄送資訊－{command.infoType} 建立／回讀中…</p>
          : null;
      })}

      {state.status === 'ready' && state.data.candidates.length === 0 && (
        <div className="order-case-review-note" role="status">
          <strong>尚未加入候選月嫂</strong>
          <p>查詢合適人選，加入清單後即可寄送資訊與記錄回覆。</p>
          {onAddCandidates && <button type="button" className="btn-primary-action" onClick={onAddCandidates}>尋找並新增候選月嫂</button>}
        </div>
      )}

      {state.status === 'ready' && state.data.candidates.length > 0 && (
        <>
          <div className="order-v2-case-meta">
            <span>共 {state.data.candidates.length} 位人選</span>
          </div>
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
              const informationOne = orderMutationFlowStore.getCandidateInformation(caseNo, candidate.id, 1);
              const informationTwo = orderMutationFlowStore.getCandidateInformation(caseNo, candidate.id, 2);
              if (presentation === 'workbench') return <article className="order-candidate-card compact" key={candidate.id} id={`candidate-inquiry-${caseNo}-${candidate.id}`} tabIndex={-1}>
                <div className="candidate-card-identity"><h4>{staffDisplayLabel(candidate.staff_union_no, candidate.staff_name)}</h4><p>{candidate.service_start_date} ～ {candidate.service_end_date}</p>
                  <span className={`order-candidate-willingness ${candidate.willingness}`}>{candidate.status === 'withdrawn' ? '已退出' : candidate.status === 'selected' ? '已選定' : candidate.willingness === 'pending' && !candidate.information['1'] && !candidate.information['2'] ? '尚未詢問' : ({ pending: '待回覆', willing: '願意承接', unwilling: '無意願' })[candidate.willingness]}</span>
                </div>
                <CaregiverCommuteQuery caseNo={caseNo} staffId={candidate.staff_id} staffName={candidate.staff_name} />
                <dl className="order-candidate-delivery">{([1, 2, 3] as const).map(value => <div key={value}>
                  <dt>{CANDIDATE_INFORMATION_LABELS[value]}</dt><dd><span>{deliveryStatus(candidate.information[String(value) as '1' | '2' | '3'], true)}</span>
                  <button type="button" aria-label={`寄送${CANDIDATE_INFORMATION_LABELS[value]}給 ${candidate.staff_name}`}
                    disabled={candidate.status !== 'active' || protectedOperation} onClick={() => { setMutationError(null); setInformationTarget({ candidateId: candidate.id, kind: value }); }}>寄送</button></dd>
                </div>)}</dl>
                {informationTarget?.candidateId === candidate.id && <OrderCandidateInformationSendPanel
                  key={`${caseNo}:${candidate.id}:${informationTarget.kind}`} caseNo={caseNo} candidate={candidate} kind={informationTarget.kind}
                  revision={informationRevision} blocked={mutationPending} onSubmit={submitInformation} onClose={() => setInformationTarget(null)}
                  onBusyChange={setInformationBusy} onViewInformation={kind => setSharedInformation({ kind })} sendError={mutationError} />}
                {candidate.reason && <p>詢問備註：{candidate.reason}</p>}
                <div className="order-case-action-row">
                  <button type="button" aria-label={`手動記錄接案意願（${candidate.staff_name}）`} aria-expanded={responseTarget?.id === candidate.id}
                    aria-controls={`candidate-willingness-${caseNo}-${candidate.id}`} disabled={candidate.status !== 'active' || protectedOperation} onClick={() => {
                    if (responseTarget?.id === candidate.id) { setResponseTarget(null); return; }
                    setResponseTarget({ id: candidate.id, name: staffDisplayLabel(candidate.staff_union_no, candidate.staff_name) });
                    setResponseChoice(candidate.willingness === 'pending' ? '' : candidate.willingness);
                    setReasonDrafts(drafts => ({ ...drafts, [candidate.id]: drafts[candidate.id] ?? candidate.reason ?? '' }));
                    setMutationError(null);
                  }}>手動記錄接案意願</button>
                  {candidate.willingness === 'willing' && candidate.status === 'active' && <button type="button" className="candidate-confirmation-link" disabled={protectedOperation} onClick={() => onOpenCustomerConfirmation?.(candidate.id)}>前往客戶確認準備 →</button>}
                </div>
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
              </article>;
              return (
                <article className="order-candidate-card" key={candidate.id}>
                  <header><h4>{staffDisplayLabel(candidate.staff_union_no, candidate.staff_name)}</h4><span className={`order-candidate-willingness ${candidate.willingness}`}>{candidate.status === 'withdrawn' ? '已退出' : candidate.status === 'selected' ? '已選定' : ({ pending: '待回覆', willing: '願意承接', unwilling: '不願承接' })[candidate.willingness]}</span></header>
                  <p>{candidate.service_start_date} ～ {candidate.service_end_date}</p>
                  {candidate.reason && <p>回覆說明：{candidate.reason}</p>}
                  <dl className="order-candidate-delivery"><div><dt>訂單資訊－1</dt><dd>{deliveryStatus(candidate.information['1'])}</dd></div><div><dt>訂單資訊－2</dt><dd>{deliveryStatus(candidate.information['2'])}</dd></div></dl>
                  <div className="order-case-action-row">
                    <button type="button" className="order-v2-open-drawer" disabled={candidate.status !== 'active' || sendPreview !== null || informationOne !== undefined} onClick={() => setSendPreview({ candidateId: candidate.id, kind: 1 })}>寄送訂單資訊－1</button>
                    <button type="button" className="order-v2-open-drawer" disabled={candidate.status !== 'active' || sendPreview !== null || informationTwo !== undefined} onClick={() => setSendPreview({ candidateId: candidate.id, kind: 2 })}>寄送訂單資訊－2</button>
                  </div>
                  {sendPreview?.candidateId === candidate.id && <CandidateInformationSend
                    key={`${caseNo}:${candidate.id}:${sendPreview.kind}`} caseNo={caseNo} candidateId={candidate.id} kind={sendPreview.kind} recipientLabel={staffDisplayLabel(candidate.staff_union_no, candidate.staff_name)}
                    onClose={() => setSendPreview(null)} onSubmit={(command) => { void submitInformation(command); }} />}
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
      {presentation === 'workbench' && sharedInformation && <OrderCandidateInformationPanel caseNo={caseNo} initialKind={sharedInformation.kind}
        onDatesSaved={onObserved}
        onClose={() => { setSharedInformation(null); setInformationRevision(value => value + 1); }} />}
    </section>
  );
};

export default OrderCandidateContactStatusPanel;
