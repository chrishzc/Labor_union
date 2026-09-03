import { useState, type FC } from 'react';
import {
  candidateContactPoolClient,
  type CandidateContactPool,
} from '../api/scheduling/candidate_contact_pool_client';
import {
  matchingCandidateWorkflowClient,
  type FormalMatchingPlan,
} from '../api/scheduling/matching_candidate_workflow_client';
import {
  matchingPlanCommunicationClient,
  type FormalPlanContactState,
} from '../api/scheduling/matching_plan_communication_client';
import {
  waitingDepositLockClient,
  type WaitingDepositPreview,
  type WaitingDepositReceipt,
} from '../api/scheduling/waiting_deposit_lock_client';

interface OrderFormalRecommendationPanelProps {
  caseNo: string;
}

type ReadState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: CandidateContactPool }
  | { status: 'error'; message: string };

type CreateState =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'success'; plan: FormalMatchingPlan }
  | { status: 'error'; message: string };

type ResumeStatusState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: FormalPlanContactState }
  | { status: 'error'; message: string };

type DecisionState =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'error'; message: string };

type WaitingLockState =
  | { status: 'idle' }
  | { status: 'previewing' }
  | { status: 'previewed'; preview: WaitingDepositPreview }
  | { status: 'applying'; preview: WaitingDepositPreview }
  | { status: 'success'; preview: WaitingDepositPreview; receipt: WaitingDepositReceipt }
  | { status: 'error'; message: string };

type CandidateContact = CandidateContactPool['candidates'][number];

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '正式媒合方案建立失敗';
}

function canCreatePlan(candidate: CandidateContact): boolean {
  return candidate.status === 'active' && candidate.willingness === 'willing';
}

