import { useState, type FC } from 'react';
import { candidateContactPoolClient, type AddCandidatesResult } from '../api/scheduling/candidate_contact_pool_client';
import {
  matchingCandidateWorkflowClient,
  type MatchingAvailability,
  type MatchingCandidateOption,
} from '../api/scheduling/matching_candidate_workflow_client';

interface OrderCandidateQueryPanelProps {
  caseNo: string;
  onPoolReadback?: () => void;
}

type CandidateQueryState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: MatchingAvailability }
  | { status: 'error'; message: string };

type CandidateAddState =
  | { status: 'idle' }
  | { status: 'saving' }
  | {
      status: 'success';
      data: AddCandidatesResult;
      readbackStaff: readonly { staffId: number; staffName: string }[];
    }
  | { status: 'error'; message: string };

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : fallback;
}

function formalCandidates(data: MatchingAvailability): MatchingCandidateOption[] {
  const staffIds = new Set<number>();
  data.complete_combinations.forEach((combination) => {
    if (combination.length === 1) staffIds.add(combination[0]!.staff_id);
  });
  return data.candidate_options.filter((candidate) => staffIds.has(candidate.staff_id));
}

function sameStaffIds(expected: readonly number[], actual: readonly number[]): boolean {
  if (expected.length !== actual.length) return false;
  const expectedSorted = [...expected].sort((left, right) => left - right);
  const actualSorted = [...actual].sort((left, right) => left - right);
  return expectedSorted.every((staffId, index) => staffId === actualSorted[index]);
}

export const OrderCandidateQueryPanel: FC<OrderCandidateQueryPanelProps> = ({ caseNo, onPoolReadback }) => {
  const [queryState, setQueryState] = useState<CandidateQueryState>({ status: 'idle' });
  const [selectedStaffIds, setSelectedStaffIds] = useState<ReadonlySet<number>>(() => new Set());
  const [addState, setAddState] = useState<CandidateAddState>({ status: 'idle' });

  const queryCandidates = () => {
    setSelectedStaffIds(new Set());
    setAddState({ status: 'idle' });
    setQueryState({ status: 'loading' });
    void matchingCandidateWorkflowClient.searchSegmentedCaregivers(caseNo, 1)
      .then((data) => setQueryState({ status: 'ready', data }))
      .catch((error) => setQueryState({
        status: 'error',
        message: errorMessage(error, '正式候選查詢失敗'),
      }));
  };

  const candidates = queryState.status === 'ready' ? formalCandidates(queryState.data) : [];

  const toggleCandidate = (staffId: number) => {
    setSelectedStaffIds((current) => {
      const next = new Set(current);
      if (next.has(staffId)) next.delete(staffId);
      else next.add(staffId);
      return next;
    });
    if (addState.status !== 'saving') setAddState({ status: 'idle' });
  };

  const addSelectedCandidates = () => {
    if (queryState.status !== 'ready') return;
    const selected = formalCandidates(queryState.data).filter((candidate) => selectedStaffIds.has(candidate.staff_id));
    if (selected.length === 0) {
      setAddState({ status: 'error', message: '請先選擇至少一位正式候選。' });
      return;
    }
    const selectedInputs = selected.map((candidate) => ({
      staff_id: candidate.staff_id,
      start_date: candidate.selected_segment_start,
      end_date: candidate.selected_segment_end,
    }));
    const expectedStaffIds = selectedInputs.map((candidate) => candidate.staff_id);

    setAddState({ status: 'saving' });
    void candidateContactPoolClient.addCandidates(caseNo, selectedInputs)
      .then(async (data) => {
        const pool = await candidateContactPoolClient.query(caseNo);
        const insertedIds = new Set(data.candidate_ids);
        const readbackCandidates = pool.candidates.filter((candidate) => insertedIds.has(candidate.id));
        if (!sameStaffIds(expectedStaffIds, readbackCandidates.map((candidate) => candidate.staff_id))) {
          throw new Error('候選池回讀與本次寫入選擇不一致。');
        }
        setSelectedStaffIds(new Set());
        setAddState({
          status: 'success',
          data,
          readbackStaff: readbackCandidates.map((candidate) => ({
            staffId: candidate.staff_id,
            staffName: candidate.staff_name,
          })),
        });
        onPoolReadback?.();
      })
      .catch((error) => setAddState({
        status: 'error',
        message: errorMessage(error, '候選池寫入後回讀失敗'),
      }));
  };

  return (
    <section aria-label={`案件 ${caseNo} 正式候選查詢`}>
      <button
        type="button"
        className="order-v2-open-drawer"
        onClick={queryCandidates}
        disabled={queryState.status === 'loading' || addState.status === 'saving'}
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
            <>
              <div className="order-v2-business-summary" aria-label="正式符合條件候選">
                {candidates.map((candidate) => (
                  <label key={candidate.staff_id}>
                    <input
                      type="checkbox"
                      aria-label={`選擇正式候選 ${candidate.staff_name}`}
                      checked={selectedStaffIds.has(candidate.staff_id)}
                      onChange={() => toggleCandidate(candidate.staff_id)}
                      disabled={addState.status === 'saving'}
                    />
                    <span>
                      <strong>{candidate.staff_name}</strong><br />
                      月嫂 #{candidate.staff_id} · Server 支援 {candidate.supported_day_count}/{candidate.required_day_count} 日
                    </span>
                  </label>
                ))}
              </div>
              <button
                type="button"
                className="order-v2-open-drawer"
                onClick={addSelectedCandidates}
                disabled={selectedStaffIds.size === 0 || addState.status === 'saving'}
              >
                {addState.status === 'saving' ? '加入候選池中…' : `加入候選池（${selectedStaffIds.size}）`}
              </button>
            </>
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

      {addState.status === 'success' && (
        <div className="order-v2-notice warning" role="status">
          <strong>候選池回讀完成</strong>
          <span>
            Pool #{addState.data.pool_id} · 已回讀 {addState.readbackStaff.length} 位本次寫入候選：
            {addState.readbackStaff.map((candidate) => `${candidate.staffName} (#${candidate.staffId})`).join('、')}。
          </span>
        </div>
      )}
      {addState.status === 'error' && (
        <div className="order-v2-notice blocked" role="alert">
          <strong>候選池寫入／回讀失敗</strong>
          <span>{addState.message}</span>
        </div>
      )}
    </section>
  );
};

export default OrderCandidateQueryPanel;
