import { useEffect, useRef, useState, type FC } from 'react';
import { candidateContactPoolClient, type CandidateContactPool } from '../api/scheduling/candidate_contact_pool_client';
import { matchingCandidateWorkflowClient } from '../api/scheduling/matching_candidate_workflow_client';
import { matchingPlanCommunicationClient, type FormalPlanContactState } from '../api/scheduling/matching_plan_communication_client';
import { waitingDepositLockClient, type ActiveWaitingDepositPlan, type WaitingDepositPreview } from '../api/scheduling/waiting_deposit_lock_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { CustomerProfilesManualActions } from './MatchingManualCommunicationActions';

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
  if (contact.plan.id !== plan.planId || contact.plan.case_no !== caseNo
    || (plan.communicationVersion !== undefined && plan.communicationVersion !== contact.plan.communication_version)) {
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
  const [reason, setReason] = useState('');
  const [resumeNote, setResumeNote] = useState('');
  const [lockPreview, setLockPreview] = useState<WaitingDepositPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const request = ++sequence.current;
    activeCase.current = caseNo;
    setActive({ status: 'loading' });
    setCandidates({ status: 'idle' });
    setReason('');
    setResumeNote('');
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
    await observe(receipt.plan_id, () => true, `正式媒合方案已建立：#${receipt.plan_id} · ${receipt.result}`);
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
      `履歷發送工作已建立：#${receipt.intent_id}（${receipt.delivery_status}）；尚不代表 LINE 已送達。`);
  });

  const recordWillingness = (segmentId: number) => perform(async () => {
    const fresh = await freshVisiblePlan();
    if (fresh.plan.activeLockId !== null || fresh.contact.plan.status !== 'proposed'
      || fresh.contact.customer_decision !== 'pending'
      || !fresh.contact.segments.some((segment) => segment.segment_id === segmentId && segment.willingness === 'pending')
      || !reason.trim()) throw new Error('目前區段不可補登意願。');
    await matchingPlanCommunicationClient.recordFormalPlanWillingness(
      caseNo, fresh.plan.planId, segmentId, fresh.contact.plan.communication_version, reason.trim(),
    );
    await observe(fresh.plan.planId,
      (data) => data.contact.segments.some((segment) => segment.segment_id === segmentId && segment.willingness === 'willing'),
      '正式方案月嫂意願已回讀確認。');
  });

  const recordDecision = (decision: 'accepted' | 'declined') => perform(async () => {
    const fresh = await freshVisiblePlan();
    if (fresh.plan.activeLockId !== null || fresh.contact.plan.status !== 'proposed'
      || fresh.contact.customer_decision !== 'pending' || !fresh.contact.all_willing || !reason.trim()) {
      throw new Error('目前正式方案不可記錄客戶決定。');
    }
    await matchingPlanCommunicationClient.recordCustomerDecision(
      caseNo, fresh.plan.planId, fresh.contact.plan.communication_version, decision, reason.trim(),
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

  return (
    <section aria-label={`案件 ${caseNo} 正式推薦媒合方案`}>
      <button type="button" className="order-v2-open-drawer" disabled={busy || active.status === 'loading'} onClick={() => void reload()}>
        重新讀取目前正式方案
      </button>
      {active.status === 'loading' && <p role="status">讀取目前正式方案中…</p>}
      {active.status === 'error' && <p role="alert">目前正式方案不可用：{active.message}</p>}
      {active.status === 'ready' && current === null && <p>尚無有效正式媒合方案。</p>}
      {current !== null && (
        <fieldset disabled={busy} style={{ border: 0, padding: 0 }}>
          <legend>目前正式媒合方案：#{current.plan.planId}</legend>
          {(current.plan.segments ?? []).map((segment) => (
            <p key={segment.segmentId}>第 {segment.sequence} 段 · 月嫂 #{segment.staffId} · {segment.assignedStartDate} → {segment.assignedEndDate}</p>
          ))}
          <div aria-label={`方案 ${current.plan.planId} 履歷推薦送達狀態`}>
            <strong>履歷推薦送達狀態</strong>
            <p>{current.contact.customer_profiles_status ?? '尚未有履歷送達根事實'}</p>
            <button type="button" aria-label={`重新讀取方案 ${current.plan.planId} 履歷推薦送達狀態`} onClick={() => void reload()}>重新讀取履歷推薦狀態</button>
          </div>
          <p>目前決定：{current.contact.customer_decision}</p>
          {current.contact.customer_decision === 'declined' && (
            <div role="alert"><strong>客戶拒絕正式推薦</strong><p>目前正式方案受阻；請依後續 owner 流程處理。</p></div>
          )}
          {canCommunicate && (
            <>
              <label>客戶決策／月嫂意願依據
                <textarea aria-label={`方案 ${current.plan.planId} 客戶決策依據`} value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} />
              </label>
              {current.contact.segments.filter((segment) => segment.willingness === 'pending').map((segment) => (
                <button key={segment.segment_id} type="button" disabled={!reason.trim()} onClick={() => void recordWillingness(segment.segment_id)}>
                  確認分段 {segment.segment_id} 月嫂願意承接
                </button>
              ))}
              {!current.contact.all_willing && <p role="status">正式方案尚缺月嫂意願確認。</p>}
              {current.contact.customer_profiles_status === null && (
                <>
                  <label>履歷傳送備註
                    <textarea aria-label={`方案 ${current.plan.planId} 履歷傳送備註`} value={resumeNote} maxLength={1000} onChange={(event) => setResumeNote(event.target.value)} />
                  </label>
                  <button type="button" disabled={!current.contact.all_willing || !resumeNote.trim()} onClick={() => void sendProfiles()}>寄送月嫂履歷給客戶</button>
                  {current.contact.all_willing && (
                    <CustomerProfilesManualActions
                      key={current.plan.planId}
                      caseNo={caseNo}
                      planId={current.plan.planId}
                      currentStatus={current.contact.customer_profiles_status}
                      onCommitted={() => observe(current.plan.planId, (data) => data.contact.customer_profiles_status !== null, '客戶履歷人工送達已完成正式回讀。')}
                    />
                  )}
                </>
              )}
              <button type="button" aria-label={`記錄方案 ${current.plan.planId} 客戶接受`} disabled={!current.contact.all_willing || !reason.trim()} onClick={() => void recordDecision('accepted')}>記錄客戶接受</button>
              <button type="button" aria-label={`記錄方案 ${current.plan.planId} 客戶拒絕`} disabled={!current.contact.all_willing || !reason.trim()} onClick={() => void recordDecision('declined')}>記錄客戶拒絕</button>
            </>
          )}
          {current.contact.customer_decision === 'accepted' && (
            <div aria-label={`方案 ${current.plan.planId} 等待訂金鎖`}>
              <strong>等待訂金鎖</strong>
              {current.plan.activeLockId !== null ? <p>既有等待訂金鎖：#{current.plan.activeLockId}</p> : (
                <>
                  <button type="button" aria-label={`預覽方案 ${current.plan.planId} 等待訂金鎖`} onClick={() => void previewLock()}>預覽等待訂金鎖</button>
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
            </div>
          )}
        </fieldset>
      )}
      <button type="button" className="order-v2-open-drawer" onClick={() => void loadCandidates()} disabled={busy || candidates.status === 'loading'}>
        {candidates.status === 'loading' ? '讀取正式推薦候選中…' : '讀取正式推薦候選'}
      </button>
      {candidates.status === 'error' && <div role="alert"><strong>正式推薦候選不可用</strong><p>{candidates.message}</p></div>}
      {candidates.status === 'ready' && candidates.data.candidates.length === 0 && <p>沒有正式推薦候選</p>}
      {candidates.status === 'ready' && candidates.data.candidates.map((candidate) => (
        <div key={candidate.id}>
          <p>{candidate.staff_name} · 月嫂 #{candidate.staff_id}</p>
          <p>候選狀態：{candidate.status} · 月嫂意願：{candidate.willingness}</p>
          <p>候選服務：{candidate.service_start_date} → {candidate.service_end_date}</p>
          {candidate.status === 'active' && candidate.willingness === 'willing' ? (
            <button type="button" className="order-v2-open-drawer" aria-label={`以 ${candidate.staff_name} 建立正式媒合方案`} disabled={busy || !canCreate} onClick={() => void createPlan(candidate)}>建立正式媒合方案</button>
          ) : <p role="note">不可建立方案：僅 active 且 willing 的 owner candidate 可送入既有正式 route。</p>}
        </div>
      ))}
      {busy && <p role="status">正式媒合操作／回讀中…</p>}
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  );
};

export default OrderFormalRecommendationPanel;