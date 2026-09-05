import { useEffect, useRef, useState, type FC } from 'react';
import './OrderWorkbenchV2Drawer.css';
import { historicalAdoptionEvidenceClient } from '../api/orders/historical_adoption_evidence_client';
import type { HistoricalOrderAdoptionEvidence } from '../api/orders/historical_adoption_evidence_schemas';
import {
  historicalServiceAccountingClient,
  type HistoricalServiceAccountingQuery,
} from '../api/orders/historical_service_accounting_client';
import { historicalOperationalBaselineClient } from '../api/orders/historical_operational_baseline_client';
import type { HistoricalOperationalBaseline } from '../api/orders/historical_operational_baseline_schemas';
import { orderCoreStageProjectionClient } from '../api/orders/order_core_stage_projection_client';
import type {
  CoreStageBranchType,
  CoreStageProjection,
  OrderCoreStageTimeline,
} from '../api/orders/order_core_stage_projection_schemas';
import { ordersQueryClient } from '../api/orders/order_query_client';
import type { AssignmentPlan, OrderDetail, OrderTerms } from '../api/orders/order_query_schemas';
import { coreStageSubstatusLabel } from '../adapters/orders/order_core_stage_projection_adapter';
import { OrderIntakeRepairPanel } from './OrderIntakeRepairPanel';
import { OrderServiceCompletionActions } from './OrderServiceCompletionActions';
import { OrderTermsMutationPanel } from './OrderTermsMutationPanel';
import { ServiceBeforeReplacementActions } from './ServiceBeforeReplacementActions';

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

type HistoricalRestartState =
  | { status: 'idle'; message: null }
  | { status: 'applying'; message: null }
  | { status: 'completed'; message: string }
  | { status: 'error'; message: string };

const loading = <T,>(): ReadState<T> => ({ status: 'loading' });

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '正式唯讀資料查詢失敗';
}

function timelineForCase(
  page: Awaited<ReturnType<typeof orderCoreStageProjectionClient.getCoreStageTimelines>>,
  caseNo: string,
): OrderCoreStageTimeline {
  const exact = page.items.filter((item) => item.case_no === caseNo);
  if (exact.length !== 1) throw new Error(`正式十三階段查詢未唯一命中案件 ${caseNo}`);
  return exact[0]!;
}

function historicalCurrentOwnerStage(timeline: OrderCoreStageTimeline): CoreStageProjection | null {
  const code = timeline.historical_current_owner_stage_code ?? null;
  if (code === null) return null;
  const stage = timeline.core_stages.find((item) => item.code === code);
  if (!stage) throw new Error('historical current owner stage 不存在於正式十三階段投影。');
  if (stage.source.owner === 'Historical Orders') {
    throw new Error('immutable historical baseline 不得冒充目前正式 owner stage。');
  }
  return stage;
}

function evidencePeriod(evidence: HistoricalOrderAdoptionEvidence): string {
  if (evidence.source_period_availability === 'unavailable') return '來源服務期間未保留';
  return `${evidence.source_start_date ?? '開始日未保留'} → ${evidence.source_end_date ?? '結束日未保留'}`;
}

function baselineSkippedSteps(baseline: HistoricalOperationalBaseline): readonly number[] {
  const selected = baseline.current_baseline?.selected_step ?? null;
  return selected === null
    ? []
    : Array.from({ length: Math.max(0, selected - 1) }, (_, index) => index + 1);
}

function lineageIdentity(identity: string | null): string {
  return identity ?? '無 identity';
}

