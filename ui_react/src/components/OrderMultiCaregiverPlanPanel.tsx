import { useUnsavedDraft } from './UnsavedChanges';
import { CaregiverCommuteQuery } from './CaregiverCommute';
import { compareStaffUnionNumbers, staffDisplayLabel } from '../adapters/staff/staff_directory_adapter';
import { useEffect, useRef, useState, useSyncExternalStore, type FC } from 'react';
import { subscribeStaffAvailabilityChanges } from '../api/staff_availability/staff_availability_changes';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { sessionClient } from '../api/auth/session_client';
import { matchingCandidateWorkflowClient, type MatchingFilterPolicy, type MatchingPlanSegmentInput } from '../api/scheduling/matching_candidate_workflow_client';
import { waitingDepositLockClient } from '../api/scheduling/waiting_deposit_lock_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { orderMutationFlowStore, type FormalPlanCreationFlowState } from '../adapters/orders/order_mutation_flow_store';

interface Props {
  caseNo: string;
  filters: MatchingFilterPolicy;
  onObserved?: () => void;
  onBusyChange?: (busy: boolean) => void;
}

type StaffChoicesState =
  | { status: 'idle' | 'loading' }
  | { status: 'ready'; caseNo: string; filterKey: string; periodStart: string; periodEnd: string; staff: readonly { id: number; name: string; unionNo?: string | null }[] }
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

function choicesErrorMessage(error: unknown): string {
  if (error instanceof ApiHttpError) {
    if (error.code === 'matching_preference_source_not_ready') return '本案尚未填寫「下廚需求」，無法依下廚料理篩選。請到客戶名冊補齊本案下廚需求，或先取消勾選「下廚料理」再查詢；取消篩選不會修改案件資料。';
    if (error.code === 'official_service_dates_incomplete') return '服務日期尚未完整，請到「服務安排 → 確認日期」完成日期後再查詢。';
    if (error.code === 'caregiver_availability_stage_conflict') return '目前案件狀態不允許查詢候選，請重新讀取案件進度，確認目前應辦事項。';
  }
  return error instanceof Error ? error.message : '可選月嫂載入失敗。';
}

