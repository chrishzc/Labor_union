import { useEffect, useRef, useState, useSyncExternalStore, type FC } from 'react';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { sessionClient } from '../api/auth/session_client';
import { matchingCandidateWorkflowClient, type MatchingAvailability, type MatchingFilterPolicy, type MatchingPlanSegmentInput } from '../api/scheduling/matching_candidate_workflow_client';
import { waitingDepositLockClient } from '../api/scheduling/waiting_deposit_lock_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { orderMutationFlowStore, type FormalPlanCreationFlowState } from '../adapters/orders/order_mutation_flow_store';

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

const subscribeFormalPlanCreation = (listener: () => void) => orderMutationFlowStore.subscribe(listener);

function hasExactSegments(
  observed: ReadonlyArray<{ sequence: number; staffId: number; assignedStartDate: string; assignedEndDate: string }> | undefined,
  command: MatchingPlanSegmentInput[],
): boolean {
  const ordered = [...(observed ?? [])].sort((left, right) => left.sequence - right.sequence);
  return ordered.length === command.length && ordered.every((segment, index) => (
    segment.staffId === command[index]?.staff_id
    && segment.assignedStartDate === command[index]?.start_date
    && segment.assignedEndDate === command[index]?.end_date
  ));
}

function hasExactReceiptSegments(
  receiptSegments: ReadonlyArray<{ segment_order: number; staff_id: number; assigned_start_date: string; assigned_end_date: string }>,
  command: MatchingPlanSegmentInput[],
): boolean {
  const ordered = [...receiptSegments].sort((left, right) => left.segment_order - right.segment_order);
  return ordered.length === command.length && ordered.every((segment, index) => (
    segment.staff_id === command[index]?.staff_id
    && segment.assigned_start_date === command[index]?.start_date
    && segment.assigned_end_date === command[index]?.end_date
  ));
}

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
  const searchController = useRef<AbortController | null>(null);
  const filterKey = JSON.stringify(filters);
  const formalPlanCreation = useSyncExternalStore(
    subscribeFormalPlanCreation,
    () => orderMutationFlowStore.getFormalPlanCreation(caseNo, 'multi'),
  );
  const creationProtected = formalPlanCreation?.status === 'applying'
    || formalPlanCreation?.status === 'outcome_unknown'
    || formalPlanCreation?.status === 'observation_failed'
    || formalPlanCreation?.status === 'observing';

  useEffect(() => {
    sequence.current += 1;
    setQuery({ status: 'idle' });
    setAttempted(false);
    setMessage(null);
    setError(null);
    return () => {
      sequence.current += 1;
      searchController.current?.abort();
      searchController.current = null;
    };
  }, [caseNo, filterKey, segmentCount]);

  const busy = saving || query.status === 'loading';
  useEffect(() => { onBusyChange?.(busy); }, [busy, onBusyChange]);
  useEffect(() => () => { onBusyChange?.(false); }, [onBusyChange]);

  const search = async () => {
    if (savingRef.current) return;
    searchController.current?.abort();
    const controller = new AbortController();
    searchController.current = controller;
    const request = ++sequence.current;
    setQuery({ status: 'loading' });
    setAttempted(false);
    setMessage(null);
    setError(null);
    try {
      const data = await matchingCandidateWorkflowClient.searchSegmentedCaregivers(caseNo, segmentCount, [], filters, { signal: controller.signal });
      if (data.case_no !== caseNo) throw new Error('多月嫂候選查詢案件識別不一致。');
      if (request === sequence.current && searchController.current === controller) setQuery({ status: 'ready', data });
    } catch (caught) {
      if (request === sequence.current && searchController.current === controller) {
        setQuery({ status: 'error', message: caught instanceof Error ? caught.message : '多月嫂候選查詢失敗。' });
      }
    }
  };

  const create = async (combination: MatchingAvailability['complete_combinations'][number]) => {
    if (savingRef.current || attempted || creationProtected || query.status !== 'ready'
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
      const command = {
        caseNo,
        kind: 'multi' as const,
        actor: sessionClient.getUser()?.username.trim() ?? '',
        asOf: new Date().toISOString().slice(0, 10),
        key: `orders-multi-plan-${crypto.randomUUID()}`,
        segments,
      };
      if (!command.actor) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
      orderMutationFlowStore.setFormalPlanCreation(caseNo, { status: 'applying', command, receipt: null, error: null });
      let receipt: FormalPlanCreationFlowState['receipt'];
      try {
        receipt = await matchingCandidateWorkflowClient.createMatchingPlan(command);
      } catch (caught) {
        const message = caught instanceof Error ? caught.message : '多月嫂方案建立結果未確定。';
        orderMutationFlowStore.setFormalPlanCreation(caseNo, { status: 'outcome_unknown', command, receipt: null, error: message });
        throw caught;
      }
      const saved: FormalPlanCreationFlowState = { status: 'observation_failed', command, receipt, error: null };
      orderMutationFlowStore.setFormalPlanCreation(caseNo, saved);
      if (request !== sequence.current) return;
      await observeCreation(saved, request);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : '多月嫂方案建立／回讀失敗。';
      if (request === sequence.current) setError(message);
    } finally {
      savingRef.current = false;
      if (request === sequence.current) setSaving(false);
    }
  };

  const observeCreation = async (state: FormalPlanCreationFlowState, request: number) => {
    const { command, receipt } = state;
    const observationToken = crypto.randomUUID();
    const ownsObservation = () => orderMutationFlowStore.getFormalPlanCreation(caseNo, 'multi')?.observationToken === observationToken;
    orderMutationFlowStore.setFormalPlanCreation(caseNo, { ...state, status: 'observing', error: null, observationToken });
    try {
      if (receipt === null || receipt.case_no !== command.caseNo || receipt.actor !== command.actor
        || receipt.as_of !== command.asOf || receipt.event_key !== command.key
        || !hasExactReceiptSegments(receipt.segments, command.segments)) {
        throw new Error('多月嫂方案收據 identity 不一致；只能重新讀取。');
      }
      const observed = await waitingDepositLockClient.queryPlan(command.caseNo);
      if (!ownsObservation()) return;
      if (observed.planId !== receipt.plan_id || observed.planVersion === undefined || observed.planVersion < receipt.version
        || !hasExactSegments(observed.segments, command.segments)) {
        throw new Error('多月嫂方案建立收據與正式分段回讀不一致；只能重新讀取。');
      }
      if (request !== sequence.current) {
        orderMutationFlowStore.setFormalPlanCreation(caseNo, { ...state, status: 'observation_failed', error: '案件畫面已切換；保留收據，只能重新讀取原案件結果。' });
        return;
      }
      orderMutationFlowStore.clearFormalPlanCreation(caseNo, 'multi');
      setMessage(`正式 ${command.segments.length} 段多月嫂方案 #${receipt.plan_id} 已建立並完成回讀；請從正式方案續辦各段意願與客戶推薦。`);
      onObserved?.();
    } catch (caught) {
      if (ownsObservation()) {
        const message = caught instanceof Error ? caught.message : '多月嫂方案正式回讀失敗。';
        orderMutationFlowStore.setFormalPlanCreation(caseNo, { ...state, status: 'observation_failed', error: message });
      }
      throw caught;
    }
  };

  const retryCreationReadback = () => {
    if (savingRef.current) return;
    const saved = orderMutationFlowStore.getFormalPlanCreation(caseNo, 'multi');
    if ((saved?.status !== 'observation_failed' && saved?.status !== 'observing') || saved.receipt === null) return;
    const request = sequence.current;
    void (async () => {
      savingRef.current = true;
      setSaving(true);
      try {
        await observeCreation(saved, request);
      } catch (caught) {
        const message = caught instanceof Error ? caught.message : '多月嫂方案正式回讀失敗。';
        if (request === sequence.current) setError(message);
      } finally {
        savingRef.current = false;
        if (request === sequence.current) setSaving(false);
      }
    })();
  };

  const confirmOriginalCreation = () => {
    if (savingRef.current) return;
    const saved = orderMutationFlowStore.getFormalPlanCreation(caseNo, 'multi');
    if (saved?.status !== 'outcome_unknown') return;
    const request = sequence.current;
    void (async () => {
      savingRef.current = true;
      setSaving(true);
      try {
        let receipt: FormalPlanCreationFlowState['receipt'];
        try {
          receipt = await matchingCandidateWorkflowClient.queryMatchingPlanReceipt(saved.command);
        } catch (caught) {
          if (!(caught instanceof ApiHttpError) || caught.status !== 404) throw caught;
          receipt = await matchingCandidateWorkflowClient.createMatchingPlan(saved.command);
        }
        const received: FormalPlanCreationFlowState = { ...saved, status: 'observation_failed', receipt, error: null };
        orderMutationFlowStore.setFormalPlanCreation(caseNo, received);
        await observeCreation(received, request);
      } catch (caught) {
        const message = caught instanceof Error ? caught.message : '目前正式方案查詢失敗。';
        const current = orderMutationFlowStore.getFormalPlanCreation(caseNo, 'multi');
        if (current?.status === 'outcome_unknown' && current.command.key === saved.command.key) {
          orderMutationFlowStore.setFormalPlanCreation(caseNo, { ...current, error: message });
        }
        if (request === sequence.current) setError(message);
      } finally {
        savingRef.current = false;
        if (request === sequence.current) setSaving(false);
      }
    })();
  };

  const combinations = query.status === 'ready'
    ? query.data.complete_combinations.filter((combination) => combination.length === segmentCount)
    : [];

  return (
    <section aria-label={`案件 ${caseNo} 多月嫂分段方案`}>
      <h4>多月嫂接續服務</h4>
      <p>一位月嫂無法全程承接時，可查詢由多位月嫂接續完成服務的方案。</p>
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
          <p>目前沒有可完整銜接的 {segmentCount} 段方案，請調整分段數或媒合條件後再查詢。</p>
          {query.data.conflicts.map((conflict, index) => <p key={index}>{conflict.work_date} · 月嫂 #{conflict.staff_id ?? '未指定'} · {conflict.reason_code}</p>)}
        </div>
      )}
      {combinations.map((combination, index) => (
        <article key={index} aria-label={`完整組合 ${index + 1}`}>
          {combination.map((segment) => <p key={segment.segment_index}>第 {segment.segment_index + 1} 段 · 月嫂 #{segment.staff_id} · {segment.start_date} → {segment.end_date}</p>)}
          <button type="button" disabled={busy || attempted || creationProtected} onClick={() => void create(combination)}>以完整組合 {index + 1} 建立正式 {segmentCount} 段方案</button>
        </article>
      ))}
      {saving && <p role="status">建立並回讀正式多月嫂方案中…</p>}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error} 請重新查詢正式狀態後確認，不自動重試。</p>}
      {formalPlanCreation?.status === 'outcome_unknown' && (
        <section aria-label="多月嫂方案建立結果未確定">
          <p role="alert">尚未確認是否建立成功。</p>
          <button type="button" data-control-id="orders.multi-plan-creation.reconcile-original" disabled={saving} onClick={confirmOriginalCreation}>確認建立結果</button>
        </section>
      )}
      {(formalPlanCreation?.status === 'observation_failed' || formalPlanCreation?.status === 'observing') && (
        <section aria-label="多月嫂方案建立回讀失敗">
          <p role="alert">方案已建立，請重新讀取最新狀態。</p>
          <button type="button" data-control-id="orders.multi-plan-creation.readback" disabled={saving} onClick={retryCreationReadback}>重新讀取</button>
        </section>
      )}
    </section>
  );
};
