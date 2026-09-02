import { useEffect, useRef, useState, type FC } from 'react';
import './OrderWorkbenchV2Drawer.css';
import {
  historicalServiceAccountingClient,
  type HistoricalServiceAccountingQuery,
} from '../api/orders/historical_service_accounting_client';
import { orderCoreStageProjectionClient } from '../api/orders/order_core_stage_projection_client';
import type {
  CoreStageBranchType,
  OrderCoreStageTimeline,
} from '../api/orders/order_core_stage_projection_schemas';
import {
  ordersQueryClient,
} from '../api/orders/order_query_client';
import type {
  AssignmentPlan,
  OrderDetail,
  OrderTerms,
} from '../api/orders/order_query_schemas';
import { coreStageSubstatusLabel } from '../adapters/orders/order_core_stage_projection_adapter';

interface OrderWorkbenchV2DrawerProps {
  caseNo: string;
  branchType: CoreStageBranchType;
  onClose: () => void;
}

type ReadState<T> =
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string }
  | { status: 'skipped' };

const loading = <T,>(): ReadState<T> => ({ status: 'loading' });

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message.trim();
  return '正式唯讀資料查詢失敗';
}

function lineageIdentity(identity: string | null): string {
  return identity ?? '無 identity';
}

function timelineForCase(
  page: Awaited<ReturnType<typeof orderCoreStageProjectionClient.getCoreStageTimelines>>,
  caseNo: string,
): OrderCoreStageTimeline {
  const exact = page.items.filter((item) => item.case_no === caseNo);
  if (exact.length !== 1) {
    throw new Error(`正式十三階段查詢未唯一命中案件 ${caseNo}`);
  }
  return exact[0]!;
}

