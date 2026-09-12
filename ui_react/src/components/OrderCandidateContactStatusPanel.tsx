import { useEffect, useRef, useState, type FC } from 'react';
import {
  candidateContactPoolClient,
  createCandidateInformationSendCommand,
  createCandidateWillingnessCommand,
  type CandidateContactPool,
  type CandidateInformationSendCommand,
  type CandidateInformationPreview,
} from '../api/scheduling/candidate_contact_pool_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';

interface OrderCandidateContactStatusPanelProps {
  caseNo: string;
  onObserved?: () => void;
  onPreviewInformation?: (kind: 1 | 2) => void;
  revision?: number;
}

type ContactStatusState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: CandidateContactPool }
  | { status: 'error'; message: string };

type CandidateContact = CandidateContactPool['candidates'][number];

function CandidateInformationSend({ caseNo, candidateId, kind, onClose, onSubmit }: {
  caseNo: string; candidateId: number; kind: 1 | 2; onClose: () => void;
  onSubmit: (command: CandidateInformationSendCommand) => void;
}) {
  const [preview, setPreview] = useState<CandidateInformationPreview | null>(null);
  const [status, setStatus] = useState('loading');
  const [message, setMessage] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    candidateContactPoolClient.previewInformation(caseNo, candidateId, kind, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) { setPreview(data); setStatus('ready'); } })
      .catch((error) => { if (!controller.signal.aborted) { setMessage(errorMessage(error)); setStatus('error'); } });
    return () => controller.abort();
  }, [caseNo, candidateId, kind]);
  const send = async () => {
    if (!preview || status !== 'ready') return;
    try {
      onSubmit(createCandidateInformationSendCommand(
        caseNo, candidateId, kind, preview.preview_fingerprint,
      ));
      onClose();
    } catch (error) {
      setStatus('error');
      setMessage(errorMessage(error));
    }
  };
  return <section className="order-case-review-note" aria-label="寄送前確認">
    <h4>寄送訂單資訊－{kind}</h4>
    {status === 'loading' && <p role="status">正在讀取寄送內容…</p>}
    {preview && <><p>收件月嫂：{preview.staff_name}；案件：{preview.case_no}</p><pre style={{ whiteSpace: 'pre-wrap', font: 'inherit' }}>{preview.text}</pre></>}
    {message && <p role={status === 'error' ? 'alert' : 'status'}>{message}</p>}
    <button type="button" disabled={status !== 'ready'} onClick={() => void send()}>確認寄送</button>
    <button type="button" onClick={onClose}>關閉</button>
  </section>;
}

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '候選聯絡狀態查詢失敗';
}

function deliveryStatus(
  delivery: CandidateContact['information']['1'] | CandidateContact['information']['2'],
): string {
  if (delivery === null) return '尚無紀錄';
  const labels = { queued: '等待發送', pending: '處理中', sent: '已發送', manually_confirmed: '已人工確認', retryable_failed: '發送未完成', failed: '發送失敗', cancelled: '已取消發送' };
  return `${labels[delivery.status]} · ${delivery.sent_at}`;
}