export const OrderFormalRecommendationPanel: FC<OrderFormalRecommendationPanelProps> = ({ caseNo }) => {
  const [readState, setReadState] = useState<ReadState>({ status: 'idle' });
  const [createStates, setCreateStates] = useState<Record<number, CreateState>>({});
  const [resumeStatusStates, setResumeStatusStates] = useState<Record<number, ResumeStatusState>>({});
  const [decisionReasons, setDecisionReasons] = useState<Record<number, string>>({});
  const [decisionStates, setDecisionStates] = useState<Record<number, DecisionState>>({});
  const [waitingLockStates, setWaitingLockStates] = useState<Record<number, WaitingLockState>>({});

  const loadCandidates = () => {
    setReadState({ status: 'loading' });
    void candidateContactPoolClient.query(caseNo)
      .then((data) => setReadState({ status: 'ready', data }))
      .catch((error) => setReadState({ status: 'error', message: errorMessage(error) }));
  };

  const loadResumeStatus = (plan: FormalMatchingPlan) => {
    setResumeStatusStates((current) => ({
      ...current,
      [plan.plan_id]: { status: 'loading' },
    }));
    void matchingPlanCommunicationClient.queryContactState(caseNo, plan.plan_id)
      .then((data) => {
        setResumeStatusStates((current) => ({
          ...current,
          [plan.plan_id]: { status: 'ready', data },
        }));
      })
      .catch((error) => {
        setResumeStatusStates((current) => ({
          ...current,
          [plan.plan_id]: { status: 'error', message: errorMessage(error) },
        }));
      });
  };

  const createPlan = (candidate: CandidateContact) => {
    if (!canCreatePlan(candidate)) return;
    setCreateStates((current) => ({
      ...current,
      [candidate.id]: { status: 'submitting' },
    }));
    void matchingCandidateWorkflowClient.createSingleCaregiverPlan(caseNo, {
      staff_id: candidate.staff_id,
      start_date: candidate.service_start_date,
      end_date: candidate.service_end_date,
    })
      .then((plan) => {
        setCreateStates((current) => ({
          ...current,
          [candidate.id]: { status: 'success', plan },
        }));
        loadResumeStatus(plan);
      })
      .catch((error) => {
        setCreateStates((current) => ({
          ...current,
          [candidate.id]: { status: 'error', message: errorMessage(error) },
        }));
      });
  };

  const recordCustomerDecision = (
    plan: FormalMatchingPlan,
    decision: 'accepted' | 'declined',
  ) => {
    const contactState = resumeStatusStates[plan.plan_id];
    const reason = (decisionReasons[plan.plan_id] ?? '').trim();
    if (contactState?.status !== 'ready' || !reason) return;

    setDecisionStates((current) => ({
      ...current,
      [plan.plan_id]: { status: 'submitting' },
    }));
    void matchingPlanCommunicationClient.recordCustomerDecision(
      caseNo,
      plan.plan_id,
      contactState.data.plan.communication_version,
      decision,
      reason,
    )
      .then(() => {
        setDecisionStates((current) => ({
          ...current,
          [plan.plan_id]: { status: 'idle' },
        }));
        setWaitingLockStates((current) => ({
          ...current,
          [plan.plan_id]: { status: 'idle' },
        }));
        loadResumeStatus(plan);
      })
      .catch((error) => {
        setDecisionStates((current) => ({
          ...current,
          [plan.plan_id]: { status: 'error', message: errorMessage(error) },
        }));
      });
  };

  const previewWaitingDepositLock = (plan: FormalMatchingPlan) => {
    setWaitingLockStates((current) => ({
      ...current,
      [plan.plan_id]: { status: 'previewing' },
    }));
    void Promise.all([
      waitingDepositLockClient.queryPlan(caseNo),
      matchingPlanCommunicationClient.queryContactState(caseNo, plan.plan_id),
    ])
      .then(async ([activePlan, contactState]) => {
        if (activePlan.planId !== plan.plan_id || contactState.plan.id !== plan.plan_id) {
          throw new Error('等待訂金鎖方案回讀不一致，請重新載入。');
        }
        if (contactState.customer_decision !== 'accepted' || activePlan.activeLockId !== null) {
          throw new Error('僅已接受且尚未鎖定的正式方案可建立等待訂金鎖。');
        }
        const preview = await waitingDepositLockClient.preview(caseNo, plan.plan_id);
        if (preview.case_no !== caseNo || preview.plan_id !== plan.plan_id) {
          throw new Error('等待訂金鎖 Preview identity 不一致，已停止套用。');
        }
        setWaitingLockStates((current) => ({
          ...current,
          [plan.plan_id]: { status: 'previewed', preview },
        }));
      })
      .catch((error) => {
        setWaitingLockStates((current) => ({
          ...current,
          [plan.plan_id]: { status: 'error', message: errorMessage(error) },
        }));
      });
  };

  const applyWaitingDepositLock = (planId: number) => {
    const currentState = waitingLockStates[planId];
    if (currentState?.status !== 'previewed' || !currentState.preview.apply_allowed) return;
    const preview = currentState.preview;
    setWaitingLockStates((current) => ({
      ...current,
      [planId]: { status: 'applying', preview },
    }));
    void waitingDepositLockClient.apply(
      caseNo,
      preview.plan_id,
      preview.preview_fingerprint,
    )
      .then(async (receipt) => {
        const observed = await waitingDepositLockClient.queryPlan(caseNo);
        if (observed.planId !== receipt.plan_id || observed.activeLockId !== receipt.lock_id) {
          throw new Error('等待訂金鎖套用後回讀不一致，請重新載入。');
        }
        setWaitingLockStates((current) => ({
          ...current,
          [planId]: { status: 'success', preview, receipt },
        }));
      })
      .catch((error) => {
        setWaitingLockStates((current) => ({
          ...current,
          [planId]: { status: 'error', message: errorMessage(error) },
        }));
      });
  };

  return (
    <section aria-label={`案件 ${caseNo} 正式推薦媒合方案`}>
      <button
        type="button"
        className="order-v2-open-drawer"
        onClick={loadCandidates}
        disabled={readState.status === 'loading'}
      >
        {readState.status === 'loading' ? '讀取正式推薦候選中…' : '讀取正式推薦候選'}
      </button>

      {readState.status === 'error' && (
        <div className="order-v2-notice blocked" role="alert">
          <strong>正式推薦候選不可用</strong>
          <span>{readState.message}</span>
        </div>
      )}

      {readState.status === 'ready' && readState.data.candidates.length === 0 && (
        <div className="order-v2-notice blocked" role="status">
          <strong>沒有正式推薦候選</strong>
          <span>目前 candidate-contact-pool 沒有 server 回傳候選。</span>
        </div>
      )}

      {readState.status === 'ready' && readState.data.candidates.length > 0 && (
        <div className="order-v2-business-summary" aria-label="正式推薦候選清單">
          {readState.data.candidates.map((candidate) => {
            const createState = createStates[candidate.id] ?? { status: 'idle' as const };
            const eligible = canCreatePlan(candidate);
            const resumeStatusState = createState.status === 'success'
              ? resumeStatusStates[createState.plan.plan_id] ?? { status: 'idle' as const }
              : { status: 'idle' as const };
            const decisionState = createState.status === 'success'
              ? decisionStates[createState.plan.plan_id] ?? { status: 'idle' as const }
              : { status: 'idle' as const };
            const decisionReason = createState.status === 'success'
              ? decisionReasons[createState.plan.plan_id] ?? ''
              : '';
            const waitingLockState = createState.status === 'success'
              ? waitingLockStates[createState.plan.plan_id] ?? { status: 'idle' as const }
              : { status: 'idle' as const };
            const waitingLockPreview = waitingLockState.status === 'previewed'
              || waitingLockState.status === 'applying'
              || waitingLockState.status === 'success'
              ? waitingLockState.preview
              : null;
            return (
              <div key={candidate.id}>
                <dt>{candidate.staff_name} · 月嫂 #{candidate.staff_id}</dt>
                <dd>候選狀態：{candidate.status}</dd>
                <dd>月嫂意願：{candidate.willingness}</dd>
                <dd>候選服務：{candidate.service_start_date} → {candidate.service_end_date}</dd>
                {eligible ? (
                  <button
                    type="button"
                    className="order-v2-open-drawer"
                    aria-label={`以 ${candidate.staff_name} 建立正式媒合方案`}
                    disabled={createState.status === 'submitting' || createState.status === 'success'}
                    onClick={() => createPlan(candidate)}
                  >
                    {createState.status === 'submitting' ? '建立正式媒合方案中…' : '建立正式媒合方案'}
                  </button>
                ) : (
                  <p role="note">不可建立方案：僅 active 且 willing 的 owner candidate 可送入既有正式 route。</p>
                )}
                {createState.status === 'success' && (
                  <>
                    <p role="status">正式媒合方案已建立：#{createState.plan.plan_id} · {createState.plan.result}</p>
                    <div className="order-v2-case-meta" aria-label={`方案 ${createState.plan.plan_id} 履歷推薦送達狀態`}>
                      <strong>履歷推薦送達狀態</strong>
                      {resumeStatusState.status === 'idle' && <span>尚未讀取</span>}
                      {resumeStatusState.status === 'loading' && <span>讀取中…</span>}
                      {resumeStatusState.status === 'ready' && (
                        <span>{resumeStatusState.data.customer_profiles_status ?? '尚未有履歷送達根事實'}</span>
                      )}
                      {resumeStatusState.status === 'error' && (
                        <span role="alert">{resumeStatusState.message}</span>
                      )}
                      <button
                        type="button"
                        className="order-v2-open-drawer"
                        aria-label={`重新讀取方案 ${createState.plan.plan_id} 履歷推薦送達狀態`}
                        disabled={resumeStatusState.status === 'loading'}
                        onClick={() => loadResumeStatus(createState.plan)}
                      >
                        重新讀取履歷推薦狀態
                      </button>
                    </div>

                    {resumeStatusState.status === 'ready' && (
                      <div className="order-v2-case-meta" aria-label={`方案 ${createState.plan.plan_id} 客戶決定`}>
                        <strong>客戶決定</strong>
                        <span>目前決定：{resumeStatusState.data.customer_decision}</span>
                        {resumeStatusState.data.customer_decision === 'declined' && (
                          <div className="order-v2-notice blocked" role="alert">
                            <strong>客戶拒絕正式推薦</strong>
                            <span>目前正式方案受阻；請依後續 owner 流程處理。</span>
                          </div>
                        )}
                        <textarea
                          aria-label={`方案 ${createState.plan.plan_id} 客戶決策依據`}
                          value={decisionReason}
                          maxLength={500}
                          onChange={(event) => setDecisionReasons((current) => ({
                            ...current,
                            [createState.plan.plan_id]: event.target.value,
                          }))}
                          placeholder="填寫客戶決策依據"
                        />
                        <button
                          type="button"
                          className="order-v2-open-drawer"
                          aria-label={`記錄方案 ${createState.plan.plan_id} 客戶接受`}
                          disabled={decisionState.status === 'submitting' || !decisionReason.trim()}
                          onClick={() => recordCustomerDecision(createState.plan, 'accepted')}
                        >
                          記錄客戶接受
                        </button>
                        <button
                          type="button"
                          className="order-v2-open-drawer"
                          aria-label={`記錄方案 ${createState.plan.plan_id} 客戶拒絕`}
                          disabled={decisionState.status === 'submitting' || !decisionReason.trim()}
                          onClick={() => recordCustomerDecision(createState.plan, 'declined')}
                        >
                          記錄客戶拒絕
                        </button>
                        {decisionState.status === 'submitting' && <span>記錄客戶決定中…</span>}
                        {decisionState.status === 'error' && (
                          <span role="alert">{decisionState.message}</span>
                        )}

                        {resumeStatusState.data.customer_decision === 'accepted' && (
                          <div className="order-v2-case-meta" aria-label={`方案 ${createState.plan.plan_id} 等待訂金鎖`}>
                            <strong>等待訂金鎖</strong>
                            <span>僅沿用既有 waiting-deposit-lock Preview／Apply；不在此計算訂金。</span>
                            <button
                              type="button"
                              className="order-v2-open-drawer"
                              aria-label={`預覽方案 ${createState.plan.plan_id} 等待訂金鎖`}
                              disabled={waitingLockState.status === 'previewing'
                                || waitingLockState.status === 'applying'
                                || waitingLockState.status === 'success'}
                              onClick={() => previewWaitingDepositLock(createState.plan)}
                            >
                              {waitingLockState.status === 'previewing' ? '預覽等待訂金鎖中…' : '預覽等待訂金鎖'}
                            </button>

                            {waitingLockPreview !== null && (
                              <>
                                <span>
                                  Preview：服務日 {waitingLockPreview.service_day_count} · 防撞期 {waitingLockPreview.buffer_day_count}
                                </span>
                                <span>允許套用：{waitingLockPreview.apply_allowed ? '是' : '否'}</span>
                                {waitingLockPreview.conflicts.map((conflict) => (
                                  <span key={`${conflict.staff_id}:${conflict.lock_date}:${conflict.source_type}:${conflict.source_id}`}>
                                    衝突：月嫂 #{conflict.staff_id} · {conflict.lock_date} · {conflict.source_type} #{conflict.source_id}
                                  </span>
                                ))}
                                <button
                                  type="button"
                                  className="order-v2-open-drawer"
                                  aria-label={`套用方案 ${createState.plan.plan_id} 等待訂金鎖`}
                                  disabled={waitingLockState.status !== 'previewed' || !waitingLockPreview.apply_allowed}
                                  onClick={() => applyWaitingDepositLock(createState.plan.plan_id)}
                                >
                                  {waitingLockState.status === 'applying' ? '套用等待訂金鎖中…' : '套用等待訂金鎖'}
                                </button>
                              </>
                            )}
                            {waitingLockState.status === 'success' && (
                              <span role="status">
                                等待訂金鎖已套用：Lock #{waitingLockState.receipt.lock_id} · {waitingLockState.receipt.result}
                              </span>
                            )}
                            {waitingLockState.status === 'error' && (
                              <span role="alert">{waitingLockState.message}</span>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
                {createState.status === 'error' && (
                  <p className="order-v2-drawer-error" role="alert">{createState.message}</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
};

export default OrderFormalRecommendationPanel;
