import { useState, type FC } from 'react';
import type { AssignmentPlan } from '../api/orders/order_query_schemas';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { ServiceBeforeReplacementActions } from './ServiceBeforeReplacementActions';

interface OrderAssignmentPlanPanelProps {
  caseNo: string;
}

type ReadState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: AssignmentPlan }
  | { status: 'error'; message: string };

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '正式指派與排班資料讀取失敗';
}

export const OrderAssignmentPlanPanel: FC<OrderAssignmentPlanPanelProps> = ({ caseNo }) => {
  const [state, setState] = useState<ReadState>({ status: 'idle' });
  const [replacementOpen, setReplacementOpen] = useState(false);

  const load = async () => {
    setState({ status: 'loading' });
    try {
      const data = await ordersQueryClient.getAssignmentPlan(caseNo);
      if (data.case_no !== caseNo) {
        throw new Error('正式指派回讀案件編號不一致。');
      }
      setState({ status: 'ready', data });
    } catch (error) {
      setState({ status: 'error', message: errorMessage(error) });
    }
  };

  const plan = state.status === 'ready' ? state.data : null;

  return (
    <section aria-label={`案件 ${caseNo} 正式指派與排班回讀`}>
      <button
        type="button"
        className="order-v2-open-drawer"
        disabled={state.status === 'loading'}
        onClick={() => void load()}
      >
        {state.status === 'loading' ? '讀取正式指派與排班中…' : '讀取正式指派與排班'}
      </button>

      <button
        type="button"
        className="order-v2-open-drawer"
        aria-expanded={replacementOpen}
        onClick={() => setReplacementOpen((current) => !current)}
      >
        {replacementOpen ? '收合服務前更換月嫂' : '服務前更換月嫂'}
      </button>

      {replacementOpen && (
        <ServiceBeforeReplacementActions
          caseNo={caseNo}
          onCommitted={() => load()}
          onSubstitutionReferral={() => {
            window.location.hash = `#scheduling?tab=leave_sub&case_no=${encodeURIComponent(caseNo)}`;
          }}
        />
      )}

      {state.status === 'error' && <p role="alert">{state.message}</p>}

      {plan !== null && (
        <>
          <dl className="order-v2-business-summary" aria-label="正式指派與排班摘要">
            <div><dt>正式指派</dt><dd>{plan.assignments.length > 0 ? `${plan.assignments.length} 段` : '尚未建立'}</dd></div>
            <div><dt>排班版本</dt><dd>#{plan.scheduling_version}</dd></div>
            <div><dt>排班世代</dt><dd>#{plan.scheduling_generation}</dd></div>
            <div><dt>合約服務</dt><dd>{plan.contracted_service_days} 天 × {plan.service_hours_per_day} 小時</dd></div>
          </dl>

          {plan.assignments.length === 0 ? (
            <div className="order-v2-notice blocked" role="status">
              <strong>尚無正式指派</strong>
              <span>Assignment Plan owner 目前未回傳任何正式指派段。</span>
            </div>
          ) : (
            plan.assignments.map((segment) => (
              <dl
                className="order-v2-business-summary"
                key={segment.assignment_id ?? segment.candidate_key ?? `${segment.staff_id}-${segment.sequence}`}
                aria-label={`第 ${segment.sequence} 段正式指派`}
              >
                <div><dt>月嫂</dt><dd>#{segment.staff_id}</dd></div>
                <div><dt>指派期間</dt><dd>{segment.assigned_start_date} ~ {segment.assigned_end_date}</dd></div>
                <div><dt>正式服務日</dt><dd>{segment.official_service_dates.length > 0 ? segment.official_service_dates.join('、') : '尚未回傳'}</dd></div>
              </dl>
            ))
          )}
        </>
      )}
    </section>
  );
};

export default OrderAssignmentPlanPanel;
