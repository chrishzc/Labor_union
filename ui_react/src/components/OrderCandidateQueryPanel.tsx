import { useUnsavedDraft } from './UnsavedChanges';
import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type FC } from 'react';
import { subscribeStaffAvailabilityChanges } from '../api/staff_availability/staff_availability_changes';
import {
  candidateContactPoolClient,
  createCandidateAddCommand,
  type AddCandidatesResult,
  type CandidateAddCommand,
} from '../api/scheduling/candidate_contact_pool_client';
import {
  defaultMatchingFilterPolicy,
  matchingCandidateWorkflowClient,
  type MatchingAvailability,
  type MatchingCandidateOption,
} from '../api/scheduling/matching_candidate_workflow_client';
import { ApiHttpError, ApiNetworkError, ApiTimeoutError } from '../api/shared/typed_errors';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { OrderMultiCaregiverPlanPanel } from './OrderMultiCaregiverPlanPanel';
import { CaregiverCommuteQuery, CommuteUsagePanel } from './CaregiverCommute';
import { compareStaffUnionNumbers, staffDisplayLabel } from '../adapters/staff/staff_directory_adapter';

interface OrderCandidateQueryPanelProps {
  caseNo: string;
  onPoolReadback?: (candidateIds?: readonly number[]) => void;
  includeMultiCaregiver?: boolean;
  onEditStateChange?: (state: { dirty: boolean; busy: boolean }) => void;
  presentation?: 'legacy' | 'workbench';
}

type CandidateQueryState =
  | { status: 'loading' }
  | { status: 'ready'; data: MatchingAvailability }
  | { status: 'blocked'; message: string }
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

const MATCHING_BLOCKER_CODES = new Set([
  'matching_preference_source_not_ready',
  'official_service_dates_incomplete',
  'caregiver_availability_stage_conflict',
]);

function CandidateServicePreferences({ candidate }: { candidate: MatchingCandidateOption }) {
  const labels = { matched: '符合', not_matched: '不符合', pending: '待確認' };
  return <span className="candidate-service-preferences" aria-label={`${candidate.staff_name}服務偏好`}>
    {([['region', '區域'], ['preferred_service_days', '週間服務']] as const).map(([key, label]) => {
      const condition = candidate.matching_conditions[key];
      return <span key={key} className={`candidate-preference-badge ${condition.status}`}>
        {label}：{condition.staff_values.join('、') || '尚未登錄'}<span> · {labels[condition.status]}</span>
      </span>;
    })}
  </span>;
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiHttpError) {
    if (error.code === 'matching_preference_source_not_ready') return '案件服務期間或來源資料尚未備妥，請先確認案件服務方式與日期，再重新查詢。';
    if (error.code === 'official_service_dates_incomplete') return '服務日期尚未完整，請到「服務安排 → 確認日期」完成日期後再查詢。';
    if (error.code === 'caregiver_availability_stage_conflict') return '目前案件狀態不允許查詢候選，請重新讀取案件進度，確認目前應辦事項。';
  }
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : fallback;
}

function queryFailure(error: unknown): CandidateQueryState {
  const message = error instanceof ApiNetworkError ? '目前無法連線，請確認網路後重新查詢。'
    : error instanceof ApiTimeoutError ? '查詢逾時，請稍後重新查詢。'
    : errorMessage(error, '候選月嫂查詢失敗');
  if (error instanceof ApiHttpError && MATCHING_BLOCKER_CODES.has(error.code)) {
    return { status: 'blocked', message };
  }
  return { status: 'error', message };
}

function formalCandidates(data: MatchingAvailability): MatchingCandidateOption[] {
  return data.candidate_options.filter(
    (candidate) => candidate.segment_index === 0,
  ).sort((left, right) => compareStaffUnionNumbers(
    { id: left.staff_id, unionNo: left.staff_union_no },
    { id: right.staff_id, unionNo: right.staff_union_no },
  ));
}