/** Save explicit service periods through the existing Scheduling owner. */
export const OrderMultiCaregiverPlanPanel: FC<Props> = ({ caseNo, filters, onObserved, onBusyChange }) => {
  const [segmentCount, setSegmentCount] = useState<2 | 3 | 4>(2);
  const [selectedStaffIds, setSelectedStaffIds] = useState<number[]>([0, 0]);
  const [segmentDates, setSegmentDates] = useState<{ start_date: string; end_date: string }[]>([
    { start_date: '', end_date: '' }, { start_date: '', end_date: '' },
  ]);
  const [staffChoices, setStaffChoices] = useState<StaffChoicesState>({ status: 'idle' });
  const [choicesRetry, setChoicesRetry] = useState(0);
  const [availabilityRevision, setAvailabilityRevision] = useState(0);
  useEffect(() => subscribeStaffAvailabilityChanges(() => setAvailabilityRevision(revision => revision + 1)), []);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [attempted, setAttempted] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sequence = useRef(0);
  const choicesController = useRef<AbortController | null>(null);
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
    if (saving || creationProtected) return;
    const controller = new AbortController();
    choicesController.current = controller;
    setStaffChoices({ status: 'loading' });
    void matchingCandidateWorkflowClient.searchSegmentedCaregivers(caseNo, 1, [], filters, { signal: controller.signal })
      .then((data) => {
        if (choicesController.current !== controller) return;
        if (data.case_no !== caseNo) throw new Error('可選月嫂查詢案件識別不一致。');
        const staff = data.candidate_options
          .filter((candidate) => candidate.segment_index === 0)
          .map((candidate) => ({ id: candidate.staff_id, name: staffDisplayLabel(candidate.staff_union_no, candidate.staff_name), unionNo: candidate.staff_union_no }))
          .sort(compareStaffUnionNumbers);
        setStaffChoices({ status: 'ready', caseNo, filterKey, periodStart: data.planned_start_date, periodEnd: data.planned_end_date, staff });
      })
      .catch((caught) => {
        if (choicesController.current === controller && !controller.signal.aborted) {
          setStaffChoices({ status: 'error', message: choicesErrorMessage(caught) });
        }
      });
    return () => {
      controller.abort();
      if (choicesController.current === controller) choicesController.current = null;
    };
  }, [caseNo, filters, filterKey, choicesRetry, availabilityRevision, saving, creationProtected]);

  useEffect(() => { setSelectedStaffIds(current => current.map(() => 0)); }, [caseNo, filterKey]);

  useEffect(() => {
    setSegmentDates((current) => current.map(() => ({ start_date: '', end_date: '' })));
  }, [caseNo]);

  useEffect(() => {
    sequence.current += 1;
    setAttempted(false);
    setMessage(null);
    setError(null);
    return () => {
      sequence.current += 1;
    };
  }, [caseNo, filterKey, segmentCount]);

  const busy = saving || creationProtected;
  useEffect(() => { onBusyChange?.(busy); }, [busy, onBusyChange]);
  useEffect(() => () => { onBusyChange?.(false); }, [onBusyChange]);

  const editDraft = () => {
    sequence.current += 1;
    setAttempted(false);
    setMessage(null);
    setError(null);
  };

  const selectStaff = (index: number, staffId: number) => {
    editDraft();
    setSelectedStaffIds((current) => current.map((id, position) => position === index ? staffId : id));
  };

  const selectDate = (index: number, field: 'start_date' | 'end_date', value: string) => {
    editDraft();
    setSegmentDates((current) => current.map((dates, position) => position === index ? { ...dates, [field]: value } : dates));
  };

  const selected = selectedStaffIds.slice(0, segmentCount);
  const canSave = staffChoices.status === 'ready'
    && staffChoices.caseNo === caseNo
    && staffChoices.filterKey === filterKey
    && selected.length === segmentCount
    && selected.every((id) => id > 0 && staffChoices.staff.some((candidate) => candidate.id === id))
    && new Set(selected).size === segmentCount
    && segmentDates.length === segmentCount
    && segmentDates.every((dates) => dates.start_date && dates.end_date && dates.start_date <= dates.end_date);

  const create = async () => {
    if (savingRef.current || attempted || creationProtected || !canSave) return;
    const segments = selected.map((staff_id, index) => ({ staff_id, ...segmentDates[index]! }));
    savingRef.current = true;
    setSaving(true);
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
      const command = {
        caseNo,
        kind: 'multi' as const,
        actor: sessionClient.getUser()?.username.trim() ?? '',
        asOf: new Date().toISOString().slice(0, 10),
        key: `orders-multi-plan-${crypto.randomUUID()}`,
        segments,
      };
      if (!command.actor) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
      setAttempted(true);
      orderMutationFlowStore.setFormalPlanCreation(caseNo, { status: 'applying', command, receipt: null, error: null });
      let receipt: FormalPlanCreationFlowState['receipt'];
      try {
        receipt = await matchingCandidateWorkflowClient.createMatchingPlan(command);
      } catch (caught) {
        if (caught instanceof ApiHttpError && caught.status >= 400 && caught.status < 500
          && caught.status !== 408 && caught.status !== 429 && !caught.retryable) {
          orderMutationFlowStore.clearFormalPlanCreation(caseNo, 'multi');
          if (request === sequence.current) setAttempted(false);
          throw caught;
        }
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
      setSaving(false);
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
      unsaved.markSaved();
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

  const unsaved = useUnsavedDraft('多人照護計畫', { '照護段數': segmentCount, '月嫂選擇': selectedStaffIds, '各段服務日期': segmentDates }, { busy, resetKey: caseNo });


  return (
    <section className="order-multi-panel" aria-label={`案件 ${caseNo} 多月嫂分段方案`}>
      <h4>多月嫂接續服務</h4>
      <p>選擇各段月嫂與服務起訖日，填好後直接儲存。</p>
      <form className="order-multi-setup" onSubmit={(event) => { event.preventDefault(); void create(); }}>
        <div className="order-multi-setup-heading">
          <div>
            <h5>安排各段服務</h5>
            <p>各段須完整銜接案件服務期間；儲存時會檢查月嫂檔期。</p>
          </div>
          {staffChoices.status === 'ready' && (
            <p>案件預計服務期間<br /><strong>{staffChoices.periodStart} ～ {staffChoices.periodEnd}</strong></p>
          )}
        </div>
        <div className={`order-multi-selectors${segmentCount > 2 ? ' many' : ''}`}>
          <label>服務分段數
            <select aria-label="多月嫂服務分段數" value={segmentCount} disabled={busy} onChange={(event) => {
              const count = Number(event.target.value) as 2 | 3 | 4;
              setSegmentCount(count);
              setSelectedStaffIds((current) => Array.from({ length: count }, (_, index) => current[index] ?? 0));
              setSegmentDates((current) => Array.from({ length: count }, (_, index) => current[index] ?? { start_date: '', end_date: '' }));
            }}>
              <option value={2}>2 段</option><option value={3}>3 段</option><option value={4}>4 段</option>
            </select>
          </label>
          {Array.from({ length: segmentCount }, (_, index) => (
            <fieldset key={index} className="order-multi-card" disabled={busy || staffChoices.status !== 'ready'}>
              <legend>第 {index + 1} 段 · {index === 0 ? '先服務' : '接續服務'}</legend>
              <label>月嫂
              <select
                aria-label={`第 ${index + 1} 段月嫂`}
                value={selectedStaffIds[index] ?? 0}
                disabled={busy || staffChoices.status !== 'ready'}
                onChange={(event) => selectStaff(index, Number(event.target.value))}
              >
                <option value={0}>請選擇月嫂</option>
                {staffChoices.status === 'ready' && staffChoices.staff.map((candidate) => (
                  <option key={candidate.id} value={candidate.id} disabled={selectedStaffIds.some((id, position) => position !== index && id === candidate.id)}>
                    {candidate.name}
                  </option>
                ))}
              </select>
              </label>
              <label>服務開始日
                <input type="date" required aria-label={`第 ${index + 1} 段服務開始日`}
                  min={staffChoices.status === 'ready' ? staffChoices.periodStart : undefined}
                  max={segmentDates[index]?.end_date || (staffChoices.status === 'ready' ? staffChoices.periodEnd : undefined)}
                  value={segmentDates[index]?.start_date ?? ''}
                  onChange={(event) => selectDate(index, 'start_date', event.target.value)} />
              </label>
              <label>服務結束日
                <input type="date" required aria-label={`第 ${index + 1} 段服務結束日`}
                  min={segmentDates[index]?.start_date || (staffChoices.status === 'ready' ? staffChoices.periodStart : undefined)}
                  max={staffChoices.status === 'ready' ? staffChoices.periodEnd : undefined}
                  value={segmentDates[index]?.end_date ?? ''}
                  onChange={(event) => selectDate(index, 'end_date', event.target.value)} />
              </label>
              {!!selectedStaffIds[index] && <CaregiverCommuteQuery caseNo={caseNo} staffId={selectedStaffIds[index]} staffName={staffChoices.status === 'ready' ? staffChoices.staff.find(staff => staff.id === selectedStaffIds[index])?.name ?? '月嫂' : '月嫂'} />}
            </fieldset>
          ))}
        </div>
        <p className="order-multi-hint">各段須選不同月嫂，下一段從前一段結束日的隔天接續，不重疊、不留空缺。</p>
        {staffChoices.status === 'loading' && <p role="status">正在載入可選月嫂…</p>}
        {staffChoices.status === 'error' && (
          <div role="alert">
            <p>{staffChoices.message}</p>
            <button type="button" disabled={busy} onClick={() => setChoicesRetry((current) => current + 1)}>重新載入可選月嫂</button>
          </div>
        )}
        {staffChoices.status === 'ready' && staffChoices.staff.length < segmentCount && (
          <p role="status">目前可選月嫂不足 {segmentCount} 位，請調整媒合條件後再查詢。</p>
        )}
        <button className="order-v2-open-drawer" type="submit" disabled={busy || !canSave || attempted}>
          儲存 {segmentCount} 段服務安排
        </button>
      </form>
      {saving && <p role="status">建立並回讀正式多月嫂方案中…</p>}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
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
