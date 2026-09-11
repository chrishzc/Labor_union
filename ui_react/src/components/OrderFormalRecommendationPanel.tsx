import { useEffect, useRef, useState, type FC } from 'react';
import { candidateContactPoolClient, type CandidateContactPool } from '../api/scheduling/candidate_contact_pool_client';
import { matchingCandidateWorkflowClient } from '../api/scheduling/matching_candidate_workflow_client';
import { matchingPlanCommunicationClient, type FormalPlanContactState } from '../api/scheduling/matching_plan_communication_client';
import { waitingDepositLockClient, type ActiveWaitingDepositPlan, type WaitingDepositPreview } from '../api/scheduling/waiting_deposit_lock_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { CustomerProfilesManualActions } from './MatchingManualCommunicationActions';
import { HolidayWorkAgreementActions } from './HolidayWorkAgreementActions';

interface OrderFormalRecommendationPanelProps {
  caseNo: string;
  onObserved?: () => void;
}

type ReadState<T> =
  | { status: 'idle' | 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string };
type CurrentPlan = { plan: ActiveWaitingDepositPlan; contact: FormalPlanContactState };
type CandidateContact = CandidateContactPool['candidates'][number];

function profileStatusLabel(status: string | null): string {
  if (status === null) return '尚未寄送';
  if (status === 'pending') return '等待系統寄送';
  if (status === 'processing') return '寄送中';
  if (status === 'sent' || status === 'manually_confirmed') return '履歷已送達';
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

export const OrderFormalRecommendationPanel: FC<OrderFormalRecommendationPanelProps> = ({ caseNo, onObserved }) => {
  const [candidates, setCandidates] = useState<ReadState<CandidateContactPool>>({ status: 'idle' });
  const [active, setActive] = useState<ReadState<CurrentPlan | null>>({ status: 'loading' });
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const sequence = useRef(0);
  const activeCase = useRef<string | null>(null);
  const [willingnessReason, setWillingnessReason] = useState('');
  const [decisionReason, setDecisionReason] = useState('');
  const [resumeNote, setResumeNote] = useState('請查收正式推薦月嫂履歷。');
  const [lockPreview, setLockPreview] = useState<WaitingDepositPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const request = ++sequence.current;
    activeCase.current = caseNo;
    setActive({ status: 'loading' });
    setCandidates({ status: 'idle' });
    setWillingnessReason('');
    setDecisionReason('');
    setResumeNote('請查收正式推薦月嫂履歷。');
    setLockPreview(null);
    setError(null);
    setNotice(null);
    void readCurrentPlan(caseNo)
      .then((data) => { if (sequence.current === request) setActive({ status: 'ready', data }); })
      .catch((caught) => { if (sequence.current === request) setActive({ status: 'error', message: errorMessage(caught) }); });
    return () => { activeCase.current = null; sequence.current += 1; };
  }, [caseNo]);

  const reload = async () => {
    if (busyRef.current) return;
    const request = ++sequence.current;
    setActive({ status: 'loading' });
    setLockPreview(null);
    setError(null);
    try {
      const data = await readCurrentPlan(caseNo);
      if (sequence.current === request) setActive({ status: 'ready', data });
    } catch (caught) {
      if (sequence.current === request) setActive({ status: 'error', message: errorMessage(caught) });
    }
  };

  const loadCandidates = async () => {
    const request = sequence.current;
    setCandidates({ status: 'loading' });
    try {
      const data = await candidateContactPoolClient.query(caseNo);
      if (data.case_no !== caseNo) throw new Error('候選池案件識別不一致。');
      if (sequence.current === request) setCandidates({ status: 'ready', data });
    } catch (caught) {
      if (sequence.current === request) setCandidates({ status: 'error', message: errorMessage(caught) });
    }
  };

  const current = active.status === 'ready' ? active.data : null;
  const currentSegments = current?.plan.segments ?? [];
  const canCreate = active.status === 'ready' && (current === null
    || (current.plan.activeLockId === null && current.plan.status === 'proposed' && current.contact.customer_decision !== 'accepted'));
  const canCommunicate = current !== null && current.plan.activeLockId === null
    && current.contact.plan.status === 'proposed' && current.contact.customer_decision === 'pending';

  const perform = async (operation: () => Promise<void>) => {
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
        setLockPreview(null);
        setError(errorMessage(caught));
        // No blind retry after a write or a failed readback. Reload the owner first.
        setActive({ status: 'error', message: '請重新讀取目前正式方案後再操作。' });
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
    setLockPreview(null);
    setNotice(message);
    onObserved?.();
  };

  const createPlan = (candidate: CandidateContact) => perform(async () => {
    if (!canCreate || candidate.status !== 'active' || candidate.willingness !== 'willing') return;
    const request = sequence.current;
    const [existing, detail] = await Promise.all([readCurrentPlan(caseNo), ordersQueryClient.getOrderDetail(caseNo)]);
    if (activeCase.current !== caseNo || sequence.current !== request) return;
    if (detail.case_no !== caseNo || !['洽談中', '訂單成立'].includes(detail.order_status)
      || (existing !== null && (existing.plan.activeLockId !== null || existing.plan.status === 'accepted'
        || existing.contact.customer_decision === 'accepted'))) {
      throw new Error('目前案件或正式方案已鎖定，不可重新建立媒合方案。');
    }
    const receipt = await matchingCandidateWorkflowClient.createSingleCaregiverPlan(caseNo, {
      staff_id: candidate.staff_id,
      start_date: candidate.service_start_date,
      end_date: candidate.service_end_date,
    });
    await observe(receipt.plan_id, () => true, `正式媒合方案已建立：#${receipt.plan_id}`);
  });

  const sendProfiles = () => perform(async () => {
    const fresh = await freshVisiblePlan();
    if (fresh.plan.activeLockId !== null || fresh.contact.plan.status !== 'proposed'
      || fresh.contact.customer_decision !== 'pending' || !fresh.contact.all_willing
      || fresh.contact.customer_profiles_status !== null || !resumeNote.trim()) {
      throw new Error('目前方案尚不可寄送或已有履歷任務，請依正式聯繫狀態續辦。');
    }
    const receipt = await matchingPlanCommunicationClient.sendCustomerProfiles(
      caseNo, fresh.plan.planId, fresh.contact.plan.communication_version, resumeNote.trim(),
    );
    await observe(fresh.plan.planId, (data) => data.contact.customer_profiles_status !== null,
      `履歷發送工作已建立：#${receipt.intent_id}（狀態：${profileStatusLabel(receipt.delivery_status)}）；尚不代表 LINE 已送達。`);
  });

  const recordWillingness = (segmentId: number) => perform(async () => {
    const fresh = await freshVisiblePlan();
    if (fresh.plan.activeLockId !== null || fresh.contact.plan.status !== 'proposed'
      || fresh.contact.customer_decision !== 'pending'
      || !fresh.contact.segments.some((segment) => segment.segment_id === segmentId && segment.willingness === 'pending')
      || !willingnessReason.trim()) throw new Error('目前區段不可補登意願。');
    await matchingPlanCommunicationClient.recordFormalPlanWillingness(
      caseNo, fresh.plan.planId, segmentId, fresh.contact.plan.communication_version, willingnessReason.trim(),
    );
    await observe(fresh.plan.planId,
      (data) => data.contact.segments.some((segment) => segment.segment_id === segmentId && segment.willingness === 'willing'),
      '正式方案月嫂意願已回讀確認。');
  });

  const recordDecision = (decision: 'accepted' | 'declined') => perform(async () => {
    const fresh = await freshVisiblePlan();
    if (fresh.plan.activeLockId !== null || fresh.contact.plan.status !== 'proposed'
      || fresh.contact.customer_decision !== 'pending' || !fresh.contact.all_willing
      || fresh.contact.customer_profiles_status === null || !decisionReason.trim()) {
      throw new Error('目前正式方案不可記錄客戶決定。');
    }
    await matchingPlanCommunicationClient.recordCustomerDecision(
      caseNo, fresh.plan.planId, fresh.contact.plan.communication_version, decision, decisionReason.trim(),
    );
    await observe(fresh.plan.planId, (data) => data.contact.customer_decision === decision, '客戶決定已完成正式回讀。');
  });

  const previewLock = () => perform(async () => {
    const fresh = await freshVisiblePlan();
    if (fresh.contact.customer_decision !== 'accepted' || fresh.plan.activeLockId !== null) {
      throw new Error('僅已接受且尚未鎖定的正式方案可建立等待訂金鎖。');
    }
    const request = sequence.current;
    const preview = await waitingDepositLockClient.preview(caseNo, fresh.plan.planId);
    if (preview.case_no !== caseNo || preview.plan_id !== fresh.plan.planId) throw new Error('等待訂金鎖 Preview identity 不一致，已停止套用。');
    if (activeCase.current === caseNo && sequence.current === request) setLockPreview(preview);
  });

  const applyLock = () => perform(async () => {
    if (!lockPreview?.apply_allowed) return;
    const fresh = await freshVisiblePlan();
    if (fresh.contact.customer_decision !== 'accepted' || fresh.plan.activeLockId !== null || fresh.plan.planId !== lockPreview.plan_id) {
      throw new Error('等待訂金鎖方案已變更，請重新預覽。');
    }
    const receipt = await waitingDepositLockClient.apply(caseNo, lockPreview.plan_id, lockPreview.preview_fingerprint);
    if (receipt.case_no !== caseNo || receipt.plan_id !== fresh.plan.planId) throw new Error('等待訂金鎖 receipt identity 不一致。');
    await observe(receipt.plan_id, (data) => data.plan.activeLockId === receipt.lock_id,
      `等待訂金鎖已套用：Lock #${receipt.lock_id} · ${receipt.result}`);
  });

  const pendingWillingnessCount = current?.contact.segments.filter(
    (segment) => segment.willingness === 'pending',
  ).length ?? 0;
  const visibleStatus = current === null
    ? '尚未選定月嫂'
    : current.contact.customer_decision !== 'pending'
      ? decisionLabel(current.contact.customer_decision)
      : pendingWillingnessCount > 0
        ? `待確認 ${pendingWillingnessCount} 位月嫂意願`
        : profileStatusLabel(current.contact.customer_profiles_status);

  return (
    <section className="formal-recommendation" aria-label={`案件 ${caseNo} 正式推薦媒合方案`}>
      {active.status === 'loading' && <p role="status">讀取目前正式方案中…</p>}
      {active.status === 'error' && (
        <div role="alert">
          <strong>目前無法讀取推薦進度</strong>
          <p>{active.message}</p>
          <button type="button" disabled={busy} onClick={() => void reload()}>再試一次</button>
        </div>
      )}
      {active.status === 'ready' && current === null && (
        <div className="formal-recommendation-empty">
          <strong>尚未選定正式推薦月嫂</strong>
          <p>從下方候選人中選擇一位已確認願意承接的月嫂。</p>
        </div>
      )}
      {current !== null && (
        <fieldset disabled={busy} className="formal-recommendation-plan">
          <legend className="sr-only">目前正式推薦方案</legend>
          <header className="formal-recommendation-summary">
            <div>
              <p className="formal-recommendation-eyebrow">目前正式媒合方案：#{current.plan.planId}</p>
              <h3>{currentSegments.length === 1 ? `月嫂 #${currentSegments[0].staffId}` : `${currentSegments.length} 位月嫂共同服務`}</h3>
              <p>{currentSegments.map((segment) => `${segment.assignedStartDate}－${segment.assignedEndDate}`).join('、')}</p>
            </div>
            <span className="formal-recommendation-status" role="status">{visibleStatus}</span>
          </header>

          {current.contact.customer_decision === 'declined' && (
            <div role="alert"><strong>客戶拒絕正式推薦</strong><p>目前方案無法繼續，請先確認客戶需求及後續人選。</p></div>
          )}

          {canCommunicate && pendingWillingnessCount > 0 && (
            <section className="formal-recommendation-next" aria-labelledby={`willingness-${current.plan.planId}`}>
              <p className="formal-recommendation-step">下一步</p>
              <h4 id={`willingness-${current.plan.planId}`}>確認月嫂願意承接正式方案</h4>
              <p>仍有 {pendingWillingnessCount} 位月嫂需要留下正式確認依據。</p>
              <label>月嫂意願確認依據
                <textarea aria-label={`方案 ${current.plan.planId} 月嫂意願確認依據`} value={willingnessReason} maxLength={500} placeholder="例如：9/11 電話確認願意承接此日期方案" onChange={(event) => setWillingnessReason(event.target.value)} />
              </label>
              {current.contact.segments.filter((segment) => segment.willingness === 'pending').map((segment) => (
                <button className="formal-recommendation-primary" key={segment.segment_id} type="button" disabled={!willingnessReason.trim()} onClick={() => void recordWillingness(segment.segment_id)}>
                  確認月嫂 #{currentSegments.find((item) => item.segmentId === segment.segment_id)?.staffId ?? segment.segment_id} 願意承接
                </button>
              ))}
            </section>
          )}

          {canCommunicate && current.contact.all_willing && current.contact.customer_profiles_status === null && (
            <section className="formal-recommendation-next" aria-labelledby={`profiles-${current.plan.planId}`}>
              <p className="formal-recommendation-step">下一步</p>
              <h4 id={`profiles-${current.plan.planId}`}>寄送月嫂履歷給客戶</h4>
              <p>人選與服務日期已確認。系統會寄送目前正式方案中的月嫂履歷。</p>
              <button className="formal-recommendation-primary" type="button" disabled={!resumeNote.trim()} onClick={() => void sendProfiles()}>寄送履歷給客戶</button>
              <details className="formal-recommendation-inline-details">
                <summary>調整寄送訊息</summary>
                <label>履歷傳送備註
                  <textarea aria-label={`方案 ${current.plan.planId} 履歷傳送備註`} value={resumeNote} maxLength={1000} onChange={(event) => setResumeNote(event.target.value)} />
                </label>
              </details>
            </section>
          )}

          {canCommunicate && current.contact.all_willing && current.contact.customer_profiles_status !== null && (
            <section className="formal-recommendation-next" aria-labelledby={`decision-${current.plan.planId}`}>
              <p className="formal-recommendation-step">下一步</p>
              <h4 id={`decision-${current.plan.planId}`}>記錄客戶回覆</h4>
              <p>履歷狀態：{profileStatusLabel(current.contact.customer_profiles_status)}</p>
              <label>客戶回覆依據
                <textarea aria-label={`方案 ${current.plan.planId} 客戶決策依據`} value={decisionReason} maxLength={500} placeholder="例如：9/11 電話確認客戶接受此人選" onChange={(event) => setDecisionReason(event.target.value)} />
              </label>
              <div className="formal-recommendation-actions">
                <button className="formal-recommendation-primary" type="button" aria-label={`記錄方案 ${current.plan.planId} 客戶接受`} disabled={!decisionReason.trim()} onClick={() => void recordDecision('accepted')}>客戶接受</button>
                <button type="button" aria-label={`記錄方案 ${current.plan.planId} 客戶拒絕`} disabled={!decisionReason.trim()} onClick={() => void recordDecision('declined')}>客戶拒絕</button>
              </div>
            </section>
          )}

          {current.contact.customer_decision === 'accepted' && (
            <section className="formal-recommendation-next" aria-label={`方案 ${current.plan.planId} 等待訂金鎖`}>
              <p className="formal-recommendation-step">下一步</p>
              <h4>保留月嫂檔期</h4>
              {current.plan.activeLockId !== null ? <p>既有等待訂金鎖：#{current.plan.activeLockId}</p> : (
                <>
                  <p>客戶已接受推薦，可先檢查服務日與防撞期，再保留檔期。</p>
                  <button className="formal-recommendation-primary" type="button" aria-label={`預覽方案 ${current.plan.planId} 等待訂金鎖`} onClick={() => void previewLock()}>檢查並保留檔期</button>
                  {lockPreview !== null && (
                    <>
                      <p>Preview：服務日 {lockPreview.service_day_count} · 防撞期 {lockPreview.buffer_day_count}</p>
                      <p>允許套用：{lockPreview.apply_allowed ? '是' : '否'}</p>
                      {lockPreview.conflicts.map((conflict, index) => <p key={index}>衝突：月嫂 #{conflict.staff_id} · {conflict.lock_date} · {conflict.source_type} #{conflict.source_id}</p>)}
                      <button type="button" aria-label={`套用方案 ${current.plan.planId} 等待訂金鎖`} disabled={!lockPreview.apply_allowed} onClick={() => void applyLock()}>套用等待訂金鎖</button>
                    </>
                  )}
                </>
              )}
            </section>
          )}

          <details className="formal-recommendation-more">
            <summary>其他處理</summary>
            <div className="formal-recommendation-more-body">
              {current.contact.plan.status === 'proposed' && currentSegments.length > 0 && (
                <HolidayWorkAgreementActions
                  caseNo={caseNo}
                  planId={current.plan.planId}
                  segments={currentSegments}
                  onCommitted={reload}
                />
              )}
              {canCommunicate && current.contact.all_willing && current.contact.customer_profiles_status === null && (
                <CustomerProfilesManualActions
                  key={current.plan.planId}
                  caseNo={caseNo}
                  planId={current.plan.planId}
                  currentStatus={current.contact.customer_profiles_status}
                  onCommitted={() => observe(current.plan.planId, (data) => data.contact.customer_profiles_status !== null, '客戶履歷人工送達已完成正式回讀。')}
                />
              )}
              <div className="formal-recommendation-technical">
                <span>履歷狀態：{profileStatusLabel(current.contact.customer_profiles_status)}</span>
                <span>{decisionLabel(current.contact.customer_decision)}</span>
                <button type="button" aria-label={`重新讀取方案 ${current.plan.planId} 履歷推薦送達狀態`} onClick={() => void reload()}>重新同步狀態</button>
              </div>
            </div>
          </details>
        </fieldset>
      )}

      {active.status === 'ready' && (
        <details key={current?.plan.planId ?? 'no-plan'} className="formal-recommendation-candidates" open={current === null ? true : undefined}>
          <summary>{current === null ? '選擇推薦月嫂' : '更換推薦人選'}</summary>
          <div className="formal-recommendation-candidates-body">
            <button type="button" onClick={() => void loadCandidates()} disabled={busy || candidates.status === 'loading'}>
              {candidates.status === 'loading' ? '讀取候選人中…' : '讀取正式推薦候選'}
            </button>
            {candidates.status === 'error' && <div role="alert"><strong>正式推薦候選不可用</strong><p>{candidates.message}</p></div>}
            {candidates.status === 'ready' && candidates.data.candidates.length === 0 && <p>沒有可推薦的候選人。</p>}
            {candidates.status === 'ready' && candidates.data.candidates.map((candidate) => (
              <article className="formal-recommendation-candidate" key={candidate.id}>
                <div>
                  <strong>{candidate.staff_name} · 月嫂 #{candidate.staff_id}</strong>
                  <span>{candidate.service_start_date}－{candidate.service_end_date}</span>
                  <span>{candidate.willingness === 'willing' ? '願意承接' : candidate.willingness === 'unwilling' ? '不願承接' : '待回覆'}</span>
                </div>
                {candidate.status === 'active' && candidate.willingness === 'willing' ? (
                  <button type="button" aria-label={`以 ${candidate.staff_name} 建立正式媒合方案`} disabled={busy || !canCreate} onClick={() => void createPlan(candidate)}>選擇此月嫂</button>
                ) : <small>目前不可選擇</small>}
              </article>
            ))}
          </div>
        </details>
      )}
      {busy && <p role="status">正式媒合操作／回讀中…</p>}
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  );
};

export default OrderFormalRecommendationPanel;
