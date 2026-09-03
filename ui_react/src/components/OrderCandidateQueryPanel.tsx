import { useState, type FC } from 'react';
import {
  matchingCandidateWorkflowClient,
  type MatchingAvailability,
  type MatchingCandidateOption,
} from '../api/scheduling/matching_candidate_workflow_client';

interface OrderCandidateQueryPanelProps {
  caseNo: string;
}

type CandidateQueryState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: MatchingAvailability }
  | { status: 'error'; message: string };

function queryErrorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '正式候選查詢失敗';
}

function formalCandidates(data: MatchingAvailability): MatchingCandidateOption[] {
  const staffIds = new Set<number>();
  data.complete_combinations.forEach((combination) => {
    if (combination.length === 1) staffIds.add(combination[0]!.staff_id);
  });
  return data.candidate_options.filter((candidate) => staffIds.has(candidate.staff_id));
}

export const OrderCandidateQueryPanel: FC<OrderCandidateQueryPanelProps> = ({ caseNo }) => {
  const [queryState, setQueryState] = useState<CandidateQueryState>({ status: 'idle' });

  const queryCandidates = () => {
    setQueryState({ status: 'loading' });
    void matchingCandidateWorkflowClient.searchSegmentedCaregivers(caseNo, 1)
      .then((data) => setQueryState({ status: 'ready', data }))
      .catch((error) => setQueryState({ status: 'error', message: queryErrorMessage(error) }));
  };

  const candidates = queryState.status === 'ready' ? formalCandidates(queryState.data) : [];

  return (
    <section aria-label={`案件 ${caseNo} 正式候選查詢`}>
      <button
        type="button"
        className="order-v2-open-drawer"
        onClick={queryCandidates}
        disabled={queryState.status === 'loading'}
      >
        {queryState.status === 'loading' ? '查詢正式候選中…' : '查詢正式候選'}
      </button>

      {queryState.status === 'error' && (
        <div className="order-v2-notice blocked" role="alert">
          <strong>阻塞</strong>
          <span>正式候選查詢不可用：{queryState.message}</span>
        </div>
      )}

      {queryState.status === 'ready' && (
        <>
          <div className="order-v2-case-meta">
            <span>Server 計畫期間：{queryState.data.planned_start_date} → {queryState.data.planned_end_date}</span>
            <span>Feasibility：{queryState.data.feasibility}</span>
          </div>

          {candidates.length > 0 ? (
            <div className="order-v2-business-summary" aria-label="正式符合條件候選">
              {candidates.map((candidate) => (
                <div key={candidate.staff_id}>
                  <dt>{candidate.staff_name}</dt>
                  <dd>
                    月嫂 #{candidate.staff_id} · Server 支援 {candidate.supported_day_count}/{candidate.required_day_count} 日
                  </dd>
                </div>
              ))}
            </div>
          ) : (
            <div className="order-v2-notice blocked" role="status">
              <strong>阻塞</strong>
              <span>目前沒有 server 確認的完整候選；不以瀏覽器條件推導人選。</span>
              {queryState.data.conflicts.map((conflict, index) => (
                <span key={`${conflict.segment_index}:${conflict.staff_id ?? 'none'}:${conflict.work_date}:${index}`}>
                  {conflict.work_date} · 月嫂 #{conflict.staff_id ?? '未指定'} · {conflict.reason_code}
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
};

export default OrderCandidateQueryPanel;