export const OrderWorkbenchV2Drawer: FC<OrderWorkbenchV2DrawerProps> = ({
  caseNo,
  branchType,
  onClose,
}) => {
  const requestSequence = useRef(0);
  const [refreshRevision, setRefreshRevision] = useState(0);
  const [timeline, setTimeline] = useState<ReadState<OrderCoreStageTimeline>>(loading);
  const [detail, setDetail] = useState<ReadState<OrderDetail>>(loading);
  const [terms, setTerms] = useState<ReadState<OrderTerms>>(loading);
  const [assignmentPlan, setAssignmentPlan] = useState<ReadState<AssignmentPlan>>(loading);
  const [historicalEvidence, setHistoricalEvidence] = useState<ReadState<HistoricalOrderAdoptionEvidence>>(
    () => branchType === 'historical' ? loading<HistoricalOrderAdoptionEvidence>() : { status: 'skipped' },
  );
  const [historicalAccounting, setHistoricalAccounting] = useState<ReadState<HistoricalServiceAccountingQuery>>(
    () => branchType === 'historical' ? loading<HistoricalServiceAccountingQuery>() : { status: 'skipped' },
  );
  const [historicalBaseline, setHistoricalBaseline] = useState<ReadState<HistoricalOperationalBaseline>>(
    () => branchType === 'historical' ? loading<HistoricalOperationalBaseline>() : { status: 'skipped' },
  );
  const [historicalRestart, setHistoricalRestart] = useState<HistoricalRestartState>({ status: 'idle', message: null });
  const [replacementExpanded, setReplacementExpanded] = useState(false);

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
    setHistoricalAccounting(branchType === 'historical' ? loading() : { status: 'skipped' });
    setHistoricalBaseline(branchType === 'historical' ? loading() : { status: 'skipped' });
    setHistoricalRestart({ status: 'idle', message: null });
    setReplacementExpanded(false);

    void orderCoreStageProjectionClient.getCoreStageTimelines({
      page_size: 20,
      lifecycle_scope: 'all',
      branch_type: branchType,
      case_no_search: caseNo,
    }, { signal: controller.signal })
      .then((page) => { if (current()) setTimeline({ status: 'ready', data: timelineForCase(page, caseNo) }); })
      .catch((error) => { if (current()) setTimeline({ status: 'error', message: errorMessage(error) }); });

    void ordersQueryClient.getOrderDetail(caseNo, { signal: controller.signal })
      .then((data) => { if (current()) setDetail({ status: 'ready', data }); })
      .catch((error) => { if (current()) setDetail({ status: 'error', message: errorMessage(error) }); });

    void ordersQueryClient.getOrderTerms(caseNo, { signal: controller.signal })
      .then((data) => { if (current()) setTerms({ status: 'ready', data }); })
      .catch((error) => { if (current()) setTerms({ status: 'error', message: errorMessage(error) }); });

    void ordersQueryClient.getAssignmentPlan(caseNo, { signal: controller.signal })
      .then((data) => { if (current()) setAssignmentPlan({ status: 'ready', data }); })
      .catch((error) => { if (current()) setAssignmentPlan({ status: 'error', message: errorMessage(error) }); });

    if (branchType === 'historical') {
      void historicalServiceAccountingClient.query(caseNo)
        .then((data) => { if (current()) setHistoricalAccounting({ status: 'ready', data }); })
        .catch((error) => { if (current()) setHistoricalAccounting({ status: 'error', message: errorMessage(error) }); });
      void historicalAdoptionEvidenceClient.queryByCase(caseNo, { signal: controller.signal })
        .then((data) => { if (current()) setHistoricalEvidence({ status: 'ready', data }); })
        .catch((error) => { if (current()) setHistoricalEvidence({ status: 'error', message: errorMessage(error) }); });
      void historicalOperationalBaselineClient.queryByCase(caseNo, { signal: controller.signal })
        .then((data) => { if (current()) setHistoricalBaseline({ status: 'ready', data }); })
        .catch((error) => { if (current()) setHistoricalBaseline({ status: 'error', message: errorMessage(error) }); });
    }

    return () => {
      controller.abort();
      if (requestSequence.current === requestId) requestSequence.current += 1;
    };
  }, [branchType, caseNo, refreshRevision]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const restartHistoricalOrderIntoNormalFlow = async () => {
    if (branchType !== 'historical' || historicalRestart.status === 'applying') return;
    setHistoricalRestart({ status: 'applying', message: null });
    try {
      const query = await historicalServiceAccountingClient.queryPrecisionRestart(caseNo);
      if (query.blockers.length > 0) {
        throw new Error(`目前不可重啟正常流程：${query.blockers.join('、')}`);
      }
      const preview = await historicalServiceAccountingClient.previewPrecisionRestart(caseNo);
      const receipt = await historicalServiceAccountingClient.applyPrecisionRestart(
        preview,
        '工會人員從待辦看板 Beta 工作 Drawer 選擇重啟正常流程',
      );
      if (receipt.lifecycle_status !== '訂單成立') {
        throw new Error('重啟後狀態不是正常「訂單成立」，已停止後續操作。');
      }
      const observed = await ordersQueryClient.getOrderDetail(caseNo);
      if (observed.order_status !== '訂單成立') {
        throw new Error('重啟收據已回傳，但正式案件回讀尚未觀察到「訂單成立」。');
      }
      setDetail({ status: 'ready', data: observed });
      setHistoricalRestart({
        status: 'completed',
        message: receipt.replayed
          ? '此案件先前已重啟正常流程；正式回讀已確認為「訂單成立」。請關閉 Drawer 後從正常訂單支線繼續。'
          : '已重啟正常流程並回讀確認為「訂單成立」。請關閉 Drawer 後從正常訂單支線繼續日期／媒合／排班。',
      });
    } catch (error) {
      setHistoricalRestart({ status: 'error', message: errorMessage(error) });
    }
  };

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
  const currentHistoricalOwner = timeline.status === 'ready' && branchType === 'historical'
    ? historicalCurrentOwnerStage(timeline.data)
    : null;

  return (
    <div
      className="order-v2-drawer-backdrop"
      role="presentation"
      onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
    >
      <aside className="order-v2-drawer" role="dialog" aria-modal="true" aria-labelledby="order-v2-drawer-title">
        <header className="order-v2-drawer-header">
          <div>
            <div className="order-v2-eyebrow">工作 Drawer</div>
            <h2 id="order-v2-drawer-title">案件 {caseNo}</h2>
            <p>正式 owner facts、immutable historical baseline 與歷史來源 evidence 分開呈現；缺件與 owner mutation 只使用既有正式流程。</p>
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
                <p className="order-v2-drawer-note">historical source period 是來源 evidence，不用來推導目前 lifecycle。</p>
              </article>
            </div>
          </section>

          {branchType !== 'cancelled' && detail.status === 'ready'
            && (branchType === 'historical'
              || detail.data.order_status === '待補件'
              || (timeline.status === 'ready' && timeline.data.current_core_stage_code === 'intake_validation')) && (
            <OrderIntakeRepairPanel
              caseNo={caseNo}
              orderStatus={detail.data.order_status}
              onChanged={() => setRefreshRevision((revision) => revision + 1)}
              onHistoricalRestartRequested={restartHistoricalOrderIntoNormalFlow}
            />
          )}

          {historicalRestart.status === 'applying' && (
            <div role="status" className="order-v2-drawer-note">正在依正式 Historical Orders Query／Preview／Apply 重啟正常流程…</div>
          )}
          {(historicalRestart.status === 'completed' || historicalRestart.status === 'error') && historicalRestart.message && (
            <div
              role={historicalRestart.status === 'error' ? 'alert' : 'status'}
              className={historicalRestart.status === 'error' ? 'order-v2-drawer-error' : 'order-v2-drawer-note'}
            >
              {historicalRestart.message}
            </div>
          )}

          {branchType === 'normal'
            && timeline.status === 'ready'
            && timeline.data.current_core_stage_code === 'intake_validation'
            && terms.status === 'ready' && (
            <OrderTermsMutationPanel caseNo={caseNo} query={terms.data} />
          )}

          {branchType === 'normal' && detail.status === 'ready' && (
            <section className="order-v2-drawer-section" data-surface-id="orders.service-before-replacement.entry">
              <h3>服務前更換月嫂</h3>
              {!replacementExpanded ? (
                <button
                  type="button"
                  className="btn-secondary-action"
                  data-control-id="orders.service-before-replacement.open"
                  onClick={() => setReplacementExpanded(true)}
                >
                  服務前更換月嫂
                </button>
              ) : (
                <ServiceBeforeReplacementActions
                  caseNo={caseNo}
                  onCommitted={() => setRefreshRevision((revision) => revision + 1)}
                  onSubstitutionReferral={() => {
                    window.location.hash = `#scheduling?tab=leave_sub&case_no=${encodeURIComponent(caseNo)}`;
                  }}
                />
              )}
            </section>
          )}

          <section className="order-v2-drawer-section" aria-labelledby="order-v2-assignment-heading">
            <h3 id="order-v2-assignment-heading">目前正式派案／Assignment projection</h3>
            {assignmentPlan.status === 'loading' && <p>載入正式派案…</p>}
            {assignmentPlan.status === 'error' && <p className="order-v2-drawer-error">正式派案不可用：{assignmentPlan.message}</p>}
            {assignmentPlan.status === 'ready' && assignmentPlan.data.assignments.length === 0 && (
              <p>尚無正式指派。歷史匯入配對證據（若有）顯示於下方歷史來源證據，不等同 Scheduling assignment。</p>
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

          {branchType === 'normal' && detail.status === 'ready' && (
            <OrderServiceCompletionActions
              caseNo={caseNo}
              orderStatus={detail.data.order_status}
              onCompleted={() => setRefreshRevision((revision) => revision + 1)}
            />
          )}

          {branchType === 'historical' && (
            <section className="order-v2-drawer-section" aria-labelledby="order-v2-historical-owner-heading">
              <h3 id="order-v2-historical-owner-heading">目前正式 owner progression</h3>
              {timeline.status === 'loading' && <p>載入正式 owner progression…</p>}
              {timeline.status === 'error' && <p className="order-v2-drawer-error">owner progression 不可用：{timeline.message}</p>}
              {timeline.status === 'ready' && currentHistoricalOwner === null && <p>目前沒有尚待處理的正式 owner stage。</p>}
              {currentHistoricalOwner !== null && (
                <div>
                  <strong>{currentHistoricalOwner.ordinal}. {currentHistoricalOwner.label}</strong>
                  <p>{coreStageSubstatusLabel(currentHistoricalOwner.substatus_code)}</p>
                  <p className="order-v2-technical">
                    owner：{currentHistoricalOwner.source.owner} · identity：{lineageIdentity(currentHistoricalOwner.source.identity)}
                  </p>
                  {currentHistoricalOwner.availability_reason && (
                    <p className="order-v2-drawer-note">availability：{currentHistoricalOwner.availability_reason}</p>
                  )}
                  {currentHistoricalOwner.available_read_actions.length > 0 && (
                    <div className="order-v2-drawer-actions" aria-label="正式唯讀入口">
                      {currentHistoricalOwner.available_read_actions.map((action) => (
                        <a key={action.action_id} href={action.path} target="_blank" rel="noreferrer">{action.action_id}</a>
                      ))}
                    </div>
                  )}
                </div>
              )}
              <p className="order-v2-drawer-note">只顯示 server 已提供的 GET action descriptor；正式 restart 只從上方既有 owner Q/P/A 入口執行。</p>
            </section>
          )}

          <section className="order-v2-drawer-section" aria-labelledby="order-v2-progress-heading">
            <h3 id="order-v2-progress-heading">13 階段正式進度</h3>
            {timeline.status === 'loading' && <p>載入正式十三階段 projection…</p>}
            {timeline.status === 'error' && <p className="order-v2-drawer-error">十三階段 projection 不可用：{timeline.message}</p>}
            {timeline.status === 'ready' && (
              <ol className="order-v2-drawer-stages">
                {timeline.data.core_stages.map((stage) => (
                  <li key={stage.code} data-testid="drawer-core-stage">
                    <span className={`order-v2-drawer-stage-status status-${stage.status}`}>{stage.ordinal}</span>
                    <div><strong>{stage.label}</strong><span>{coreStageSubstatusLabel(stage.substatus_code)}</span></div>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section className="order-v2-drawer-section" aria-labelledby="order-v2-notices-heading">
            <h3 id="order-v2-notices-heading">阻塞與提醒</h3>
            {timeline.status === 'ready' && blockers.length === 0 && warnings.length === 0 && <p>目前沒有正式 blocker / warning。</p>}
            {blockers.map((notice) => (
              <div className="order-v2-notice blocked" key={notice.key}><strong>阻塞 · {notice.stage}</strong><span>{notice.message}</span></div>
            ))}
            {warnings.map((notice) => (
              <div className="order-v2-notice warning" key={notice.key}><strong>提醒 · {notice.stage}</strong><span>{notice.message}</span></div>
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
            <section className="order-v2-drawer-section historical-evidence" aria-label="歷史來源證據">
              <h3 id="order-v2-history-baseline-heading">Immutable historical baseline</h3>
              <p className="order-v2-drawer-note">baseline 只表示已接受略過的前置步驟，不是真實 owner event，也不覆寫後續正式 owner facts。</p>
              {historicalBaseline.status === 'loading' && <p>載入 immutable baseline…</p>}
              {historicalBaseline.status === 'error' && <p className="order-v2-drawer-error">baseline read model 不可用：{historicalBaseline.message}</p>}
              {historicalBaseline.status === 'ready' && historicalBaseline.data.current_baseline === null && (
                <p>目前沒有獨立 historical operational baseline event；採納 receipt lineage 仍顯示於下方。</p>
              )}
              {historicalBaseline.status === 'ready' && historicalBaseline.data.current_baseline !== null && (
                <dl>
                  <div><dt>Baseline identity</dt><dd>{historicalBaseline.data.current_baseline.baseline_event_identity}</dd></div>
                  <div><dt>Selected step</dt><dd>{historicalBaseline.data.current_baseline.selected_step}</dd></div>
                  <div><dt>略過前置步驟</dt><dd>{baselineSkippedSteps(historicalBaseline.data).join(', ') || '無'}</dd></div>
                </dl>
              )}

              <h3>歷史來源證據</h3>
              <p className="order-v2-drawer-note">以下為歷史匯入／帳務 read model 證據，不代表目前正式服務期間或目前正式派案。source period 不等於已發生 actual period，pairing evidence 不等於 formal Scheduling assignment。</p>
              {historicalAccounting.status === 'error' && (
                <p className="order-v2-drawer-error">歷史帳務 Query／blocker：{historicalAccounting.message}</p>
              )}
              {historicalAccounting.status === 'ready' && (
                <dl aria-label="既有 historical accounting read model">
                  <div><dt>來源 identity</dt><dd>{historicalAccounting.data.adoption_source_identity}</dd></div>
                  <div><dt>歷史合約服務天數</dt><dd>{historicalAccounting.data.contracted_service_days} 日</dd></div>
                  <div><dt>歷史配對月嫂</dt><dd>{historicalAccounting.data.assignments.map((item) => `${item.staff_name} (#${item.staff_id}, ${item.assignment_identity})`).join('；')}</dd></div>
                </dl>
              )}
              {historicalEvidence.status === 'loading' && <p>載入 historical adoption evidence…</p>}
              {historicalEvidence.status === 'error' && <p className="order-v2-drawer-error">historical adoption evidence 不可用：{historicalEvidence.message}</p>}
              {historicalEvidence.status === 'ready' && (
                <>
                  <dl>
                    <div><dt>Receipt</dt><dd>{historicalEvidence.data.receipt_identity}</dd></div>
                    <div><dt>來源 identity</dt><dd>{historicalEvidence.data.source_identity}</dd></div>
                    <div><dt>Evidence owner</dt><dd>{historicalEvidence.data.evidence_owner}</dd></div>
                    <div><dt>歷史匯入服務日期</dt><dd>{evidencePeriod(historicalEvidence.data)}</dd></div>
                    <div><dt>期間 availability</dt><dd>{historicalEvidence.data.source_period_availability}</dd></div>
                  </dl>
                  {historicalEvidence.data.paired_staff.length === 0 ? (
                    <p>歷史匯入未保留可唯一解析的配對月嫂 evidence。</p>
                  ) : (
                    <div className="order-v2-drawer-assignments" aria-label="歷史匯入配對月嫂">
                      {historicalEvidence.data.paired_staff.map((item) => (
                        <article key={`${item.caregiver_ordinal}:${item.staff_id}`}>
                          <strong>歷史匯入配對月嫂 · #{item.staff_id}</strong>
                          <span>月嫂名稱：{item.staff_name}</span>
                          <span>resolution：{item.resolution}</span>
                          <span>來源服務：{item.source_start_date ?? '未保留'} → {item.source_end_date ?? '未保留'}</span>
                          <span>historical assignment_id：{item.assignment_id ?? '無（evidence-only）'}</span>
                        </article>
                      ))}
                    </div>
                  )}
                </>
              )}
            </section>
          )}
        </div>
      </aside>
    </div>
  );
};

export default OrderWorkbenchV2Drawer;