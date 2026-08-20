/**
 * File: OrderTrackerPage.tsx
 * Description: 顯示待階段投影的訂單摘要，並誠實保留七階、SOP、LINE與三個結清 unavailable 槽位。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { adaptOrderTrackerPage, type OrderTrackerPageViewModel, type TrackerOrderCardViewModel } from '../adapters/orders/order_tracker_adapter';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { Drawer } from '../components/Drawer';
import './OrderTrackerPage.css';

type TrackerQueryState =
  | { kind: 'loading' }
  | { kind: 'ready'; data: OrderTrackerPageViewModel }
  | { kind: 'empty'; data: OrderTrackerPageViewModel }
  | { kind: 'error'; message: string };

function controlSafeCaseNo(caseNo: string): string {
  return encodeURIComponent(caseNo);
}

export const OrderTrackerPage: React.FC = () => {
  const [queryState, setQueryState] = useState<TrackerQueryState>({ kind: 'loading' });
  const [selectedOrder, setSelectedOrder] = useState<TrackerOrderCardViewModel | null>(null);
  const [drawerTab, setDrawerTab] = useState<'sop' | 'notifications'>('sop');
  const generationRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const fetchTrackerData = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    setSelectedOrder(null);
    setQueryState({ kind: 'loading' });

    try {
      const page = await ordersQueryClient.getOrderSummaries({}, { signal: controller.signal });
      if (controller.signal.aborted || generation !== generationRef.current) return;
      const data = adaptOrderTrackerPage(page);
      setQueryState(data.loadedCount === 0 ? { kind: 'empty', data } : { kind: 'ready', data });
    } catch (error) {
      if (controller.signal.aborted || generation !== generationRef.current) return;
      setQueryState({
        kind: 'error',
        message: error instanceof Error ? error.message : '載入訂單摘要失敗',
      });
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void fetchTrackerData();
    });
    return () => {
      cancelled = true;
      abortRef.current?.abort();
      generationRef.current += 1;
    };
  }, [fetchTrackerData]);

  const resolvedData = queryState.kind === 'ready' || queryState.kind === 'empty'
    ? queryState.data
    : null;

  const scrollToStage = (stageId: string) => {
    document.getElementById(`order-tracker-stage-${stageId}`)?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    });
  };

  const openOrder = (order: TrackerOrderCardViewModel) => {
    setDrawerTab('sop');
    setSelectedOrder(order);
  };

  return (
    <div data-surface-id="order-tracker.page">
      <header className="tracker-page-header">
        <div>
          <h1 className="page-title">📊 訂單進度儀表板</h1>
          <p className="page-subtitle">
            七階段與作業歷程槽位完整保留；沒有 server lineage 的狀態會明確標示 unavailable。
          </p>
        </div>
        <button
          type="button"
          className="tracker-reload-button"
          data-control-id="order-tracker.query.retry"
          onClick={() => void fetchTrackerData()}
        >
          重新載入摘要
        </button>
      </header>

      {queryState.kind === 'loading' && (
        <div className="tracker-query-state" data-surface-id="order-tracker.query.loading" role="status">
          ⏳ 正在載入訂單摘要…
        </div>
      )}

      {queryState.kind === 'error' && (
        <div className="tracker-query-state tracker-query-error" data-surface-id="order-tracker.query.error" role="alert">
          <strong>載入訂單摘要失敗</strong>
          <span>{queryState.message}</span>
        </div>
      )}

      {resolvedData && (
        <>
          <nav className="pipeline-stepper-nav" aria-label="訂單七階段槽位">
            {resolvedData.stageSlots.map((slot) => (
              <button
                type="button"
                key={slot.id}
                className="pipeline-step-pill"
                data-control-id={`order-tracker.stage-nav.${slot.id}`}
                onClick={() => scrollToStage(slot.id)}
              >
                <span>{slot.title}</span>
                <span
                  className="pipeline-step-badge"
                  data-surface-id={`order-tracker.stage-count.${slot.id}`}
                  aria-label={`${slot.title}案件數尚未提供`}
                >
                  —
                </span>
              </button>
            ))}
          </nav>

          <section className="pipeline-vertical-container" aria-label="七階段服務流程">
            {resolvedData.stageSlots.map((slot) => (
              <article
                key={slot.id}
                id={`order-tracker-stage-${slot.id}`}
                className="pipeline-stage-section"
                data-surface-id={`order-tracker.stage-slot.${slot.id}`}
              >
                <div className="pipeline-stage-header">
                  <div className="pipeline-stage-title-wrap">
                    <h2 className="pipeline-stage-title">{slot.title}</h2>
                    <span className="pipeline-stage-desc">{slot.description}</span>
                  </div>
                  <span className="pipeline-stage-count" style={{ backgroundColor: slot.badgeColor, color: slot.textColor }}>
                    案件數 —
                  </span>
                </div>
                <div
                  className="tracker-unavailable-panel"
                  data-surface-id={`order-tracker.stage-unavailable.${slot.id}`}
                  role="status"
                >
                  <strong>階段案件分布尚未開放</strong>
                  <span>{slot.unavailableMessage}</span>
                </div>
              </article>
            ))}
          </section>

          <section className="tracker-unclassified" data-surface-id="order-tracker.unclassified-orders">
            <div className="tracker-section-heading">
              <div>
                <h2>待後端階段投影</h2>
                <p>以下為本次已載入的訂單摘要，不代表任何七階段歸屬。</p>
              </div>
              <span className="tracker-loaded-count">已載入 {resolvedData.loadedCount} 筆</span>
            </div>

            {queryState.kind === 'empty' ? (
              <div className="tracker-query-state" data-surface-id="order-tracker.query.empty">
                目前 loaded scope 沒有訂單摘要；七階段投影仍為 unavailable。
              </div>
            ) : (
              <div className="pipeline-cards-grid">
                {resolvedData.unclassifiedOrders.map((order) => (
                  <button
                    type="button"
                    key={order.id}
                    className="pipeline-order-card"
                    data-control-id={`order-tracker.card.${controlSafeCaseNo(order.id)}`}
                    onClick={() => openOrder(order)}
                    aria-label={`查看訂單 ${order.id} 的摘要與 unavailable 歷程槽位`}
                  >
                    <div className="card-top-row">
                      <span className="card-id-tag">{order.id}</span>
                      <span className="card-days-tag">{order.serviceDaysLabel}</span>
                    </div>
                    <div className="card-client-row">
                      <strong className="card-client-name">👤 {order.clientName}</strong>
                      <span className="card-amount-tag">{order.contractAmountFormatted}</span>
                    </div>
                    <dl className="tracker-card-facts">
                      <div><dt>原始訂單狀態（非七階段）</dt><dd>{order.rawOrderStatus}</dd></div>
                      <div><dt>約定服務日期</dt><dd>{order.plannedServiceRange}</dd></div>
                      <div><dt>實際服務日期</dt><dd>{order.actualServiceRange}</dd></div>
                      <div><dt>正式指派月嫂</dt><dd>{order.assignedStaffDisplay}</dd></div>
                    </dl>
                    <div className="card-waiting-alert">
                      <strong>目前卡點／待辦</strong>
                      <span>{order.waitingText}</span>
                    </div>
                    <span className="tracker-card-link">查看摘要與保留槽位 ➔</span>
                  </button>
                ))}
              </div>
            )}
          </section>
        </>
      )}

      <Drawer
        isOpen={selectedOrder !== null}
        onClose={() => setSelectedOrder(null)}
        size="wide"
        title={`📋 訂單作業歷程 - ${selectedOrder?.id ?? ''}`}
        footer={(
          <button
            type="button"
            className="tracker-close-button"
            data-control-id="order-tracker.drawer.close"
            onClick={() => setSelectedOrder(null)}
          >
            關閉
          </button>
        )}
      >
        {selectedOrder && (
          <div className="tracker-drawer" data-surface-id="order-tracker.drawer">
            <section className="tracker-summary-panel">
              <h3>{selectedOrder.clientName}</h3>
              <dl className="tracker-drawer-facts">
                <div><dt>案件編號</dt><dd>{selectedOrder.id}</dd></div>
                <div><dt>原始訂單狀態（非七階段）</dt><dd>{selectedOrder.rawOrderStatus}</dd></div>
                <div><dt>聯絡電話</dt><dd>{selectedOrder.clientPhoneText}</dd></div>
                <div><dt>服務地址</dt><dd>{selectedOrder.serviceAddressText}</dd></div>
                <div><dt>約定服務日期</dt><dd>{selectedOrder.plannedServiceRange}</dd></div>
                <div><dt>實際服務日期</dt><dd>{selectedOrder.actualServiceRange}</dd></div>
                <div><dt>正式指派月嫂</dt><dd>{selectedOrder.assignedStaffDisplay}</dd></div>
                <div><dt>契約應付金額</dt><dd>{selectedOrder.contractAmountFormatted}</dd></div>
              </dl>
            </section>

            <section className="tracker-settlement-grid" aria-label="三個獨立結清投影">
              {selectedOrder.settlementSlots.map((slot) => (
                <article key={slot.id} data-surface-id={`order-tracker.settlement.${slot.id}`}>
                  <span>{slot.owner}</span>
                  <h4>{slot.label}</h4>
                  <p>{slot.value}</p>
                </article>
              ))}
            </section>

            <div className="tracker-tabs" role="tablist" aria-label="訂單作業歷程內容">
              <button
                type="button"
                role="tab"
                aria-selected={drawerTab === 'sop'}
                data-control-id="order-tracker.drawer.tab.sop"
                onClick={() => setDrawerTab('sop')}
              >
                📋 11 步 SOP 檢核
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={drawerTab === 'notifications'}
                data-control-id="order-tracker.drawer.tab.notifications"
                onClick={() => setDrawerTab('notifications')}
              >
                🔔 LINE 通知紀錄與發送狀態
              </button>
            </div>

            {drawerTab === 'sop' ? (
              <section className="tracker-tab-panel" role="tabpanel" data-surface-id="order-tracker.sop.unavailable">
                <h3>工會因果鏈 11 步驟標準作業檢核</h3>
                <div className="tracker-sop-list">
                  {selectedOrder.stepsChecklist.map((step) => (
                    <article key={step.stepNo} data-surface-id={`order-tracker.sop.step.${step.stepNo}`}>
                      <span className="tracker-sop-number">{step.stepNo}</span>
                      <div>
                        <h4>{step.name}</h4>
                        <p>{step.notes}</p>
                        <span className="tracker-unavailable-badge">狀態 —　時間 —</span>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ) : (
              <section className="tracker-tab-panel" role="tabpanel" data-surface-id="order-tracker.notifications.unavailable">
                <h3>訂單生命週期通知紀錄</h3>
                <div className="tracker-unavailable-panel">
                  <strong>LINE 通知歷程尚未開放</strong>
                  <span>{selectedOrder.notificationTimelineMessage}</span>
                </div>
                <button
                  type="button"
                  className="tracker-disabled-action"
                  data-control-id="order-tracker.notifications.replay"
                  disabled
                >
                  手動重發（未開放）
                </button>
              </section>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default OrderTrackerPage;
