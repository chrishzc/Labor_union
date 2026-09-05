import { useEffect, useRef, useState, type FC } from 'react';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { matchingCandidateWorkflowClient, type MatchingAvailability, type MatchingFilterPolicy } from '../api/scheduling/matching_candidate_workflow_client';
import { waitingDepositLockClient } from '../api/scheduling/waiting_deposit_lock_client';
import { ApiHttpError } from '../api/shared/typed_errors';

interface Props {
  caseNo: string;
  filters: MatchingFilterPolicy;
  onObserved?: () => void;
  onBusyChange?: (busy: boolean) => void;
}

type QueryState =
  | { status: 'idle' | 'loading' }
  | { status: 'ready'; data: MatchingAvailability }
  | { status: 'error'; message: string };

/** Present only complete combinations returned by the existing Scheduling owner. */
export const OrderMultiCaregiverPlanPanel: FC<Props> = ({ caseNo, filters, onObserved, onBusyChange }) => {
  const [segmentCount, setSegmentCount] = useState<2 | 3 | 4>(2);
  const [query, setQuery] = useState<QueryState>({ status: 'idle' });
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [attempted, setAttempted] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sequence = useRef(0);
  const filterKey = JSON.stringify(filters);

  useEffect(() => {
    sequence.current += 1;
    setQuery({ status: 'idle' });
    setAttempted(false);
    setMessage(null);
    setError(null);
    return () => { sequence.current += 1; };
  }, [caseNo, filterKey, segmentCount]);

  const busy = saving || query.status === 'loading';
  useEffect(() => { onBusyChange?.(busy); }, [busy, onBusyChange]);
  useEffect(() => () => { onBusyChange?.(false); }, [onBusyChange]);

  const search = async () => {
    if (savingRef.current) return;
    const request = ++sequence.current;
    setQuery({ status: 'loading' });
    setAttempted(false);
    setMessage(null);
    setError(null);
    try {
      const data = await matchingCandidateWorkflowClient.searchSegmentedCaregivers(caseNo, segmentCount, [], filters);
      if (data.case_no !== caseNo) throw new Error('多月嫂候選查詢案件識別不一致。');
      if (request === sequence.current) setQuery({ status: 'ready', data });
    } catch (caught) {
      if (request === sequence.current) setQuery({ status: 'error', message: caught instanceof Error ? caught.message : '多月嫂候選查詢失敗。' });
    }
  };

  const create = async (combination: MatchingAvailability['complete_combinations'][number]) => {
    if (savingRef.current || attempted || query.status !== 'ready'
      || !query.data.complete_combinations.includes(combination) || combination.length !== segmentCount) return;
    savingRef.current = true;
    setSaving(true);
    setAttempted(true);
    setError(null);
    setMessage(null);
    const request = sequence.current;
    try {
      const [detail, active] = await Promise.all([
        ordersQueryClient.getOrderDetail(caseNo),
        waitingDepositLockClient.queryPlan(caseNo).catch((caught: unknown) => {
          if (caught instanceof ApiHttpError && caught.status === 404) return null;
          throw caught;
        }),
      ]);
      if (detail.case_no !== caseNo || !['洽談中', '訂單成立'].includes(detail.order_status)
        || (active !== null && (active.activeLockId !== null || active.status === 'accepted'))) {
        throw new Error('目前案件或正式方案已接受／鎖定，不可建立新的多月嫂方案。');
      }
      if (request !== sequence.current) return;
      const segments = combination.map((segment) => ({
        staff_id: segment.staff_id,
        start_date: segment.start_date,
        end_date: segment.end_date,
      }));
      const receipt = await matchingCandidateWorkflowClient.createMatchingPlan(caseNo, segments);
      const observed = await waitingDepositLockClient.queryPlan(caseNo);
      const observedSegments = [...(observed.segments ?? [])].sort((left, right) => left.sequence - right.sequence);
      if (receipt.case_no !== caseNo || observed.planId !== receipt.plan_id
        || observedSegments.length !== segments.length || observedSegments.some((segment, index) => (
          segment.staffId !== segments[index]?.staff_id
          || segment.assignedStartDate !== segments[index]?.start_date
          || segment.assignedEndDate !== segments[index]?.end_date
        ))) throw new Error('多月嫂方案建立後正式分段回讀不一致；不重送建立操作。');
      if (request !== sequence.current) return;
      setMessage(`正式 ${segments.length} 段多月嫂方案 #${receipt.plan_id} 已建立並完成回讀；請從正式方案續辦各段意願與客戶推薦。`);
      onObserved?.();
    } catch (caught) {
      if (request === sequence.current) setError(caught instanceof Error ? caught.message : '多月嫂方案建立／回讀失敗。');
    } finally {
      savingRef.current = false;
      if (request === sequence.current) setSaving(false);
    }
  };

  const combinations = query.status === 'ready'
    ? query.data.complete_combinations.filter((combination) => combination.length === segmentCount)
    : [];

  return (
    <section aria-label={`案件 ${caseNo} 多月嫂分段方案`}>
      <h4>多月嫂接續服務</h4>
      <p>沿用上方四項媒合篩選；僅選用後端回傳的完整組合，不在瀏覽器拼接人選或服務日期。</p>
      <label>服務分段數
        <select aria-label="多月嫂服務分段數" value={segmentCount} disabled={busy} onChange={(event) => setSegmentCount(Number(event.target.value) as 2 | 3 | 4)}>
          <option value={2}>2 段</option><option value={3}>3 段</option><option value={4}>4 段</option>
        </select>
      </label>
      <button type="button" disabled={busy} onClick={() => void search()}>查詢多月嫂完整組合</button>
      {query.status === 'loading' && <p role="status">查詢多月嫂組合中…</p>}
      {query.status === 'error' && <p role="alert">{query.message}</p>}
      {query.status === 'ready' && combinations.length === 0 && (
        <div role="status">
          <p>後端未回傳可建立的 {segmentCount} 段完整組合。</p>
          {query.data.conflicts.map((conflict, index) => <p key={index}>{conflict.work_date} · 月嫂 #{conflict.staff_id ?? '未指定'} · {conflict.reason_code}</p>)}
        </div>
      )}
      {combinations.map((combination, index) => (
        <article key={index} aria-label={`完整組合 ${index + 1}`}>
          {combination.map((segment) => <p key={segment.segment_index}>第 {segment.segment_index + 1} 段 · 月嫂 #{segment.staff_id} · {segment.start_date} → {segment.end_date}</p>)}
          <button type="button" disabled={busy || attempted} onClick={() => void create(combination)}>以完整組合 {index + 1} 建立正式 {segmentCount} 段方案</button>
        </article>
      ))}
      {saving && <p role="status">建立並回讀正式多月嫂方案中…</p>}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error} 請重新查詢正式狀態後確認，不自動重試。</p>}
    </section>
  );
};
