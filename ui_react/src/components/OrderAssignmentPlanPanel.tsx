import { useEffect, useRef, useState, type FC } from 'react';
import type { AssignmentPlan } from '../api/orders/order_query_schemas';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { waitingDepositLockClient, type ActiveWaitingDepositPlan } from '../api/scheduling/waiting_deposit_lock_client';
import { MatchingScheduleAndAssignmentActions } from './MatchingScheduleAndAssignmentActions';
import { ServiceBeforeReplacementActions } from './ServiceBeforeReplacementActions';
import { createStaffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { staffDisplayLabel } from '../adapters/staff/staff_directory_adapter';

interface OrderAssignmentPlanPanelProps {
  caseNo: string;
  revision?: number;
  onObserved?: () => void;
  onOpenReplacement?: () => void;
  contractReady?: boolean;
  depositReady?: boolean;
  onOpenDates?: () => void;
  onOpenRecommendation?: () => void;
  historicalArrangementPending?: boolean;
  onEditStateChange?: (state: { dirty: boolean; busy: boolean }) => void;
}

type ReadState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: { assignment: AssignmentPlan; matchingPlan: ActiveWaitingDepositPlan | null } }
  | { status: 'error'; message: string };

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '正式指派與排班資料讀取失敗';
}

export const OrderAssignmentPlanPanel: FC<OrderAssignmentPlanPanelProps> = ({ caseNo, onObserved, onOpenReplacement, revision, historicalArrangementPending = false, onEditStateChange, contractReady, depositReady, onOpenDates, onOpenRecommendation }) => {
  const [state, setState] = useState<ReadState>({ status: 'idle' });
  const [replacementOpen, setReplacementOpen] = useState(false);
  const [names, setNames] = useState<Record<number, string>>({});
  useEffect(() => {
    if (state.status !== 'ready') return;
    const controller = new AbortController();
    const ids = [...new Set([...state.data.assignment.assignments.map(item => item.staff_id), ...(state.data.matchingPlan?.segments ?? []).map(item => item.staffId)])];
    void Promise.all(ids.map(async staffId => {
      try { const page = await createStaffDirectoryClient().queryPage({ staffId }, { signal: controller.signal }); const person = page.items.find(item => item.id === staffId); return [staffId, person ? staffDisplayLabel(person.union_no, person.name ?? '姓名未設定') : '月嫂資料待確認'] as const; }
      catch { return [staffId, '月嫂資料待確認'] as const; }
    })).then(entries => { if (!controller.signal.aborted) setNames(Object.fromEntries(entries)); });
    return () => controller.abort();
  }, [state]);
  const mounted = useRef(false);
  const sequence = useRef(0);
  const currentCase = useRef(caseNo);
  currentCase.current = caseNo;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  const load = async (notify = false) => {
    const request = ++sequence.current;
    setState({ status: 'loading' });
    try {
      const [assignment, matchingPlan] = await Promise.all([
        ordersQueryClient.getAssignmentPlan(caseNo),
        waitingDepositLockClient.queryPlan(caseNo).catch((error: unknown) => {
          if (error instanceof ApiHttpError && error.status === 404) return null;
          throw error;
        }),
      ]);
      if (assignment.case_no !== caseNo) {
        throw new Error('正式指派回讀案件編號不一致。');
      }
      if (!mounted.current || currentCase.current !== caseNo || sequence.current !== request) return;
      setState({ status: 'ready', data: { assignment, matchingPlan } });
      if (notify && mounted.current) onObserved?.();
    } catch (error) {
      if (!mounted.current || currentCase.current !== caseNo || sequence.current !== request) return;
      setState({ status: 'error', message: errorMessage(error) });
    }
  };

  useEffect(() => {
    void load();
    return () => { sequence.current += 1; };
    // The workbench supplies a revision after committed owner changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseNo, revision]);

  const plan = state.status === 'ready' ? state.data.assignment : null;
  const matchingPlan = state.status === 'ready' ? state.data.matchingPlan : null;

  return (
    <section aria-label={`案件 ${caseNo} 正式指派與排班回讀`}>
      {(state.status === 'idle' || state.status === 'error') && <button
        type="button"
        className="order-v2-open-drawer"
        disabled={false}
        onClick={() => void load()}
      >
        重新讀取服務安排
      </button>}

      {!onEditStateChange && <button
        type="button"
        className="order-v2-open-drawer"
        aria-expanded={onOpenReplacement ? undefined : replacementOpen}
        onClick={() => onOpenReplacement ? onOpenReplacement() : setReplacementOpen((current) => !current)}
      >
        {replacementOpen ? '收合服務前更換月嫂' : '服務前更換月嫂'}
      </button>

      }
      {!onEditStateChange && !onOpenReplacement && replacementOpen && (
        <ServiceBeforeReplacementActions
          caseNo={caseNo}
          onCommitted={() => load(true)}
          onSubstitutionReferral={() => {
            window.location.hash = `#scheduling?tab=leave_sub&case_no=${encodeURIComponent(caseNo)}`;
          }}
        />
      )}

      {state.status === 'error' && <p role="alert">{state.message}</p>}

      {state.status === 'ready' && matchingPlan === null && !historicalArrangementPending && (
        <p role="status">{plan && plan.assignments.length > 0
          ? '尚無有效媒合方案；既有正式指派資料顯示於下方。'
          : '尚無有效媒合方案；請至「推薦確認」確認人選。既有正式指派資料仍顯示於下方。'}</p>
      )}

      {plan !== null && (plan.assignments.length > 0 || matchingPlan === null || historicalArrangementPending) && (
        <details className="service-arrangement-assignment-details"><summary>查看目前月嫂與排班明細</summary>
          <dl className="order-v2-business-summary" aria-label="正式指派與排班摘要">
            <div><dt>正式指派</dt><dd>{plan.assignments.length > 0 ? `${plan.assignments.length} 段` : '尚未建立'}</dd></div>
            <div><dt>合約服務</dt><dd>{plan.contracted_service_days} 天 × {plan.service_hours_per_day} 小時</dd></div>
          </dl>

          {plan.assignments.length === 0 ? (
            <div className="order-v2-notice blocked" role="status">
              <strong>尚無正式指派</strong>
              <span>{historicalArrangementPending ? '請在上方沿用既定月嫂建立正式安排。' : '此案件尚未安排正式服務人員。'}</span>
            </div>
          ) : (
            plan.assignments.map((segment) => (
              <dl
                className="order-v2-business-summary"
                key={segment.assignment_id ?? segment.candidate_key ?? `${segment.staff_id}-${segment.sequence}`}
                aria-label={`第 ${segment.sequence} 段正式指派`}
              >
                <div><dt>月嫂</dt><dd>{names[segment.staff_id] ?? '月嫂資料待確認'}</dd></div>
                <div><dt>指派期間</dt><dd>{segment.assigned_start_date} ~ {segment.assigned_end_date}</dd></div>
                <div><dt>服務日</dt><dd>{segment.official_service_dates.length > 0 ? `${segment.official_service_dates.length} 天` : '尚未回傳'}</dd></div>
              </dl>
            ))
          )}
        </details>
      )}

      {plan !== null && matchingPlan !== null && !historicalArrangementPending && (matchingPlan.segments ?? []).length > 0 && (
        <MatchingScheduleAndAssignmentActions
          caseNo={caseNo}
          planId={matchingPlan.planId}
          planSegments={matchingPlan.segments ?? []}
          staffNames={names}
          onEditStateChange={onEditStateChange}
          contractReady={contractReady} depositReady={depositReady} onOpenDates={onOpenDates} onOpenRecommendation={onOpenRecommendation}
          waitingLockAcquired={matchingPlan.activeLockId !== null}
          assignmentExists={plan.assignments.length > 0}
          officialServiceDates={plan.assignments.flatMap(segment => segment.official_service_dates).sort()}
          onAssignmentCompleted={() => load(true)}
        />
      )}
    </section>
  );
};

export default OrderAssignmentPlanPanel;