export const OrderCandidateContactStatusPanel: FC<OrderCandidateContactStatusPanelProps> = ({ caseNo, onObserved, revision = 0 }) => {
  const [state, setState] = useState<ContactStatusState>({ status: 'idle' });
  const [sendPreview, setSendPreview] = useState<{ candidateId: number; kind: 1 | 2 } | null>(null);
  const [reasonDrafts, setReasonDrafts] = useState<Record<number, string>>({});
  const [willingnessNotices, setWillingnessNotices] = useState<Record<number, string>>({});
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
  const candidateInformationFlows = orderMutationFlowStore.getCandidateInformationForCase(caseNo);
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
      const delivery = candidates[0] && (command.infoType === 1
        ? candidates[0].information['1']
        : candidates[0].information['2']);
      if (readback.case_no !== command.caseNo || candidates.length !== 1 || delivery === null) {
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
    orderMutationFlowStore.setCandidateInformation(command.caseNo, {
      status: 'applying', command, receipt: null, error: null,
    });
    try {
      const receipt = await candidateContactPoolClient.sendInformation(command);
      orderMutationFlowStore.setCandidateInformation(command.caseNo, {
        status: 'observation_failed', command, receipt, error: null,
      });
      await observeInformation(command);
    } catch (error) {
      const rejected = error instanceof ApiHttpError
        && error.status >= 400 && error.status < 500 && error.status !== 408 && error.status !== 429;
      if (rejected && !recoveringUnknown) {
        orderMutationFlowStore.clearCandidateInformation(command.caseNo, command.candidateId, command.infoType);
      } else {
        orderMutationFlowStore.setCandidateInformation(command.caseNo, {
          status: 'outcome_unknown', command, receipt: null,
          error: recoveringUnknown
            ? '目前無法確認寄送結果，請稍後重新讀取投遞狀態。'
            : '寄送結果尚未確認；請確認寄送結果。',
        });
      }
    } finally {
      informationInFlight.current.delete(key);
    }
  };

  const retryInformation = (candidateId: number, infoType: 1 | 2) => {
    const current = orderMutationFlowStore.getCandidateInformation(caseNo, candidateId, infoType);
    if (current?.status === 'outcome_unknown') void submitInformation(current.command);
  };

  const retryInformationReadback = (candidateId: number, infoType: 1 | 2) => {
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
        onObserved?.();
      }
      orderMutationFlowStore.clearCandidateWillingness(command.caseNo, command.candidateId);
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
    if (saved?.status !== 'outcome_unknown' && currentCandidate?.willingness === willingness) return;
    if (
      saved?.status === 'applying'
      || saved?.status === 'observing'
      || saved?.status === 'observation_failed'
    ) return;
    const command = saved?.status === 'outcome_unknown'
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
      await observeWillingness(command.candidateId);
    } catch (error) {
      const rejected = error instanceof ApiHttpError
        && error.status >= 400 && error.status < 500 && error.status !== 408 && error.status !== 429;
      if (rejected && !recoveringUnknown) {
        orderMutationFlowStore.clearCandidateWillingness(command.caseNo, command.candidateId);
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

  return (
    <section className="order-candidate-list" aria-label={`案件 ${caseNo} 候選聯絡狀態`}>
      <header className="order-candidate-list-heading"><div><h3>候選月嫂</h3><p>人選、聯絡紀錄與回覆集中在這裡，不必切換不同候選池。</p></div>
      <button
        type="button"
        className="order-v2-open-drawer"
        onClick={loadStatus}
        disabled={state.status === 'loading' || sendPreview !== null}
      >
        {state.status === 'loading' ? '讀取中…' : '重新讀取候選清單'}
      </button>
      </header>
      {state.status === 'idle' && <div className="order-case-empty"><h4>查看已加入的人選</h4><p>讀取候選清單以查看意願與聯絡紀錄；要加入人選，請切換「新增候選月嫂」。</p></div>}

      {state.status === 'error' && (
        <div className="order-v2-notice blocked" role="alert">
          <strong>候選聯絡狀態不可用</strong>
          <span>{state.message}</span>
        </div>
      )}

      {candidateInformationFlows.map((information) => {
        const { command } = information;
        const candidateName = state.status === 'ready'
          ? state.data.candidates.find((candidate) => candidate.id === command.candidateId)?.staff_name
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
        <div className="order-v2-notice blocked" role="status">
          <strong>尚未加入候選月嫂</strong>
          <span>請先從「新增候選月嫂」查詢並選擇人選。</span>
        </div>
      )}

      {state.status === 'ready' && state.data.candidates.length > 0 && (
        <>
          <div className="order-v2-case-meta">
            <span>共 {state.data.candidates.length} 位人選</span>
          </div>
          <div className="order-candidate-cards" aria-label="候選聯絡正式狀態">
            {state.data.candidates.map((candidate) => {
              const willingnessFlow = orderMutationFlowStore.getCandidateWillingness(caseNo, candidate.id);
              const willingnessProtected = willingnessFlow?.status === 'applying'
                || willingnessFlow?.status === 'outcome_unknown'
                || willingnessFlow?.status === 'observation_failed'
                || willingnessFlow?.status === 'observing';
              const informationOne = orderMutationFlowStore.getCandidateInformation(caseNo, candidate.id, 1);
              const informationTwo = orderMutationFlowStore.getCandidateInformation(caseNo, candidate.id, 2);
              return (
                <article className="order-candidate-card" key={candidate.id}>
                  <header><h4>{candidate.staff_name}</h4><span className={`order-candidate-willingness ${candidate.willingness}`}>{candidate.status === 'withdrawn' ? '已退出' : candidate.status === 'selected' ? '已選定' : ({ pending: '待回覆', willing: '願意承接', unwilling: '不願承接' })[candidate.willingness]}</span></header>
                  <p>{candidate.service_start_date} ～ {candidate.service_end_date}</p>
                  {candidate.reason && <p>回覆說明：{candidate.reason}</p>}
                  <dl className="order-candidate-delivery"><div><dt>訂單資訊－1</dt><dd>{deliveryStatus(candidate.information['1'])}</dd></div><div><dt>訂單資訊－2</dt><dd>{deliveryStatus(candidate.information['2'])}</dd></div></dl>
                  <div className="order-case-action-row">
                    <button type="button" className="order-v2-open-drawer" disabled={candidate.status !== 'active' || sendPreview !== null || informationOne !== undefined} onClick={() => setSendPreview({ candidateId: candidate.id, kind: 1 })}>寄送訂單資訊－1</button>
                    <button type="button" className="order-v2-open-drawer" disabled={candidate.status !== 'active' || sendPreview !== null || informationTwo !== undefined} onClick={() => setSendPreview({ candidateId: candidate.id, kind: 2 })}>寄送訂單資訊－2</button>
                  </div>
                  {sendPreview?.candidateId === candidate.id && <CandidateInformationSend
                    key={`${caseNo}:${candidate.id}:${sendPreview.kind}`} caseNo={caseNo} candidateId={candidate.id} kind={sendPreview.kind}
                    onClose={() => setSendPreview(null)} onSubmit={(command) => { void submitInformation(command); }} />}
                  <details open={willingnessProtected || willingnessNotices[candidate.id] !== undefined}>
                    <summary>記錄電話或現場詢問結果</summary>
                    <label htmlFor={`candidate-${candidate.id}-willingness-reason`}>
                      詢問結果備註（{candidate.staff_name}）
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
                      placeholder="無意願時必填；願意可留空"
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
    </section>
  );
};

export default OrderCandidateContactStatusPanel;
