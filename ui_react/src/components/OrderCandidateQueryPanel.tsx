import { useEffect, useRef, useState, useSyncExternalStore, type FC } from 'react';
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
  type MatchingFilterPolicy,
} from '../api/scheduling/matching_candidate_workflow_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { OrderMultiCaregiverPlanPanel } from './OrderMultiCaregiverPlanPanel';

interface OrderCandidateQueryPanelProps {
  caseNo: string;
  onPoolReadback?: () => void;
}

type CandidateQueryState =
  | { status: 'idle' }
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

const FILTER_OPTIONS: readonly {
  key: keyof MatchingFilterPolicy;
  label: string;
}[] = [
  { key: 'region', label: '服務地區' },
  { key: 'cooking', label: '下廚料理' },
  { key: 'preferred_service_days', label: '偏好服務日' },
  { key: 'daily_service_hours', label: '每日服務時數' },
];

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : fallback;
}

function queryFailure(error: unknown): CandidateQueryState {
  const message = errorMessage(error, '正式候選查詢失敗');
  if (error instanceof ApiHttpError && MATCHING_BLOCKER_CODES.has(error.code)) {
    return { status: 'blocked', message };
  }
  return { status: 'error', message };
}

function formalCandidates(data: MatchingAvailability): MatchingCandidateOption[] {
  return data.candidate_options.filter(
    (candidate) => candidate.segment_index === 0 && candidate.full_case_coverage,
  );
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

const CandidateQueryForCase: FC<OrderCandidateQueryPanelProps> = ({ caseNo, onPoolReadback }) => {
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
  const [filters, setFilters] = useState<MatchingFilterPolicy>(() => ({ ...defaultMatchingFilterPolicy }));
  const [queryState, setQueryState] = useState<CandidateQueryState>({ status: 'idle' });
  const [selectedStaffIds, setSelectedStaffIds] = useState<ReadonlySet<number>>(() => new Set());
  const [addState, setAddState] = useState<CandidateAddState>({ status: 'idle' });
  const [multiBusy, setMultiBusy] = useState(false);
  const flow = useSyncExternalStore(subscribeCandidatePoolAdd, () => orderMutationFlowStore.getCandidatePoolAdd(caseNo));
  const addInFlight = useRef(false);

  const updateFilter = (key: keyof MatchingFilterPolicy) => {
    setFilters((current) => ({ ...current, [key]: !current[key] }));
    setSelectedStaffIds(new Set());
    setAddState({ status: 'idle' });
    setQueryState({ status: 'idle' });
  };

  const queryCandidates = () => {
    queryController.current?.abort();
    const controller = new AbortController();
    queryController.current = controller;
    setSelectedStaffIds(new Set());
    setAddState({ status: 'idle' });
    setQueryState({ status: 'loading' });
    void matchingCandidateWorkflowClient.searchInquiryCandidates(caseNo, filters, { signal: controller.signal })
      .then((data) => {
        if (!mounted.current || queryController.current !== controller) return;
        if (data.case_no !== caseNo) throw new Error('候選詢問案件識別不一致。');
        setQueryState({ status: 'ready', data });
      })
      .catch((error) => {
        if (mounted.current && queryController.current === controller) setQueryState(queryFailure(error));
      });
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
      staffName: candidate.staff_name,
    }));
    orderMutationFlowStore.setCandidatePoolAdd(command.caseNo, {
      status: 'observed', command, receipt: data, readbackStaff, error: null,
    });
    if (!mounted.current || command.caseNo !== caseNo) return;
    setSelectedStaffIds(new Set());
    setAddState({ status: 'success', data, readbackStaff });
    onPoolReadback?.();
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

  const addSelectedCandidates = () => {
    if (queryState.status !== 'ready' || addInFlight.current
      || flow?.status === 'applying' || flow?.status === 'observing'
      || flow?.status === 'outcome_unknown' || flow?.status === 'observation_failed') return;
    const selected = formalCandidates(queryState.data).filter((candidate) => selectedStaffIds.has(candidate.staff_id));
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

  return (
    <section aria-label={`案件 ${caseNo} 正式候選查詢`}>
      <fieldset disabled={busy} aria-label="媒合篩選條件">
        <legend>媒合篩選條件</legend>
        {FILTER_OPTIONS.map((option) => (
          <label key={option.key}>
            <input
              type="checkbox"
              checked={filters[option.key]}
              onChange={() => updateFilter(option.key)}
            />
            {option.label}
          </label>
        ))}
      </fieldset>

      <button
        type="button"
        className="order-v2-open-drawer"
        onClick={queryCandidates}
        disabled={busy}
      >
        {queryState.status === 'loading' ? '查詢中…' : '查詢符合條件月嫂'}
      </button>

      {queryState.status === 'idle' && (
        <div className="order-v2-notice warning" role="status">
          <strong>尚未查詢</strong>
          <span>依預計服務期間查詢；尚未填寫的需求待確認，不阻擋初步詢問。</span>
        </div>
      )}

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

          {candidates.length > 0 ? (
            <>
              <div className="order-v2-notice warning" role="status">
                <strong>符合 {candidates.length} 位</strong>
                <span>以下月嫂在預計期間無檔期衝突，可先詢問意願；尚未確認的需求待確認，正式服務日期仍須後續確認。</span>
              </div>
              <div className="order-v2-business-summary" aria-label="正式符合條件候選">
                {candidates.map((candidate) => (
                  <label key={candidate.staff_id}>
                    <input
                      type="checkbox"
                      aria-label={`選擇正式候選 ${candidate.staff_name}`}
                      checked={selectedStaffIds.has(candidate.staff_id)}
                      onChange={() => toggleCandidate(candidate.staff_id)}
                      disabled={busy}
                    />
                    <span>
                      <strong>{candidate.staff_name}</strong><br />
                      月嫂 #{candidate.staff_id} · 已檢查預計期間 {candidate.supported_day_count}/{candidate.required_day_count} 個日曆日無衝突
                    </span>
                  </label>
                ))}
              </div>
              <button
                type="button"
                className="order-v2-open-drawer"
                onClick={addSelectedCandidates}
                disabled={selectedStaffIds.size === 0 || busy || recoveryPending}
              >
                {addState.status === 'saving' ? '加入候選池中…' : `加入候選池（${selectedStaffIds.size}）`}
              </button>
            </>
          ) : (
            <div className="order-v2-notice blocked" role="status">
              <strong>沒有符合條件</strong>
              <span>目前沒有可完整承接的月嫂，可調整篩選條件後重新查詢。</span>
              {queryState.data.conflicts.map((conflict, index) => (
                <span key={`${conflict.segment_index}:${conflict.staff_id ?? 'none'}:${conflict.work_date}:${index}`}>
                  {conflict.work_date} · 月嫂 #{conflict.staff_id ?? '未指定'} · {conflict.reason_code}
                </span>
              ))}
            </div>
          )}
        </>
      )}

      {completedAdd && (
        <div className="order-v2-notice warning" role="status">
          <strong>候選池回讀完成</strong>
          <span>
            Pool #{completedAdd.data.pool_id} · 已回讀 {completedAdd.readbackStaff.length} 位本次寫入候選：
            {completedAdd.readbackStaff.map((candidate) => `${candidate.staffName} (#${candidate.staffId})`).join('、')}。
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
      <fieldset disabled={queryState.status === 'loading' || addState.status === 'saving'} style={{ border: 0, padding: 0 }}>
        <OrderMultiCaregiverPlanPanel caseNo={caseNo} filters={filters} onObserved={onPoolReadback} onBusyChange={setMultiBusy} />
      </fieldset>
    </section>
  );
};

export default OrderCandidateQueryPanel;