function sameStaffIds(expected: readonly number[], actual: readonly number[]): boolean {
  if (expected.length !== actual.length) return false;
  const expectedSorted = [...expected].sort((left, right) => left - right);
  const actualSorted = [...actual].sort((left, right) => left - right);
  return expectedSorted.every((staffId, index) => staffId === actualSorted[index]);
}

const subscribeCandidatePoolAdd = (listener: () => void) => orderMutationFlowStore.subscribe(listener);

export const OrderCandidateQueryPanel: FC<OrderCandidateQueryPanelProps> = (props) => (
  <CandidateQueryForCase key={props.caseNo} {...props} />
);

const CandidateQueryForCase: FC<OrderCandidateQueryPanelProps> = ({ caseNo, onPoolReadback, includeMultiCaregiver = true, onEditStateChange, presentation = 'legacy' }) => {
  const mounted = useRef(true);
  const queryController = useRef<AbortController | null>(null);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      queryController.current?.abort();
      queryController.current = null;
    };
  }, []);
  const [queryState, setQueryState] = useState<CandidateQueryState>({ status: 'loading' });
  const [selectedStaffIds, setSelectedStaffIds] = useState<ReadonlySet<number>>(() => new Set());
  const [joinedStaffIds, setJoinedStaffIds] = useState<ReadonlySet<number>>(() => new Set());
  const [outdatedStaffIds, setOutdatedStaffIds] = useState<ReadonlySet<number>>(() => new Set());
  const [addState, setAddState] = useState<CandidateAddState>({ status: 'idle' });
  const [multiBusy, setMultiBusy] = useState(false);
  const flow = useSyncExternalStore(subscribeCandidatePoolAdd, () => orderMutationFlowStore.getCandidatePoolAdd(caseNo));
  const addInFlight = useRef(false);
  const [availabilityRevision, setAvailabilityRevision] = useState(0);
  const observedAvailabilityRevision = useRef(0);
  useEffect(() => subscribeStaffAvailabilityChanges(() => setAvailabilityRevision(revision => revision + 1)), []);

  const queryCandidates = useCallback(() => {
    queryController.current?.abort();
    const controller = new AbortController();
    queryController.current = controller;
    setSelectedStaffIds(new Set());
    setAddState({ status: 'idle' });
    setQueryState({ status: 'loading' });
    void Promise.all([
      matchingCandidateWorkflowClient.searchInquiryCandidates(caseNo, defaultMatchingFilterPolicy, { signal: controller.signal }),
      presentation === 'workbench' ? candidateContactPoolClient.query(caseNo, { signal: controller.signal }) : Promise.resolve(null),
    ]).then(([data, pool]) => {
        if (!mounted.current || queryController.current !== controller) return;
        if (data.case_no !== caseNo || (pool && pool.case_no !== caseNo)) throw new Error('候選詢問案件識別不一致。');
        if (pool) {
          const active = pool.candidates.filter(value => value.status !== 'withdrawn');
          const outdated = new Set(active.filter(value => value.service_start_date !== data.planned_start_date || value.service_end_date !== data.planned_end_date).map(value => value.staff_id));
          setOutdatedStaffIds(outdated);
          setJoinedStaffIds(new Set(active.filter(value => !outdated.has(value.staff_id)).map(value => value.staff_id)));
        }
        setQueryState({ status: 'ready', data });
      })
      .catch((error) => {
        if (mounted.current && queryController.current === controller) setQueryState(queryFailure(error));
      });
  }, [caseNo, presentation]);

  useEffect(() => { queryCandidates(); }, [queryCandidates]);

  useEffect(() => {
    if (availabilityRevision === observedAvailabilityRevision.current || addInFlight.current || multiBusy
      || (flow && ['applying', 'observing', 'outcome_unknown', 'observation_failed'].includes(flow.status))) return;
    observedAvailabilityRevision.current = availabilityRevision;
    queryCandidates();
  }, [availabilityRevision, queryCandidates, multiBusy, addState.status, flow]);

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

  const observeCandidatePoolAdd = async (command: CandidateAddCommand, data: AddCandidatesResult) => {
    orderMutationFlowStore.setCandidatePoolAdd(command.caseNo, {
      status: 'observing', command, receipt: data, readbackStaff: [], error: null,
    });
    const pool = await candidateContactPoolClient.query(command.caseNo);
    const expectedStaffIds = command.candidates.map((candidate) => candidate.staff_id);
    const insertedIds = new Set(data.candidate_ids);
    const readbackCandidates = pool.candidates.filter((candidate) => insertedIds.has(candidate.id));
    if (pool.case_no !== command.caseNo || pool.pool_id !== data.pool_id
      || !sameStaffIds(expectedStaffIds, readbackCandidates.map((candidate) => candidate.staff_id))
      || !command.candidates.every((input) => readbackCandidates.some((candidate) => (
        candidate.staff_id === input.staff_id
        && candidate.service_start_date === input.start_date
        && candidate.service_end_date === input.end_date
      )))) {
      throw new Error('候選池回讀與本次寫入選擇不一致。');
    }
    const readbackStaff = readbackCandidates.map((candidate) => ({
      staffId: candidate.staff_id,
      staffName: staffDisplayLabel(candidate.staff_union_no, candidate.staff_name),
    }));
    orderMutationFlowStore.setCandidatePoolAdd(command.caseNo, {
      status: 'observed', command, receipt: data, readbackStaff, error: null,
    });
    if (!mounted.current || command.caseNo !== caseNo) return;
    if (presentation === 'workbench') {
      const active = pool.candidates.filter(value => value.status !== 'withdrawn');
      const period = command.candidates[0];
      const outdated = new Set(active.filter(value => value.service_start_date !== period.start_date || value.service_end_date !== period.end_date).map(value => value.staff_id));
      setJoinedStaffIds(new Set(active.filter(value => !outdated.has(value.staff_id)).map(value => value.staff_id)));
      setOutdatedStaffIds(outdated);
    }
    setSelectedStaffIds(new Set());
    setAddState({ status: 'success', data, readbackStaff });
    onPoolReadback?.(data.candidate_ids);
  };

  const failObservation = (command: CandidateAddCommand, error: unknown) => {
    const saved = orderMutationFlowStore.getCandidatePoolAdd(command.caseNo);
    if (saved?.receipt) {
      orderMutationFlowStore.setCandidatePoolAdd(command.caseNo, {
        ...saved,
        status: 'observation_failed',
        error: errorMessage(error, '候選池寫入後回讀失敗'),
      });
    }
    if (mounted.current && command.caseNo === caseNo) {
      setAddState({ status: 'error', message: errorMessage(error, '候選池寫入後回讀失敗') });
    }
  };

  const submitCandidatePoolAdd = async (command: CandidateAddCommand) => {
    if (addInFlight.current) return;
    const current = orderMutationFlowStore.getCandidatePoolAdd(command.caseNo);
    const recoveringUnknown = current?.status === 'outcome_unknown';
    addInFlight.current = true;
    setAddState({ status: 'saving' });
    orderMutationFlowStore.setCandidatePoolAdd(command.caseNo, {
      status: 'applying', command, receipt: null, readbackStaff: [], error: null,
    });
    let data: AddCandidatesResult;
    try {
      data = await candidateContactPoolClient.addCandidates(command);
    } catch (error) {
      const rejected = error instanceof ApiHttpError && error.status >= 400 && error.status < 500
        && error.status !== 408 && error.status !== 429;
      if (rejected && !recoveringUnknown) orderMutationFlowStore.clearCandidatePoolAdd(command.caseNo);
      else orderMutationFlowStore.setCandidatePoolAdd(command.caseNo, {
        status: 'outcome_unknown', command, receipt: null, readbackStaff: [],
        error: recoveringUnknown
          ? '候選池寫入結果仍未確認；請恢復權限後使用原操作重新確認結果。'
          : '候選池寫入結果尚未確認；請使用原操作重新確認結果。',
      });
      if (mounted.current && command.caseNo === caseNo) {
        setAddState({ status: 'error', message: rejected && !recoveringUnknown
          ? errorMessage(error, '候選池寫入失敗')
          : recoveringUnknown
            ? '候選池寫入結果仍未確認；請恢復權限後使用原操作重新確認結果。'
            : '候選池寫入結果尚未確認；請使用原操作重新確認結果。' });
      }
      addInFlight.current = false;
      return;
    }
    orderMutationFlowStore.setCandidatePoolAdd(command.caseNo, {
      status: 'observation_failed', command, receipt: data, readbackStaff: [], error: null,
    });
    try {
      await observeCandidatePoolAdd(command, data);
    } catch (error) {
      failObservation(command, error);
    } finally {
      addInFlight.current = false;
    }
  };

  const addSelectedCandidates = (staffIds: ReadonlySet<number> = selectedStaffIds) => {
    if (queryState.status !== 'ready' || addInFlight.current
      || flow?.status === 'applying' || flow?.status === 'observing'
      || flow?.status === 'outcome_unknown' || flow?.status === 'observation_failed') return;
    const selected = formalCandidates(queryState.data).filter((candidate) => staffIds.has(candidate.staff_id)
      && (presentation !== 'workbench' || !joinedStaffIds.has(candidate.staff_id)));
    if (selected.length === 0) {
      setAddState({ status: 'error', message: '請先選擇至少一位正式候選。' });
      return;
    }
    if (flow?.status === 'observed') orderMutationFlowStore.clearCandidatePoolAdd(caseNo);
    try {
      const command = createCandidateAddCommand(caseNo, selected.map((candidate) => ({
        staff_id: candidate.staff_id,
        start_date: candidate.selected_segment_start,
        end_date: candidate.selected_segment_end,
      })));
      void submitCandidatePoolAdd(command);
    } catch (error) {
      setAddState({ status: 'error', message: errorMessage(error, '無法建立候選池操作。') });
    }
  };

  const retryCandidatePoolAdd = () => {
    const current = orderMutationFlowStore.getCandidatePoolAdd(caseNo);
    if (current?.status === 'outcome_unknown') void submitCandidatePoolAdd(current.command);
  };

  const retryCandidatePoolReadback = () => {
    const current = orderMutationFlowStore.getCandidatePoolAdd(caseNo);
    if (addInFlight.current || current?.status !== 'observation_failed' || !current.receipt) return;
    addInFlight.current = true;
    setAddState({ status: 'saving' });
    void observeCandidatePoolAdd(current.command, current.receipt)
      .catch((error) => failObservation(current.command, error))
      .finally(() => { addInFlight.current = false; });
  };

  const recoveryPending = flow?.status === 'applying' || flow?.status === 'observing'
    || flow?.status === 'outcome_unknown' || flow?.status === 'observation_failed';
  const busy = queryState.status === 'loading' || addState.status === 'saving' || multiBusy
    || flow?.status === 'applying' || flow?.status === 'observing';
  const completedAdd = addState.status === 'success' ? addState : flow?.status === 'observed' && flow.receipt
    ? { status: 'success' as const, data: flow.receipt, readbackStaff: flow.readbackStaff }
    : null;
  useEffect(() => { onEditStateChange?.({ dirty: selectedStaffIds.size > 0, busy: busy || recoveryPending }); }, [selectedStaffIds, busy, recoveryPending, onEditStateChange]);
  useEffect(() => () => { onEditStateChange?.({ dirty: false, busy: false }); }, [onEditStateChange]);
  useUnsavedDraft('新增詢問人選', { '已選月嫂': [...selectedStaffIds] }, { baseline: { '已選月嫂': [] }, busy: multiBusy || addState.status === 'saving' || !!flow });


  return (
    <section aria-label={`案件 ${caseNo} 候選月嫂查詢`}>
      <p className="order-v2-row-meta">區域與週間服務僅作提示，不符合仍可加入候選池並協調。</p>
      <CommuteUsagePanel />

      <button
        type="button"
        className="order-v2-open-drawer"
        onClick={queryCandidates}
        disabled={busy}
      >
        {queryState.status === 'loading' ? '正在載入月嫂…' : '重新查詢'}
      </button>

      {queryState.status === 'loading' && (
        <div className="order-v2-notice warning" role="status">
          <strong>查詢中</strong>
          <span>正在向正式媒合服務查詢候選月嫂。</span>
        </div>
      )}

      {queryState.status === 'blocked' && (
        <div className="order-v2-notice blocked" role="alert">
          <strong>被既有條件阻擋</strong>
          <span>{queryState.message}</span>
        </div>
      )}

      {queryState.status === 'error' && (
        <div className="order-v2-notice blocked" role="alert">
          <strong>查詢失敗</strong>
          <span>{queryState.message}</span>
        </div>
      )}

      {queryState.status === 'ready' && (
        <>
          <div className="order-v2-case-meta">
            <span>服務期間：{queryState.data.planned_start_date} ～ {queryState.data.planned_end_date}</span>
          </div>
          {candidates[0] && <div className="candidate-query-requirements" aria-label="本案需求">
            <strong>本案需求</strong>
            <span>服務地區：{candidates[0].matching_conditions.region.required_value || '待確認'}</span>
            <span>週間服務：{candidates[0].matching_conditions.preferred_service_days.required_value || '待確認'}</span>
          </div>}

          {candidates.length > 0 ? (
            <>
              <div className="order-v2-notice warning" role="status">
                <strong>可詢問 {candidates.length} 位</strong>
                <span>有檔期衝突仍可加入候選池並協調；排班前須確認調整後的完整服務日期。</span>
              </div>
              <div className="order-v2-business-summary" aria-label="可詢問月嫂">
                {candidates.map((candidate) => presentation === 'workbench' ? <div key={candidate.staff_id} className="candidate-add-row">
                  <div className="candidate-add-details"><div className="candidate-name-and-preferences"><strong>{staffDisplayLabel(candidate.staff_union_no, candidate.staff_name)}</strong><CandidateServicePreferences candidate={candidate} /></div>空閒 {candidate.supported_day_count}/{candidate.required_day_count} 天
                    {!candidate.full_case_coverage && <span role="status"> · 有檔期衝突，待公會協調</span>}
                    {queryState.data.conflicts.some(value => value.staff_id === candidate.staff_id && value.reason_code === 'buffer') && <span role="status"> · 七天緩衝期重疊，僅提醒</span>}
                    {queryState.data.conflicts.some(value => value.staff_id === candidate.staff_id) && <details><summary>查看衝突日期與原因</summary><ul>
                      {Object.entries({ active_lock: '其他案件已保留檔期', assignment: '已有正式排班', schedule: '已有服務排程', staff_unavailability: '月嫂不可服務', requires_review: '既有排程待核對', coverage_gap: '此段服務尚缺可用人選', outside_case_period: '超出本案服務期間', draft_overlap: '方案服務段落重疊', buffer: '七天緩衝期（僅提醒，不阻擋）' }).map(([code, label]) => {
                        const dates = [...new Set(queryState.data.conflicts.filter(value => value.staff_id === candidate.staff_id && value.reason_code === code).map(value => value.work_date))].sort();
                        return dates.length > 0 ? <li key={code}>{label}：{dates.join('、')}</li> : null;
                      })}
                    </ul></details>}
                    <CaregiverCommuteQuery caseNo={caseNo} staffId={candidate.staff_id} staffName={candidate.staff_name} />
                  </div>
                  {outdatedStaffIds.has(candidate.staff_id) && <p role="status">原詢問期間與本次不同；更新後須重新記錄接案意願。</p>}
                  <button type="button" aria-label={`${joinedStaffIds.has(candidate.staff_id) ? '已加入候選池' : outdatedStaffIds.has(candidate.staff_id) ? '更新詢問期間' : '加入候選池'}（${candidate.staff_name}）`}
                    disabled={joinedStaffIds.has(candidate.staff_id) || busy || recoveryPending}
                    onClick={() => addSelectedCandidates(new Set([candidate.staff_id]))}>
                    {joinedStaffIds.has(candidate.staff_id) ? '已加入' : addState.status === 'saving' && flow?.command.candidates.some(value => value.staff_id === candidate.staff_id) ? '儲存中…' : outdatedStaffIds.has(candidate.staff_id) ? '更新詢問期間' : '加入候選池'}
                  </button>
                </div> : (
                  <label key={candidate.staff_id}>
                    <input
                      type="checkbox"
                      aria-label={`選擇正式候選 ${candidate.staff_name}`}
                      checked={selectedStaffIds.has(candidate.staff_id)}
                      onChange={() => toggleCandidate(candidate.staff_id)}
                      disabled={busy}
                    />
                    <span>
                      <span className="candidate-name-and-preferences"><strong>{staffDisplayLabel(candidate.staff_union_no, candidate.staff_name)}</strong><CandidateServicePreferences candidate={candidate} /></span>
                      空閒 {candidate.supported_day_count}/{candidate.required_day_count} 天
                      {!candidate.full_case_coverage && <span role="status"> · 有檔期衝突，待公會協調</span>}
                      {queryState.data.conflicts.some((conflict) => conflict.staff_id === candidate.staff_id && conflict.reason_code === 'buffer') && <span role="status"> · 七天緩衝期重疊，僅提醒</span>}
                    </span>
                  </label>
                ))}
              </div>
              {presentation === 'legacy' && <button
                type="button"
                className="order-v2-open-drawer"
                onClick={() => addSelectedCandidates()}
                disabled={selectedStaffIds.size === 0 || busy || recoveryPending}
              >
                {addState.status === 'saving' ? '正在加入…' : `加入候選池（${selectedStaffIds.size}）`}
              </button>}
            </>
          ) : (
            <div className="order-v2-notice blocked" role="status">
              <strong>目前沒有可詢問月嫂</strong>
              <span>請確認案件服務期間與月嫂資料，或稍後重新查詢。</span>
            </div>
          )}
        </>
      )}

      {completedAdd && presentation === 'workbench' && <p role="status">已加入：{completedAdd.readbackStaff.map(value => value.staffName).join('、')}。可繼續加入其他人選，或關閉抽屜回到候選清單。</p>}
      {completedAdd && presentation === 'legacy' && (
        <div className="order-v2-notice warning" role="status">
          <strong>候選池回讀完成</strong>
          <span>
            Pool #{completedAdd.data.pool_id} · 已回讀 {completedAdd.readbackStaff.length} 位本次寫入候選：
            {completedAdd.readbackStaff.map((candidate) => candidate.staffName).join('、')}。
          </span>
        </div>
      )}
      {(addState.status === 'error' || flow?.status === 'outcome_unknown' || flow?.status === 'observation_failed') && (
        <div className="order-v2-notice blocked" role="alert">
          <strong>候選池寫入／回讀失敗</strong>
          <span>{flow?.error ?? (addState.status === 'error' ? addState.message : '候選池寫入後回讀失敗')}</span>
        </div>
      )}
      {flow?.status === 'outcome_unknown' && <button type="button" onClick={retryCandidatePoolAdd}>以原操作重新確認加入候選池</button>}
      {flow?.status === 'observation_failed' && <button type="button" onClick={retryCandidatePoolReadback}>只重新讀取候選池結果</button>}
      {includeMultiCaregiver && <fieldset disabled={queryState.status === 'loading' || addState.status === 'saving'} style={{ border: 0, padding: 0 }}>
        <OrderMultiCaregiverPlanPanel caseNo={caseNo} filters={defaultMatchingFilterPolicy} onObserved={onPoolReadback} onBusyChange={setMultiBusy} />
      </fieldset>}
    </section>
  );
};

export default OrderCandidateQueryPanel;