export const OrderWorkbenchV2Drawer: FC<OrderWorkbenchV2DrawerProps> = ({
  caseNo,
  branchType,
  onClose,
}) => {
  const requestSequence = useRef(0);
  const [timeline, setTimeline] = useState<ReadState<OrderCoreStageTimeline>>(loading);
  const [detail, setDetail] = useState<ReadState<OrderDetail>>(loading);
  const [terms, setTerms] = useState<ReadState<OrderTerms>>(loading);
  const [assignmentPlan, setAssignmentPlan] = useState<ReadState<AssignmentPlan>>(loading);
  const [historicalEvidence, setHistoricalEvidence] = useState<ReadState<HistoricalServiceAccountingQuery>>(
    () => branchType === 'historical' ? loading<HistoricalServiceAccountingQuery>() : { status: 'skipped' },
  );

  useEffect(() => {
    const requestId = requestSequence.current + 1;
    requestSequence.current = requestId;
    const controller = new AbortController();
    const current = () => !controller.signal.aborted && requestSequence.current === requestId;

    setTimeline(loading());
    setDetail(loading());
    setTerms(loading());
    setAssignmentPlan(loading());
    setHistoricalEvidence(branchType === 'historical' ? loading() : { status: 'skipped' });

    void orderCoreStageProjectionClient.getCoreStageTimelines({
      page_size: 20,
      lifecycle_scope: 'all',
      branch_type: branchType,
      case_no_search: caseNo,
    }, { signal: controller.signal })
      .then((page) => {
        if (current()) setTimeline({ status: 'ready', data: timelineForCase(page, caseNo) });
      })
      .catch((error) => {
        if (current()) setTimeline({ status: 'error', message: errorMessage(error) });
      });

    void ordersQueryClient.getOrderDetail(caseNo, { signal: controller.signal })
      .then((data) => {
        if (current()) setDetail({ status: 'ready', data });
      })
      .catch((error) => {
        if (current()) setDetail({ status: 'error', message: errorMessage(error) });
      });

    void ordersQueryClient.getOrderTerms(caseNo, { signal: controller.signal })
      .then((data) => {
        if (current()) setTerms({ status: 'ready', data });
      })
      .catch((error) => {
        if (current()) setTerms({ status: 'error', message: errorMessage(error) });
      });

    void ordersQueryClient.getAssignmentPlan(caseNo, { signal: controller.signal })
      .then((data) => {
        if (current()) setAssignmentPlan({ status: 'ready', data });
      })
      .catch((error) => {
        if (current()) setAssignmentPlan({ status: 'error', message: errorMessage(error) });
      });

    if (branchType === 'historical') {
      void historicalServiceAccountingClient.query(caseNo)
        .then((data) => {
          if (current()) setHistoricalEvidence({ status: 'ready', data });
        })
        .catch((error) => {
          if (current()) setHistoricalEvidence({ status: 'error', message: errorMessage(error) });
        });
    }

    return () => {
      controller.abort();
      if (requestSequence.current === requestId) requestSequence.current += 1;
    };
  }, [branchType, caseNo]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const blockers = timeline.status === 'ready'
    ? timeline.data.core_stages.flatMap((stage) => stage.blockers.map((notice) => ({
      key: `${stage.code}:${notice.code}`,
      stage: stage.label,
      message: notice.message,
    })))
    : [];
  const warnings = timeline.status === 'ready'
    ? timeline.data.core_stages.flatMap((stage) => stage.warnings.map((notice) => ({
      key: `${stage.code}:${notice.code}`,
      stage: stage.label,
      message: notice.message,
    })))
    : [];

  return (
    <div
      className="order-v2-drawer-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside
        className="order-v2-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="order-v2-drawer-title"
      >
        <header className="order-v2-drawer-header">
          <div>
            <div className="order-v2-eyebrow">唯讀工作 Drawer</div>
            <h2 id="order-v2-drawer-title">案件 {caseNo}</h2>
            <p>正式目前 owner facts 與歷史來源證據分開呈現；此 Drawer 不提供任何寫入操作。</p>
          </div>
          <button type="button" onClick={onClose} aria-label="關閉工作 Drawer">關閉</button>
        </header>

        <div className="order-v2-drawer-body">
          <section className="order-v2-drawer-section" aria-labelledby="order-v2-current-facts">
            <h3 id="order-v2-current-facts">正式目前 owner facts</h3>

            <div className="order-v2-drawer-fact-grid">
              <article>
                <h4>案件／客戶</h4>
                {detail.status === 'loading' && <p>載入正式案件資料…</p>}
                {detail.status === 'error' && <p className="order-v2-drawer-error">案件資料不可用：{detail.message}</p>}
                {detail.status === 'ready' && (
                  <dl>
                    <div><dt>客戶</dt><dd>{detail.data.client_name || '未登錄'}</dd></div>
                    <div><dt>客戶 ID</dt><dd>{detail.data.client_id}</dd></div>
                    <div><dt>訂單狀態</dt><dd>{detail.data.order_status}</dd></div>
                    <div><dt>身分類別</dt><dd>{detail.data.identity_status ?? '未登錄'}</dd></div>
                    <div><dt>實際開始</dt><dd>{detail.data.actual_start_date ?? '尚無 actual start'}</dd></div>
                  </dl>
                )}
              </article>

              <article aria-label="正式服務期間">
                <h4>正式服務條款</h4>
                {terms.status === 'loading' && <p>載入 Orders canonical planned period…</p>}
                {terms.status === 'error' && <p className="order-v2-drawer-error">正式服務條款不可用：{terms.message}</p>}
                {terms.status === 'ready' && (
                  <dl>
                    <div><dt>計畫開始</dt><dd>{terms.data.terms.planned_start_date}</dd></div>
                    <div><dt>合約服務</dt><dd>{terms.data.terms.service_days} 日</dd></div>
                    <div><dt>每日時數</dt><dd>{terms.data.terms.service_hours_per_day} 小時</dd></div>
                    <div><dt>Order version</dt><dd>{terms.data.order_version}</dd></div>
                    <div><dt>Scheduling version</dt><dd>{terms.data.scheduling_version}</dd></div>
                  </dl>
                )}
                <p className="order-v2-drawer-note">`actual_start_date` 僅代表實際開始，不作為完整服務區間。</p>
              </article>
            </div>
          </section>

          <section className="order-v2-drawer-section" aria-labelledby="order-v2-assignment-heading">
            <h3 id="order-v2-assignment-heading">目前正式派案／Assignment projection</h3>
            {assignmentPlan.status === 'loading' && <p>載入正式派案…</p>}
            {assignmentPlan.status === 'error' && (
              <p className="order-v2-drawer-error">正式派案不可用：{assignmentPlan.message}</p>
            )}
            {assignmentPlan.status === 'ready' && assignmentPlan.data.assignments.length === 0 && (
              <p>目前沒有正式 assignment segment。</p>
            )}
            {assignmentPlan.status === 'ready' && assignmentPlan.data.assignments.length > 0 && (
              <div className="order-v2-drawer-assignments">
                {assignmentPlan.data.assignments.map((segment) => (
                  <article key={`${segment.sequence}:${segment.staff_id}`}>
                    <strong>Segment {segment.sequence} · 月嫂 #{segment.staff_id}</strong>
                    <span>{segment.assigned_start_date} → {segment.assigned_end_date}</span>
                    <span>正式服務日：{segment.official_service_dates.length} 日</span>
                    <span>assignment_id：{segment.assignment_id ?? '無'}</span>
                    <span>lineage_source_assignment_ids：{segment.lineage_source_assignment_ids.join(', ') || '無'}</span>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="order-v2-drawer-section" aria-labelledby="order-v2-progress-heading">
            <h3 id="order-v2-progress-heading">13 階段正式進度</h3>
            {timeline.status === 'loading' && <p>載入正式十三階段 projection…</p>}
            {timeline.status === 'error' && <p className="order-v2-drawer-error">十三階段 projection 不可用：{timeline.message}</p>}
            {timeline.status === 'ready' && (
              <ol className="order-v2-drawer-stages">
                {timeline.data.core_stages.map((stage) => (
                  <li key={stage.code} data-testid="drawer-core-stage">
                    <span className={`order-v2-drawer-stage-status status-${stage.status}`}>{stage.ordinal}</span>
                    <div>
                      <strong>{stage.label}</strong>
                      <span>{coreStageSubstatusLabel(stage.substatus_code)}</span>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section className="order-v2-drawer-section" aria-labelledby="order-v2-notices-heading">
            <h3 id="order-v2-notices-heading">阻塞與提醒</h3>
            {timeline.status === 'ready' && blockers.length === 0 && warnings.length === 0 && <p>目前沒有正式 blocker / warning。</p>}
            {blockers.map((notice) => (
              <div className="order-v2-notice blocked" key={notice.key}>
                <strong>阻塞 · {notice.stage}</strong><span>{notice.message}</span>
              </div>
            ))}
            {warnings.map((notice) => (
              <div className="order-v2-notice warning" key={notice.key}>
                <strong>提醒 · {notice.stage}</strong><span>{notice.message}</span>
              </div>
            ))}
          </section>

          <section className="order-v2-drawer-section" aria-labelledby="order-v2-lineage-heading">
            <h3 id="order-v2-lineage-heading">Lineage／來源</h3>
            {timeline.status === 'ready' && (
              <>
                <p className="order-v2-technical">source_projection_digest：{timeline.data.source_projection_digest}</p>
                <div className="order-v2-drawer-lineage">
                  {timeline.data.core_stages.map((stage) => (
                    <div key={stage.code}>
                      <strong>{stage.ordinal}. {stage.label}</strong>
                      <span>owner：{stage.source.owner}</span>
                      <span>identity：{lineageIdentity(stage.source.identity)}</span>
                      <span>version：{stage.source.version ?? '無'}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </section>

          {branchType === 'historical' && (
            <section
              className="order-v2-drawer-section historical-evidence"
              aria-labelledby="order-v2-history-heading"
              aria-label="歷史來源證據"
            >
              <h3 id="order-v2-history-heading">歷史來源證據</h3>
              <p className="order-v2-drawer-note">以下為歷史匯入／帳務 read model 證據，不代表目前正式服務期間或目前正式派案。</p>
              {historicalEvidence.status === 'loading' && <p>載入歷史來源證據…</p>}
              {historicalEvidence.status === 'error' && (
                <p className="order-v2-drawer-error">歷史來源證據不可用：{historicalEvidence.message}</p>
              )}
              {historicalEvidence.status === 'ready' && (
                <dl>
                  <div><dt>來源 identity</dt><dd>{historicalEvidence.data.adoption_source_identity}</dd></div>
                  <div><dt>歷史合約服務天數</dt><dd>{historicalEvidence.data.contracted_service_days} 日</dd></div>
                  <div><dt>歷史配對月嫂</dt><dd>{historicalEvidence.data.assignments.map((item) => `${item.staff_name} (#${item.staff_id}, ${item.assignment_identity})`).join('；')}</dd></div>
                </dl>
              )}
            </section>
          )}
        </div>
      </aside>
    </div>
  );
};

export default OrderWorkbenchV2Drawer;
