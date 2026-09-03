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
