/**
 * File: OrdersPage.tsx
 * Description: 顯示八個核准 Orders GET，保留 unavailable slots 與既有 Phase 2B 安全流程。
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import './OrdersPage.css';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { Drawer } from '../components/Drawer';
import {
  ORDER_FILTER_OPTIONS,
  adaptOrderSummaryPage,
  ORDERS_TYPED_PROJECTION_UNAVAILABLE,
  type OrderSummaryCardViewModel,
  type OrderSummaryPageViewModel,
} from '../adapters/orders/order_summary_adapter';
import {
  adaptServiceDateConfirmationDrawer,
  adaptMatchingWorkbenchDrawer,
  adaptOrderTermsContractDrawer,
  adaptOrderCancellationDrawer,
  type ServiceDateConfirmationDrawerViewModel,
  type MatchingWorkbenchDrawerViewModel,
  type OrderTermsContractDrawerViewModel,
  type OrderCancellationDrawerViewModel,
} from '../adapters/orders/order_detail_adapter';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import {
  applyReopenFlow,
  applyServiceDatesFlow,
  fetchServiceDatesQuery,
  previewReopenFlow,
  previewServiceDatesFlow,
  retryReopenApplyFlow,
  retryReopenObservationFlow,
  retryServiceDatesApplyFlow,
  retryServiceDatesObservationFlow,
  selectServiceDates,
  updateReopenReason,
  updateServiceDatesReason,
} from '../adapters/orders/order_mutation_adapter';
import { OrderMutationError } from '../api/orders/order_mutation_errors';

export const OrdersPage: React.FC = () => {
  const [pageData, setPageData] = useState<OrderSummaryPageViewModel | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Active drawer orders
  const [matchingOrder, setMatchingOrder] = useState<OrderSummaryCardViewModel | null>(null);
  const [contractOrder, setContractOrder] = useState<OrderSummaryCardViewModel | null>(null);
  const [cancelOrder, setCancelOrder] = useState<OrderSummaryCardViewModel | null>(null);
  const [dateConfirmOrder, setDateConfirmOrder] = useState<OrderSummaryCardViewModel | null>(null);
  const [reopenOrder, setReopenOrder] = useState<OrderSummaryCardViewModel | null>(null);
  const [, setMutationRevision] = useState(0);

  // Drawer detail states
  const [drawerLoading, setDrawerLoading] = useState<boolean>(false);
  const [dateConfirmDetail, setDateConfirmDetail] = useState<ServiceDateConfirmationDrawerViewModel | null>(null);
  const [matchingDetail, setMatchingDetail] = useState<MatchingWorkbenchDrawerViewModel | null>(null);
  const [contractDetail, setContractDetail] = useState<OrderTermsContractDrawerViewModel | null>(null);
  const [cancelDetail, setCancelDetail] = useState<OrderCancellationDrawerViewModel | null>(null);

  // Generation guard refs to prevent race conditions on fast switching
  const currentSummaryRequestRef = useRef<number>(0);
  const currentDrawerRequestRef = useRef<number>(0);

  useEffect(
    () => orderMutationFlowStore.subscribe(() => setMutationRevision((value) => value + 1)),
    []
  );

  // Load summaries from live API
  const fetchOrderSummaries = useCallback(async () => {
    const requestId = ++currentSummaryRequestRef.current;
    setLoading(true);
    setError(null);

    try {
      const rawPage = await ordersQueryClient.getOrderSummaries();
      if (requestId === currentSummaryRequestRef.current) {
        const adapted = adaptOrderSummaryPage(rawPage);
        setPageData(adapted);
      }
    } catch (err) {
      if (requestId === currentSummaryRequestRef.current) {
        const message = err instanceof Error ? err.message : '載入訂單列表失敗';
        setError(message);
      }
    } finally {
      if (requestId === currentSummaryRequestRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    fetchOrderSummaries();
  }, [fetchOrderSummaries]);

  // Handle opening Drawer 1: Service Date Confirmation
  const handleOpenDateConfirmDrawer = async (order: OrderSummaryCardViewModel) => {
    setDateConfirmOrder(order);
    setDateConfirmDetail(null);
    setDrawerLoading(true);
    const requestId = ++currentDrawerRequestRef.current;

    try {
      const [actualStartRes, orderDetailRes, calendarDetailRes] = await Promise.allSettled([
        ordersQueryClient.getActualStart(order.id),
        ordersQueryClient.getOrderDetail(order.id),
        ordersQueryClient.getOrderCalendarDetail(order.id),
      ]);
      await fetchServiceDatesQuery(order.id);

      if (requestId !== currentDrawerRequestRef.current) return;

      const actualStart = actualStartRes.status === 'fulfilled' ? actualStartRes.value : null;
      const orderDetail = orderDetailRes.status === 'fulfilled' ? orderDetailRes.value : null;
      const calendarDetail = calendarDetailRes.status === 'fulfilled' ? calendarDetailRes.value : null;

      if (requestId === currentDrawerRequestRef.current) {
        const adapted = adaptServiceDateConfirmationDrawer({
          caseNo: order.id,
          actualStart,
          calendarDetail,
          orderDetail,
        });
        setDateConfirmDetail(adapted);
      }
    } catch {
      // mutation adapter 已將 typed error 寫入 flow store；此層只避免事件 Promise 外洩。
    } finally {
      if (requestId === currentDrawerRequestRef.current) {
        setDrawerLoading(false);
      }
    }
  };

  const handleOpenReopen = (order: OrderSummaryCardViewModel) => {
    setReopenOrder(order);
    void previewReopenFlow(order.id).catch(() => undefined);
  };

  const handleCloseReopen = () => {
    if (!reopenOrder) return;
    const status = orderMutationFlowStore.getReopenDraft(reopenOrder.id)?.status;
    if (status === 'apply_pending' || status === 'outcome_unknown' || status === 'requery_loading') {
      return;
    }
    orderMutationFlowStore.closeReopenDialog(reopenOrder.id);
    setReopenOrder(null);
  };

  const serviceDatesDraft = dateConfirmOrder
    ? orderMutationFlowStore.getServiceDatesDraft(dateConfirmOrder.id)
    : undefined;
  const reopenDraft = reopenOrder
    ? orderMutationFlowStore.getReopenDraft(reopenOrder.id)
    : undefined;
  const serviceDatesLocked =
    serviceDatesDraft?.status === 'apply_pending' ||
    serviceDatesDraft?.status === 'outcome_unknown' ||
    serviceDatesDraft?.status === 'receipt_received' ||
    serviceDatesDraft?.status === 'requery_loading';
  const reopenLocked =
    reopenDraft?.status === 'apply_pending' ||
    reopenDraft?.status === 'outcome_unknown' ||
    reopenDraft?.status === 'receipt_received' ||
    reopenDraft?.status === 'requery_loading';
  const reopenTypedError =
    reopenDraft?.error instanceof OrderMutationError ? reopenDraft.error : null;

  // Handle opening Drawer 2: Matching Workbench
  const handleOpenMatchingDrawer = async (order: OrderSummaryCardViewModel) => {
    setMatchingOrder(order);
    setMatchingDetail(null);
    setDrawerLoading(true);
    const requestId = ++currentDrawerRequestRef.current;

    try {
      const [detailRes, assignmentPlanRes] = await Promise.allSettled([
        ordersQueryClient.getOrderDetail(order.id),
        ordersQueryClient.getAssignmentPlan(order.id),
      ]);

      if (requestId !== currentDrawerRequestRef.current) return;

      const assignmentPlan = assignmentPlanRes.status === 'fulfilled' ? assignmentPlanRes.value : null;
      const orderDetail = detailRes.status === 'fulfilled' ? detailRes.value : null;

      if (requestId === currentDrawerRequestRef.current) {
        const adapted = adaptMatchingWorkbenchDrawer({
          caseNo: order.id,
          assignmentPlan:
            orderDetail?.case_no === order.id && assignmentPlan?.case_no === order.id
              ? assignmentPlan
              : null,
        });
        setMatchingDetail(adapted);
      }
    } finally {
      if (requestId === currentDrawerRequestRef.current) {
        setDrawerLoading(false);
      }
    }
  };

  // Handle opening Drawer 3: Terms & Contract Progress
  const handleOpenContractDrawer = async (order: OrderSummaryCardViewModel) => {
    setContractOrder(order);
    setContractDetail(null);
    setDrawerLoading(true);
    const requestId = ++currentDrawerRequestRef.current;

    try {
      const [termsRes, completionRes, orderDetailRes] = await Promise.allSettled([
        ordersQueryClient.getOrderTerms(order.id),
        ordersQueryClient.getContractCompletion(order.id),
        ordersQueryClient.getOrderDetail(order.id),
      ]);

      if (requestId !== currentDrawerRequestRef.current) return;

      const terms = termsRes.status === 'fulfilled' ? termsRes.value : null;
      const completion = completionRes.status === 'fulfilled' ? completionRes.value : null;
      const orderDetail = orderDetailRes.status === 'fulfilled' ? orderDetailRes.value : null;

      if (requestId === currentDrawerRequestRef.current) {
        const adapted = adaptOrderTermsContractDrawer({
          caseNo: order.id,
          terms,
          completion,
          summary: order,
          orderDetail,
        });
        setContractDetail(adapted);
      }
    } finally {
      if (requestId === currentDrawerRequestRef.current) {
        setDrawerLoading(false);
      }
    }
  };

  // Handle opening Drawer 4: Cancellation & Refund Preview
  const handleOpenCancelDrawer = (order: OrderSummaryCardViewModel) => {
    setCancelOrder(order);
    setCancelDetail(adaptOrderCancellationDrawer({ caseNo: order.id, summary: order }));
  };

  const allItems = pageData?.items || [];
  const filteredOrders = allItems;

  return (
    <div>
      <div className="page-header-banner" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 className="page-title">📦 訂單與客戶管理</h1>
          <p className="page-subtitle">顯示核准的訂單查詢投影；未開放的媒合、簽回與退款資訊會在原位置明確標示。</p>
        </div>
        <button
          style={{
            padding: '10px 20px',
            backgroundColor: '#ccc',
            color: '#fff',
            border: 'none',
            borderRadius: '10px',
            fontWeight: 700,
            cursor: 'not-allowed',
            opacity: 0.8,
          }}
          disabled={true}
          title="[查詢模式] 建立新訂單功能尚在開發中 (Phase 2A 唯讀查詢模式)"
        >
          + 新建訂單
        </button>
      </div>

      {/* Status Filter Chips */}
      <div className="orders-filter-bar">
        {ORDER_FILTER_OPTIONS.map((filter) => {
          const isLoadedScope = filter.stage === '全部';
          return (
            <button
              key={filter.stage}
              type="button"
              data-control-id={`orders.filter.${filter.stage}`}
              className={`filter-chip ${isLoadedScope ? 'active' : ''}`}
              disabled={!isLoadedScope}
              aria-disabled={!isLoadedScope}
              title={isLoadedScope ? '目前已載入的 Orders 摘要' : '後端尚未提供 typed 七階段投影'}
            >
              {filter.label} {pageData ? `(${isLoadedScope ? pageData.loadedCount : '—'})` : ''}
            </button>
          );
        })}
      </div>

      {/* Loading & Error States */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '40px', color: '#64748b', fontSize: '1rem', fontWeight: 600 }}>
          ⏳ 正在載入即時訂單數據...
        </div>
      )}

      {error && !loading && (
        <div style={{ padding: '16px 20px', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '12px', color: '#991b1b', marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>⚠️ 載入訂單資料失敗：{error}</div>
          <button
            style={{ padding: '6px 14px', backgroundColor: '#dc2626', color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 700, cursor: 'pointer' }}
            onClick={fetchOrderSummaries}
          >
            重試
          </button>
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && filteredOrders.length === 0 && (
        <div style={{ textAlign: 'center', padding: '48px', backgroundColor: '#fff', borderRadius: '16px', border: '1px solid #e2e8f0', color: '#64748b' }}>
          <div style={{ fontSize: '2.5rem', marginBottom: '10px' }}>☕</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 700 }}>目前無符合條件的訂單</div>
          <div style={{ fontSize: '0.85rem', marginTop: '6px' }}>目前沒有已載入的訂單摘要</div>
        </div>
      )}

      {/* Orders Grid Cards */}
      {!loading && !error && (
        <div className="orders-grid">
          {filteredOrders.map((order) => (
            <div key={order.id} className="order-card">
              <div className="order-card-top">
                <span className="order-id-badge">{order.id}</span>
                <span className="order-status-pill">伺服器狀態：{order.orderStatus}</span>
              </div>

              <div className="order-card-body">
                <div className="order-client-title">👤 {order.clientName}</div>
                <div>📞 聯絡電話：{order.clientPhone}</div>
                <div>📍 服務地址：{order.serviceAddress}</div>
                <div>📅 約定服務：{order.serviceRange}（{order.serviceDaysLabel}）</div>

                {/* Actual Start Date Badge if exists */}
                {order.actualStartDate && (
                  <div style={{ color: '#0f766e', fontWeight: 700, fontSize: '0.85rem' }}>
                    🗓️ 實際服務開始日：{order.actualStartDate}
                  </div>
                )}

                {/* Daily Time Tuple */}
                <div>
                  ⏰ 每日時段：
                  {order.serviceTimeTuple && order.serviceTimeTuple.dailyHours > 0 ? (
                    <strong>{order.serviceTimeTuple.formattedText}</strong>
                  ) : (
                    <span style={{ color: '#dc2626', fontWeight: 600 }}>⚠️ 時段三欄尚未確認</span>
                  )}
                </div>

                {/* Order Terms Tags */}
                <div className="order-terms-pill-row">
                  <span className="term-tag">
                    🍳 下廚料理：{ORDERS_TYPED_PROJECTION_UNAVAILABLE}
                  </span>
                  <span className="term-tag">🏢 樓層加給：{ORDERS_TYPED_PROJECTION_UNAVAILABLE}</span>
                  <span className="term-tag">
                    💰 定金：{order.depositSettledText}
                  </span>
                </div>

                <div>
                  💰 合約總額：<strong style={{ color: '#ff7f50', fontSize: '1.05rem' }}>{order.contractAmountFormatted}</strong>
                </div>

                {/* Doula Assigned Box */}
                <div className="order-doula-box">
                  {order.assignedDoulaName ? (
                    <div>
                      <div>👩‍🍼 摘要所列月嫂：<strong>{order.assignedDoulaName}</strong></div>
                      <div style={{ fontSize: '0.8rem', color: '#74593f' }}>正式推薦與分段方案須查看 typed assignment projection</div>
                    </div>
                  ) : (
                    <div style={{ color: '#74593f', fontWeight: 600 }}>
                      {order.assignedDoulaDisplay}
                    </div>
                  )}
                </div>
              </div>

              <div className="order-card-actions">
                <button
                  className="btn-secondary-action"
                  onClick={() => handleOpenContractDrawer(order)}
                >
                  📑 條款與契約
                </button>

                <button
                  className="btn-primary-action"
                  onClick={() => handleOpenMatchingDrawer(order)}
                >
                  👩‍🍼 媒合與正式排班
                </button>

                {/* Service Date Confirmation Button */}
                <button
                  style={{
                    padding: '6px 12px',
                    backgroundColor: '#f0fdfa',
                    color: '#0f766e',
                    border: '1px solid #99f6e4',
                    borderRadius: '8px',
                    fontWeight: 700,
                    fontSize: '0.8rem',
                    cursor: 'pointer',
                  }}
                  onClick={() => handleOpenDateConfirmDrawer(order)}
                >
                  📅 確認服務日期
                </button>

                <button
                  className="btn-cancel-preview"
                  onClick={() => handleOpenCancelDrawer(order)}
                  title="訂單取消與退款試算 (Zero-Mutation Preview)"
                >
                  🛑 取消試算
                </button>

                <button
                  data-control-id="orders.card.reopen"
                  style={{
                    padding: '6px 12px',
                    backgroundColor: '#fef2f2',
                    color: '#991b1b',
                    border: '1px solid #fecaca',
                    borderRadius: '8px',
                    fontWeight: 700,
                    fontSize: '0.8rem',
                    cursor: 'pointer',
                  }}
                  onClick={() => handleOpenReopen(order)}
                  title="由伺服器預覽判定是否可受控重開，不依前端訂單階段推測"
                >
                  🔄 重啟訂單
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 1. Service Date Confirmation Gate Drawer */}
      <Drawer
        isOpen={dateConfirmOrder !== null}
        onClose={() => {
          if (!serviceDatesLocked) setDateConfirmOrder(null);
        }}
        size="wide"
        title={`📅 確認實際服務日期與精算日程工作台 — ${dateConfirmOrder?.id || ''}`}
        footer={
          <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', alignItems: 'center' }}>
            <span style={{ fontSize: '0.85rem', color: '#888' }}>
              門檻：客戶與月嫂皆確認同一日程版本無異議後，方可解鎖正式排班。
            </span>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                style={{
                  padding: '8px 16px',
                  border: '1px solid #dec0b6',
                  borderRadius: '8px',
                  background: '#fff',
                  cursor: 'pointer',
                }}
                onClick={() => setDateConfirmOrder(null)}
                disabled={serviceDatesLocked}
              >
                關閉
              </button>
              <button
                style={{
                  padding: '8px 20px',
                  backgroundColor: '#ccc',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '8px',
                  fontWeight: 700,
                  cursor: 'not-allowed',
                }}
                disabled={true}
                title="[查詢模式] 轉入履約需由後端排班狀態機自動推進，查詢模式不支援手動轉入"
              >
                🚀 轉入正式服務履約 (Active Assignment)
              </button>
            </div>
          </div>
        }
      >
        {dateConfirmOrder && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {drawerLoading && (
              <div style={{ textAlign: 'center', padding: '20px', color: '#0d9488' }}>
                ⏳ 正在載入服務日程即時確認數據...
              </div>
            )}

            <section
              data-surface-id="orders.drawer.service-dates"
              style={{ backgroundColor: '#f8fafc', border: '1px solid #cbd5e1', padding: '20px', borderRadius: '14px' }}
            >
              <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#0f766e', marginBottom: '12px' }}>
                正式服務日期確認
              </h3>

              {serviceDatesDraft?.queryView && (
                <>
                  <div className="service-dates-meta-row" style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', marginBottom: '14px', fontSize: '0.85rem' }}>
                    <span>合約服務天數：{serviceDatesDraft.queryView.contracted_service_days} 天</span>
                    <span>目前確認版本：{serviceDatesDraft.queryView.current_version === null ? '尚未確認' : `v${serviceDatesDraft.queryView.current_version}`}</span>
                    <span>已確認日期：{serviceDatesDraft.queryView.current_dates.length > 0 ? serviceDatesDraft.queryView.current_dates.join(', ') : '無'}</span>
                  </div>

                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '12px' }}>
                    {serviceDatesDraft.queryView.selectable_dates.map((date) => {
                      const selected = serviceDatesDraft.selectedDates.includes(date);
                      return (
                        <button
                          key={date}
                          data-control-id="orders.date.service-date-select"
                          type="button"
                          aria-pressed={selected}
                          disabled={serviceDatesLocked}
                          onClick={() =>
                            selectServiceDates(
                              dateConfirmOrder.id,
                              selected
                                ? serviceDatesDraft.selectedDates.filter((value) => value !== date)
                                : [...serviceDatesDraft.selectedDates, date]
                            )
                          }
                          style={{
                            padding: '7px 10px',
                            borderRadius: '8px',
                            border: selected ? '1px solid #0d9488' : '1px solid #cbd5e1',
                            background: selected ? '#ccfbf1' : '#fff',
                            color: '#0f766e',
                            cursor: serviceDatesLocked ? 'not-allowed' : 'pointer',
                          }}
                        >
                          {date}
                        </button>
                      );
                    })}
                  </div>

                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginBottom: '12px' }}>
                    <button
                      type="button"
                      disabled={serviceDatesLocked}
                      onClick={() => selectServiceDates(dateConfirmOrder.id, serviceDatesDraft.queryView!.suggested_dates)}
                    >
                      帶入建議日期
                    </button>
                    <button
                      type="button"
                      data-control-id="orders.date.service-date-preview"
                      disabled={
                        serviceDatesLocked ||
                        serviceDatesDraft.status === 'preview_loading' ||
                        serviceDatesDraft.selectedDates.length !== serviceDatesDraft.queryView.contracted_service_days
                      }
                      onClick={() => void previewServiceDatesFlow(dateConfirmOrder.id).catch(() => undefined)}
                    >
                      {serviceDatesDraft.status === 'preview_loading' ? '預覽處理中…' : '預覽正式服務日期'}
                    </button>
                  </div>
                </>
              )}

              {serviceDatesDraft?.previewView && (
                <div style={{ background: '#fff', border: '1px solid #99f6e4', borderRadius: '10px', padding: '14px' }}>
                  <h4 style={{ color: '#0f766e', marginBottom: '8px' }}>服務週次精算預覽</h4>
                  {serviceDatesDraft.previewView.weeks.map((week) => (
                    <div key={week.week_number} style={{ marginBottom: '6px', fontSize: '0.85rem' }}>
                      第 {week.week_number} 週：{week.period_start} ～ {week.period_end}（{week.service_dates.join(', ')}）
                    </div>
                  ))}
                  <label style={{ display: 'block', marginTop: '10px', fontWeight: 700 }}>
                    確認原因
                    <textarea
                      className="mutation-reason-input"
                      rows={3}
                      maxLength={500}
                      value={serviceDatesDraft.reason}
                      disabled={serviceDatesLocked}
                      onChange={(event) => updateServiceDatesReason(dateConfirmOrder.id, event.target.value)}
                      style={{ display: 'block', width: '100%', marginTop: '6px' }}
                    />
                  </label>
                  <button
                    type="button"
                    data-control-id="orders.date.service-date-apply"
                    disabled={serviceDatesLocked || serviceDatesDraft.reason.trim().length === 0}
                    onClick={() => void applyServiceDatesFlow(dateConfirmOrder.id).catch(() => undefined)}
                    style={{ marginTop: '10px' }}
                  >
                    確認套用服務日期
                  </button>
                </div>
              )}

              {serviceDatesDraft?.status === 'outcome_unknown' && (
                <div role="alert" style={{ marginTop: '12px', color: '#9a3412' }}>
                  服務日期確認回應逾時或未明；只可用原 Payload 與原 Key 重試。
                  <button type="button" onClick={() => void retryServiceDatesApplyFlow(dateConfirmOrder.id).catch(() => undefined)}>
                    重試提交
                  </button>
                </div>
              )}
              {(serviceDatesDraft?.status === 'observed' || serviceDatesDraft?.status === 'receipt_received' || serviceDatesDraft?.status === 'requery_loading') && serviceDatesDraft.receiptView && (
                <div role="status" style={{ marginTop: '12px', color: '#166534', fontWeight: 700 }}>
                  服務日期已確認成功（Confirmed v{serviceDatesDraft.receiptView.confirmed_version}）
                </div>
              )}
              {serviceDatesDraft?.status === 'observation_failed' && (
                <div role="alert" style={{ marginTop: '12px', color: '#9a3412' }}>
                  套用 receipt 已收到，但重新查詢失敗：{serviceDatesDraft.error?.message}
                  <button type="button" onClick={() => void retryServiceDatesObservationFlow(dateConfirmOrder.id).catch(() => undefined)}>
                    重試觀察
                  </button>
                </div>
              )}
              {(serviceDatesDraft?.status === 'typed_error' || serviceDatesDraft?.status === 'stale') && (
                <div role="alert" style={{ marginTop: '12px', color: '#b91c1c' }}>
                  {serviceDatesDraft.error?.message ?? '服務日期操作失敗，請重新查詢。'}
                </div>
              )}
            </section>

            {/* Step 1: Input / Confirm Actual Start Date & Rest Days */}
            <div style={{ backgroundColor: '#ffffff', border: '1px solid #fed9b8', padding: '20px', borderRadius: '14px' }}>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#ff7f50', marginBottom: '12px' }}>
                一、 填寫/更正實際服務開始日 (actual_start_date)
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '14px' }}>
                <div>
                  <label htmlFor="edit-actual-start-date" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#57423b', marginBottom: '6px' }}>
                    實際服務開始日 (產婦生產通知開工日)：
                  </label>
                  <input
                    id="edit-actual-start-date"
                    type="date"
                    disabled={true}
                    value={dateConfirmDetail?.actualStartDate !== '—' ? dateConfirmDetail?.actualStartDate || '' : ''}
                    title="[查詢模式] 實際服務開始日需由產婦通報開工並經審核確認，查詢模式不可直接修改"
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '8px', border: '1px solid #dec0b6', fontSize: '0.95rem', fontWeight: 600, backgroundColor: '#f8fafc', cursor: 'not-allowed' }}
                    readOnly
                  />
                </div>
                <div>
                  <label htmlFor="edit-rest-days-note" style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: '#57423b', marginBottom: '6px' }}>
                    排休與請假摘要：
                  </label>
                  <input
                    id="edit-rest-days-note"
                    type="text"
                    disabled={true}
                    value={dateConfirmDetail?.restDaysSummary || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（排休摘要）`}
                    title="[查詢模式] 排休摘要需由排班系統核定，查詢模式不支援編輯"
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '8px', border: '1px solid #dec0b6', fontSize: '0.9rem', backgroundColor: '#f8fafc', cursor: 'not-allowed' }}
                    readOnly
                  />
                </div>
              </div>

              {/* Negotiated Holiday Decisions */}
              <div style={{ backgroundColor: '#fff8f6', border: '1px solid #fed9b8', borderRadius: '10px', padding: '14px' }}>
                <div style={{ fontSize: '0.88rem', fontWeight: 700, color: '#c2410c', marginBottom: '8px' }}>
                  🏮 本案檔期內排班模式：{dateConfirmDetail?.serviceMode || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（排班模式）`}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                  <div style={{ backgroundColor: '#fff', border: '1px solid #dec0b6', padding: '10px 12px', borderRadius: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: '0.85rem' }}>🗓️ 服務模式排休精算</div>
                      <div style={{ fontSize: '0.75rem', color: '#888' }}>條款：國定假日排休依服務模式統一精算</div>
                    </div>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.8rem', fontWeight: 600, color: '#c2410c', cursor: 'not-allowed' }}>
                      <input
                        type="checkbox"
                        checked={true}
                        disabled={true}
                        title="[查詢模式] 國定假日協議由雙邊合約排班引擎核定，查詢模式不支援變更"
                        style={{ accentColor: '#ff7f50', cursor: 'not-allowed' }}
                        readOnly
                      />
                      系統精算排定
                    </label>
                  </div>
                </div>
              </div>
            </div>

            {/* Step 2: Schedule Calculation Result Snapshot */}
            <div style={{ backgroundColor: '#f0fdfa', border: '1px solid #99f6e4', padding: '20px', borderRadius: '14px' }}>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#0f766e', marginBottom: '12px' }}>
                二、 精算日程表輸出結果 (Schedule Calculation Snapshot)
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '14px' }}>
                <div style={{ backgroundColor: '#fff', padding: '12px', borderRadius: '8px', border: '1px solid #ccfbf1' }}>
                  <div style={{ fontSize: '0.78rem', color: '#64748b' }}>實際服務起訖</div>
                  <div style={{ fontWeight: 700, fontSize: '0.95rem', color: '#0f766e', marginTop: '2px' }}>
                    {dateConfirmDetail?.serviceRangeText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（服務起訖）`}
                  </div>
                </div>
                <div style={{ backgroundColor: '#fff', padding: '12px', borderRadius: '8px', border: '1px solid #ccfbf1' }}>
                  <div style={{ fontSize: '0.78rem', color: '#64748b' }}>約定出勤總量</div>
                  <div style={{ fontWeight: 700, fontSize: '0.95rem', color: '#0f766e', marginTop: '2px' }}>
                    {dateConfirmDetail?.calculatedServiceDaysText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（精算服務天數）`}
                  </div>
                </div>
                <div style={{ backgroundColor: '#fff', padding: '12px', borderRadius: '8px', border: '1px solid #ccfbf1' }}>
                  <div style={{ fontSize: '0.78rem', color: '#64748b' }}>排休天數合計</div>
                  <div style={{ fontWeight: 700, fontSize: '0.95rem', color: '#166534', marginTop: '2px' }}>
                    {dateConfirmDetail?.restDaysCountText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（順延天數）`}
                  </div>
                </div>
                <div style={{ backgroundColor: '#fff', padding: '12px', borderRadius: '8px', border: '1px solid #ccfbf1' }}>
                  <div style={{ fontSize: '0.78rem', color: '#64748b' }}>服務後緩衝期間</div>
                  <div style={{ fontWeight: 700, fontSize: '0.85rem', color: '#92400e', marginTop: '2px' }}>
                    {dateConfirmDetail?.bufferDateRange || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（服務後緩衝期間）`}
                  </div>
                </div>
              </div>

              <button
                style={{
                  width: '100%',
                  padding: '10px 20px',
                  backgroundColor: '#94a3b8',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '8px',
                  fontWeight: 700,
                  fontSize: '0.9rem',
                  cursor: 'not-allowed',
                }}
                disabled={true}
                title="[查詢模式] 日程推播需經由後端 LINE 通知服務發送，查詢模式不支援手動發送"
              >
                📢 發送精算日程表給客戶與月嫂確認 (Send via LINE) ➔
              </button>
            </div>

            {/* Step 3: Two-Party Confirmation Gate (Customer & Caregiver) */}
            <div style={{ backgroundColor: '#ffffff', border: '1px solid #dec0b6', padding: '20px', borderRadius: '14px' }}>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#1e1b19', marginBottom: '12px' }}>
                三、 雙方確認狀態與電話人工補登 (Matching Schedule Confirmation Gate)
              </h3>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {/* Customer Confirmation Row */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 16px', borderRadius: '10px', backgroundColor: dateConfirmDetail?.customerConfirmed ? '#f0fdf4' : '#fff7ed', border: '1px solid #fed7aa' }}>
                  <div>
                    <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>👤 客戶確認 ({dateConfirmOrder.clientName})：</span>
                    <span style={{ marginLeft: '8px', fontWeight: 700, color: dateConfirmDetail?.customerConfirmed ? '#16a34a' : '#c2410c' }}>
                      {dateConfirmDetail?.customerConfirmedText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（客戶確認狀態）`}
                    </span>
                  </div>
                  <button
                    style={{ padding: '6px 14px', backgroundColor: '#cbd5e1', color: '#475569', border: 'none', borderRadius: '6px', fontWeight: 600, fontSize: '0.85rem', cursor: 'not-allowed' }}
                    disabled={true}
                    title="[查詢模式] 電話補登需經由審核授權，查詢模式不支援人工寫入"
                  >
                    📞 電話補登客戶確認
                  </button>
                </div>

                {/* Staff Confirmation Row */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 16px', borderRadius: '10px', backgroundColor: dateConfirmDetail?.staffConfirmed ? '#f0fdf4' : '#fff7ed', border: '1px solid #fed7aa' }}>
                  <div>
                    <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>👩‍🍼 月嫂確認 ({dateConfirmOrder.assignedDoulaName || '指派月嫂'})：</span>
                    <span style={{ marginLeft: '8px', fontWeight: 700, color: dateConfirmDetail?.staffConfirmed ? '#16a34a' : '#c2410c' }}>
                      {dateConfirmDetail?.staffConfirmedText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（月嫂確認狀態）`}
                    </span>
                  </div>
                  <button
                    style={{ padding: '6px 14px', backgroundColor: '#cbd5e1', color: '#475569', border: 'none', borderRadius: '6px', fontWeight: 600, fontSize: '0.85rem', cursor: 'not-allowed' }}
                    disabled={true}
                    title="[查詢模式] 電話補登需經由審核授權，查詢模式不支援人工寫入"
                  >
                    📞 電話補登月嫂確認
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </Drawer>

      {/* 2. 1280px Extra-Wide Matching Workbench (size="xl") */}
      <Drawer
        isOpen={matchingOrder !== null}
        onClose={() => setMatchingOrder(null)}
        size="xl"
        title={`👩‍🍼 媒合與正式排班查詢工作台 — ${matchingOrder?.id || ''}`}
        footer={
          <button
            style={{
              padding: '12px 28px',
              border: '1px solid #dec0b6',
              borderRadius: '10px',
              background: '#fff',
              cursor: 'pointer',
              fontWeight: 700,
              fontSize: '0.95rem',
            }}
            onClick={() => setMatchingOrder(null)}
          >
            關閉工作台
          </button>
        }
      >
        {matchingOrder && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '28px', maxWidth: '1200px', margin: '0 auto' }}>
            {drawerLoading && (
              <div style={{ textAlign: 'center', padding: '20px', color: '#ff7f50' }}>
                ⏳ 正在載入訂單 detail 與正式排班投影...
              </div>
            )}

            {/* Top Demand Summary: 4-Column Card Grid */}
            <div style={{
              backgroundColor: '#ffffff',
              padding: '24px 28px',
              borderRadius: '18px',
              border: '1px solid #fed9b8',
              boxShadow: '0 4px 16px rgba(255,127,80,0.06)',
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: '20px',
            }}>
              <div style={{ borderRight: '1px solid #f2e2dc', paddingRight: '16px' }}>
                <div style={{ fontSize: '0.8rem', color: '#8b7169', fontWeight: 600 }}>產婦與服務地點</div>
                <div style={{ fontSize: '1.15rem', fontWeight: 700, color: '#1e1b19', marginTop: '4px' }}>{matchingOrder.clientName}</div>
                <div style={{ fontSize: '0.85rem', color: '#57423b', marginTop: '2px' }}>📍 {matchingOrder.serviceAddress}</div>
              </div>

              <div style={{ borderRight: '1px solid #f2e2dc', paddingRight: '16px' }}>
                <div style={{ fontSize: '0.8rem', color: '#8b7169', fontWeight: 600 }}>約定起訖與天數</div>
                <div style={{ fontSize: '1.15rem', fontWeight: 700, color: '#ff7f50', marginTop: '4px' }}>{matchingOrder.serviceDaysLabel}</div>
                <div style={{ fontSize: '0.85rem', color: '#57423b', marginTop: '2px' }}>📅 {matchingOrder.serviceRange}</div>
              </div>

              <div style={{ borderRight: '1px solid #f2e2dc', paddingRight: '16px' }}>
                <div style={{ fontSize: '0.8rem', color: '#8b7169', fontWeight: 600 }}>每日時段與料理</div>
                <div style={{ fontSize: '1.15rem', fontWeight: 700, color: '#1e1b19', marginTop: '4px' }}>
                  {matchingOrder.serviceTimeTuple?.dailyHours ? `${matchingOrder.serviceTimeTuple.dailyHours} 小時 / 天` : ORDERS_TYPED_PROJECTION_UNAVAILABLE}
                </div>
                <div style={{ fontSize: '0.85rem', color: '#57423b', marginTop: '2px' }}>
                  🍳 {ORDERS_TYPED_PROJECTION_UNAVAILABLE}
                </div>
              </div>

              <div>
                <div style={{ fontSize: '0.8rem', color: '#8b7169', fontWeight: 600 }}>合約總額與定金</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#ff7f50', marginTop: '2px' }}>{matchingOrder.contractAmountFormatted}</div>
                <div style={{ fontSize: '0.85rem', color: '#74593f', marginTop: '2px', fontWeight: 600 }}>
                  💰 定金：{matchingOrder.depositSettledText}
                </div>
              </div>
            </div>

            {/* Step 1: Multi-Caregiver Willingness Pool */}
            <div style={{
              backgroundColor: '#ffffff',
              border: '1px solid #f2e2dc',
              borderRadius: '18px',
              padding: '28px 32px',
              boxShadow: '0 4px 20px rgba(74,69,67,0.05)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', paddingBottom: '14px', borderBottom: '2px solid #f5ece9' }}>
                <div>
                  <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#1e1b19', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ backgroundColor: '#ffdbcf', color: '#6c2000', width: '28px', height: '28px', borderRadius: '50%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.9rem' }}>1</span>
                    月嫂配對意願徵詢池 (Caregiver Willingness Pool)
                  </h3>
                  <p style={{ fontSize: '0.85rem', color: '#74593f', marginTop: '4px' }}>
                    候選聯繫池與正式推薦尚未開放 typed projection；下方僅顯示 assignment-owned 正式排班段。
                  </p>
                </div>

                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                  <button
                    style={{
                      padding: '8px 16px',
                      backgroundColor: '#ccc',
                      color: '#fff',
                      border: 'none',
                      borderRadius: '8px',
                      fontWeight: 700,
                      fontSize: '0.88rem',
                      cursor: 'not-allowed',
                    }}
                    disabled={true}
                    title="[查詢模式] 意願池候選人挑選由媒合推薦引擎處理，查詢模式不支援新增"
                  >
                    ➕ 加入月嫂至意願池
                  </button>

                  <button
                    style={{ background: 'none', border: '1px solid #fecdd3', color: '#e11d48', padding: '8px 14px', borderRadius: '8px', fontSize: '0.85rem', cursor: 'not-allowed', fontWeight: 600, opacity: 0.6 }}
                    disabled={true}
                    title="[查詢模式] 配對池重設需由媒合審核模組處理，查詢模式不支援直接重設"
                  >
                    ✖ 重設配對池
                  </button>
                </div>
              </div>

              {matchingDetail?.assignmentSegments.length ? (
                <div data-surface-id="orders.matching.assignment-plan" style={{ display: 'grid', gap: '10px', marginBottom: '18px' }}>
                  <h4 style={{ margin: 0 }}>正式執行排班（非候選推薦）</h4>
                  {matchingDetail.assignmentSegments.map((segment) => (
                    <article key={segment.key} style={{ border: '1px solid #dec0b6', borderRadius: '10px', padding: '12px' }}>
                      <strong>第 {segment.sequence} 段｜Staff #{segment.staffId}</strong>
                      <div>{segment.serviceRange}</div>
                      <div>正式服務日：{segment.officialServiceDates.length ? segment.officialServiceDates.join('、') : '無'}</div>
                      <div>{segment.actualHoursText}</div>
                    </article>
                  ))}
                </div>
              ) : (
                <div data-surface-id="orders.matching.assignment-plan-unavailable" role="status" style={{ marginBottom: '18px', color: '#74593f' }}>
                  {matchingDetail ? '目前沒有伺服器回傳的正式執行排班段' : ORDERS_TYPED_PROJECTION_UNAVAILABLE}
                </div>
              )}

              {/* Multi-Candidate Cards in the Pool */}
              {matchingDetail && matchingDetail.candidatePool.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {matchingDetail.candidatePool.map((c) => (
                    <div key={c.staffId} style={{
                      border: c.selectedForResume ? '2px solid #ff7f50' : '1px solid #fed9b8',
                      padding: '24px',
                      borderRadius: '16px',
                      backgroundColor: c.selectedForResume ? '#fffdfb' : '#ffffff',
                      boxShadow: c.selectedForResume ? '0 4px 16px rgba(255,127,80,0.12)' : 'none',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '16px',
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'not-allowed', backgroundColor: c.selectedForResume ? '#ffedd5' : '#f5ece9', padding: '8px 14px', borderRadius: '10px' }}>
                            <input
                              type="checkbox"
                              checked={c.selectedForResume}
                              disabled={true}
                              title="[查詢模式] 推薦候選人勾選狀態僅供檢視"
                              style={{ width: '18px', height: '18px', accentColor: '#ff7f50', cursor: 'not-allowed' }}
                              readOnly
                            />
                            <span style={{ fontSize: '0.9rem', fontWeight: 700, color: c.selectedForResume ? '#c2410c' : '#57423b' }}>
                              {c.selectedForResume ? '★ 已勾選推薦此履歷' : '勾選推薦此月嫂'}
                            </span>
                          </label>

                          <div style={{ width: '48px', height: '48px', borderRadius: '50%', backgroundColor: '#ffdbcf', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.6rem' }}>
                            👩‍🍼
                          </div>

                          <div>
                            <div style={{ fontWeight: 700, fontSize: '1.2rem', color: '#1e1b19' }}>
                              {c.staffName}
                              <span style={{ fontSize: '0.85rem', color: '#888', fontWeight: 400, marginLeft: '10px' }}>📞 {c.staffPhone}</span>
                            </div>
                            <div style={{ fontSize: '0.85rem', color: '#74593f', marginTop: '2px' }}>
                              📍 {c.location} ｜ 年資 {c.experienceYears} 年 ｜ 問卷契合度：<strong style={{ color: '#16a34a' }}>{c.matchScore}%</strong>
                            </div>
                          </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <span style={{
                            padding: '6px 16px',
                            borderRadius: '9999px',
                            fontSize: '0.9rem',
                            fontWeight: 700,
                            backgroundColor: c.willingness === 'willing' ? '#dcfce7' : c.willingness === 'unwilling' ? '#fee2e2' : '#ffedd5',
                            color: c.willingness === 'willing' ? '#166534' : c.willingness === 'unwilling' ? '#991b1b' : '#c2410c',
                          }}>
                            月嫂意願：{c.willingnessLabel}
                          </span>

                          <button
                            aria-label={`移除候選月嫂 ${c.staffName}（查詢模式不可用）`}
                            style={{ background: 'none', border: 'none', color: '#ccc', cursor: 'not-allowed', fontSize: '1.1rem' }}
                            title="[查詢模式] 查詢模式不支援移除候選人"
                            disabled={true}
                          >
                            🗑️
                          </button>
                        </div>
                      </div>

                      {/* Push Info Cards */}
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                        <div style={{ backgroundColor: '#fffdfc', padding: '16px 18px', borderRadius: '12px', border: '1px solid #dec0b6', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontWeight: 700, fontSize: '0.92rem', color: '#1e1b19' }}>📢 訂單資訊-1 (粗篩案況徵詢)</span>
                            <span style={{ fontSize: '0.8rem', color: c.info1Sent ? '#16a34a' : '#888', fontWeight: 600 }}>
                              {c.info1Sent ? `✅ 已發送 (${c.info1SentAt || '已推播'})` : '未發送'}
                            </span>
                          </div>
                          <div style={{ fontSize: '0.8rem', color: '#888' }}>
                            推播服務天數、時段與地區，保護產婦個資並徵詢初步接案意願。
                          </div>
                          <button
                            style={{
                              marginTop: 'auto',
                              padding: '8px 14px',
                              backgroundColor: '#e2e8f0',
                              color: '#64748b',
                              border: 'none',
                              borderRadius: '8px',
                              fontWeight: 700,
                              fontSize: '0.85rem',
                              cursor: 'not-allowed',
                            }}
                            disabled={true}
                            title="[查詢模式] LINE 推播需由後端派單服務發送，查詢模式不支援手動發送"
                          >
                            💬 發送 訂單資訊-1 (LINE)
                          </button>
                        </div>

                        <div style={{ backgroundColor: '#fffdfc', padding: '16px 18px', borderRadius: '12px', border: '1px solid #dec0b6', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontWeight: 700, fontSize: '0.92rem', color: '#1e1b19' }}>📄 訂單資訊-2 (精篩條款與地址)</span>
                            <span style={{ fontSize: '0.8rem', color: c.info2Sent ? '#16a34a' : '#888', fontWeight: 600 }}>
                              {c.info2Sent ? `✅ 已發送 (${c.info2SentAt || '已推播'})` : '未發送'}
                            </span>
                          </div>
                          <div style={{ fontSize: '0.8rem', color: '#888' }}>
                            推播詳細合約條款、地址與特殊膳食需求，供月嫂二次確認。
                          </div>
                          <button
                            style={{
                              marginTop: 'auto',
                              padding: '8px 14px',
                              backgroundColor: '#e2e8f0',
                              color: '#64748b',
                              border: 'none',
                              borderRadius: '8px',
                              fontWeight: 700,
                              fontSize: '0.85rem',
                              cursor: 'not-allowed',
                            }}
                            disabled={true}
                            title="[查詢模式] LINE 推播需由後端派單服務發送，查詢模式不支援手動發送"
                          >
                            📄 發送 訂單資訊-2 (LINE)
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ textAlign: 'center', padding: '36px', color: '#888' }}>
                  <div style={{ fontSize: '2rem', marginBottom: '8px' }}>👩‍🍼</div>
                  <div style={{ fontWeight: 600, fontSize: '1rem' }}>候選聯繫池目前不可用</div>
                  <div style={{ fontSize: '0.85rem', marginTop: '4px' }}>{matchingDetail?.candidatePoolUnavailable || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（候選聯繫池）`}</div>
                </div>
              )}
            </div>

            {/* Step 2: Send Resume to Client */}
            <div style={{
              backgroundColor: '#ffffff',
              border: '1px solid #f2e2dc',
              borderRadius: '18px',
              padding: '28px 32px',
              boxShadow: '0 4px 20px rgba(74,69,67,0.05)',
            }}>
              <div style={{ marginBottom: '16px', paddingBottom: '14px', borderBottom: '2px solid #f5ece9' }}>
                <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#1e1b19', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ backgroundColor: '#ffdbcf', color: '#6c2000', width: '28px', height: '28px', borderRadius: '50%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.9rem' }}>2</span>
                  從意願池選擇並傳送履歷給客戶 (Resume Selection & Presentation)
                </h3>
              </div>

              <div style={{ marginBottom: '18px' }}>
                <label style={{ display: 'block', fontSize: '0.9rem', fontWeight: 700, marginBottom: '6px', color: '#1e1b19' }}>
                  傳送給客戶的履歷說明備註 (Resume Presentation Notes)：
                </label>
                <textarea
                  rows={3}
                  disabled={true}
                  placeholder="[查詢模式] 履歷備註需由行政配對系統編輯，查詢模式為唯讀展示"
                  style={{ width: '100%', padding: '12px 16px', borderRadius: '10px', border: '1px solid #dec0b6', fontSize: '0.95rem', lineHeight: '1.5', backgroundColor: '#f8fafc', cursor: 'not-allowed' }}
                  readOnly
                />
              </div>

              <button
                style={{
                  padding: '12px 28px',
                  backgroundColor: '#ccc',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '10px',
                  fontWeight: 700,
                  cursor: 'not-allowed',
                  fontSize: '1rem',
                }}
                disabled={true}
                title="[查詢模式] 履歷推播需由後端通知服務處理，查詢模式不支援發送"
              >
                📨 傳送已勾選月嫂履歷給客戶 (Send Selected Resumes via LINE) ➔
              </button>
            </div>

            {/* Step 3: Customer Decision & Waiting Lock */}
            <div style={{
              backgroundColor: '#ffffff',
              border: '1px solid #f2e2dc',
              borderRadius: '18px',
              padding: '28px 32px',
              boxShadow: '0 4px 20px rgba(74,69,67,0.05)',
            }}>
              <div style={{ marginBottom: '20px', paddingBottom: '14px', borderBottom: '2px solid #f5ece9' }}>
                <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#1e1b19', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ backgroundColor: '#ffdbcf', color: '#6c2000', width: '28px', height: '28px', borderRadius: '50%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.9rem' }}>3</span>
                  客戶配對回覆與等待訂金鎖 (Customer Decision & Waiting-Deposit Lock)
                </h3>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
                <div style={{ backgroundColor: '#fffdfc', border: '1px solid #dec0b6', padding: '20px', borderRadius: '14px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '1rem', fontWeight: 700 }}>客戶回覆狀態：</span>
                    <span style={{
                      padding: '4px 12px',
                      borderRadius: '9999px',
                      fontWeight: 700,
                      fontSize: '0.85rem',
                      backgroundColor: '#f8fafc',
                      color: '#57423b',
                    }}>
                      {matchingDetail?.customerDecisionLabel || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（客戶決策）`}
                    </span>
                  </div>
                </div>

                <div style={{ backgroundColor: '#fffdfc', border: '1px solid #dec0b6', padding: '20px', borderRadius: '14px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div style={{ fontWeight: 700, fontSize: '1rem', color: '#1e1b19' }}>🔒 Waiting-Deposit 檔期鎖定</div>
                  <p style={{ fontSize: '0.85rem', color: '#74593f', lineHeight: '1.5' }}>
                    {matchingDetail?.waitingLockText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（等待訂金鎖）`}
                  </p>
                  <button
                    style={{
                      marginTop: 'auto',
                      padding: '12px 20px',
                      backgroundColor: '#ccc',
                      color: '#fff',
                      border: 'none',
                      borderRadius: '10px',
                      fontWeight: 700,
                      cursor: 'not-allowed',
                      fontSize: '0.95rem',
                    }}
                    disabled={true}
                    title="[查詢模式] 檔期鎖定需由後端排程引擎執行，查詢模式不支援直接加鎖"
                  >
                    🔒 產生並建立等待訂金鎖 (Acquire Lock)
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </Drawer>

      {/* 3. Order Terms & Contract Progress Drawer */}
      <Drawer
        isOpen={contractOrder !== null}
        onClose={() => setContractOrder(null)}
        size="wide"
        title={`📑 訂單契約條款與簽署進度 - ${contractOrder?.id || ''}`}
        footer={
          <button
            style={{
              padding: '8px 16px',
              border: 'none',
              borderRadius: '8px',
              background: '#ff7f50',
              color: '#fff',
              fontWeight: 700,
              cursor: 'pointer',
            }}
            onClick={() => setContractOrder(null)}
          >
            關閉
          </button>
        }
      >
        {contractOrder && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {drawerLoading && (
              <div style={{ textAlign: 'center', padding: '16px', color: '#ff7f50' }}>
                ⏳ 正在載入契約條款數據...
              </div>
            )}

            <div style={{ backgroundColor: '#fff8f6', padding: '16px', borderRadius: '12px', border: '1px solid #f2e2dc' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#ff7f50', marginBottom: '8px' }}>正式 Order Terms (不可原地修改)</h3>
              <p><strong>客戶姓名：</strong>{contractDetail?.clientName || contractOrder.clientName}</p>
              <p><strong>服務起訖：</strong>{contractDetail?.serviceRange || contractOrder.serviceRange}（{contractDetail?.serviceDays === null || contractDetail?.serviceDays === undefined ? ORDERS_TYPED_PROJECTION_UNAVAILABLE : `${contractDetail.serviceDays} 天`}）</p>
              <p><strong>每日時段 Tuple：</strong>{contractDetail?.serviceTimeText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（服務時段）`}</p>
              <p><strong>下廚料理條款：</strong>{contractDetail?.requiresCookingText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（下廚料理條款）`}</p>
              <p><strong>樓層加給費：</strong>{contractDetail?.floorFeeText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（樓層加給）`}</p>
              <p><strong>合約總金額：</strong>{contractDetail?.contractAmountText || contractOrder.contractAmountFormatted}</p>
            </div>

            <div style={{ border: '1px solid #dec0b6', padding: '16px', borderRadius: '12px' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '8px' }}>📝 雙邊契約簽署證據 (Contract Signing SSOT)</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '0.88rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>👩‍🍼 月嫂服務契約 (Staff Contract)：</span>
                  <span style={{ color: contractDetail?.staffContractSigned ? '#16a34a' : '#c2410c', fontWeight: 700 }}>
                    {contractDetail?.staffContractSignedText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（月嫂契約簽回）`}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>💰 客戶定金核銷 (Deposit Settlement)：</span>
                  <span style={{ color: contractDetail?.depositSettled ? '#16a34a' : '#c2410c', fontWeight: 700 }}>
                    {contractDetail?.depositSettledText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（客戶定金核銷）`}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>👥 客戶服務契約 (Client Contract)：</span>
                  <span style={{ color: contractDetail?.clientContractSigned ? '#16a34a' : '#c2410c', fontWeight: 700 }}>
                    {contractDetail?.clientContractSignedText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（客戶契約簽回）`}
                  </span>
                </div>
              </div>
            </div>

            {contractDetail?.domainBlockers && contractDetail.domainBlockers.length > 0 && (
              <div style={{ backgroundColor: '#fef2f2', border: '1px solid #fecaca', padding: '14px', borderRadius: '10px' }}>
                <div style={{ fontWeight: 700, color: '#991b1b', marginBottom: '6px' }}>🛑 完工阻擋檢核項目：</div>
                <ul style={{ margin: 0, paddingLeft: '20px', color: '#b91c1c', fontSize: '0.85rem' }}>
                  {contractDetail.domainBlockers.map((b, idx) => (
                    <li key={idx}>{b}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Drawer>

      {/* 4. Cancellation & Refund Preview Drawer */}
      <Drawer
        isOpen={cancelOrder !== null}
        onClose={() => setCancelOrder(null)}
        size="wide"
        title={`🛑 訂單取消與退款試算 (Preview) - ${cancelOrder?.id || ''}`}
        footer={
          <>
            <button
              style={{
                padding: '8px 16px',
                border: '1px solid #dec0b6',
                borderRadius: '8px',
                background: '#fff',
                cursor: 'pointer',
              }}
              onClick={() => setCancelOrder(null)}
            >
              放棄取消
            </button>
            <button
              style={{
                padding: '8px 16px',
                border: 'none',
                borderRadius: '8px',
                background: '#ccc',
                color: '#fff',
                fontWeight: 700,
                cursor: 'not-allowed',
              }}
              disabled={true}
              title="[查詢模式] 退款與訂單取消需經由工會行政與財務審核模組處理，唯讀查詢模式不支援直接提交取消申請"
            >
              確認執行取消 (Apply Cancellation)
            </button>
          </>
        }
      >
        {cancelOrder && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {drawerLoading && (
              <div style={{ textAlign: 'center', padding: '16px', color: '#9f1239' }}>
                ⏳ 正在計算後端退款試算明細...
              </div>
            )}

            <div style={{ backgroundColor: '#fff1f2', padding: '16px', borderRadius: '12px', border: '1px solid #fecdd3' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#9f1239', marginBottom: '6px' }}>
                取消類型：{cancelDetail?.cancellationType || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（取消類型）`}
              </h3>
              <p style={{ fontSize: '0.85rem', color: '#be123c' }}>
                {cancelDetail?.statutoryExplanation || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（取消與退款規則）`}
              </p>
            </div>

            <div style={{ backgroundColor: '#fff', padding: '16px', borderRadius: '12px', border: '1px solid #dec0b6' }}>
              <h4 style={{ fontWeight: 700, marginBottom: '8px' }}>📊 退款財務試算明細 (純預覽)</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.88rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>合約總金額：</span>
                  <span>{cancelDetail?.contractAmountText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（取消基準金額）`}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>實收定金金額：</span>
                  <span>{cancelDetail?.depositAmountText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（實收定金）`}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>已實質履約天數：</span>
                  <span>{cancelDetail?.servedDaysText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（已履約天數）`}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: '#dc2626' }}>
                  <span>違約/手續扣除費：</span>
                  <span>{cancelDetail?.penaltyFeeText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（扣除費用）`}</span>
                </div>
                <div style={{ borderTop: '2px solid #dec0b6', paddingTop: '8px', marginTop: '4px', display: 'flex', justifyContent: 'space-between', fontWeight: 700, fontSize: '1.1rem', color: '#ff7f50' }}>
                  <span>應退客戶金額：</span>
                  <span>{cancelDetail?.refundAmountText || `${ORDERS_TYPED_PROJECTION_UNAVAILABLE}（應退款金額）`}</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </Drawer>

      <Drawer
        isOpen={reopenOrder !== null}
        onClose={handleCloseReopen}
        size="wide"
        title={`🔄 訂單受控重開 — ${reopenOrder?.id || ''}`}
        footer={
          <button
            type="button"
            onClick={handleCloseReopen}
            disabled={reopenLocked}
            style={{ padding: '8px 16px' }}
          >
            關閉
          </button>
        }
      >
        {reopenOrder && (
          <div data-surface-id="orders.modal.reopen" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {reopenDraft?.status === 'preview_loading' && (
              <div role="status">正在向伺服器取得重開預覽…</div>
            )}

            {reopenDraft?.previewView && (
              <>
                <div style={{ background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: '12px', padding: '16px' }}>
                  <h3 style={{ marginBottom: '8px', color: '#9a3412' }}>伺服器重開候選</h3>
                  <div>{reopenDraft.previewView.before_status} → <strong>{reopenDraft.previewView.after_status}</strong></div>
                  <div>Order v{reopenDraft.previewView.order_version}</div>
                  <div>Client Finance v{reopenDraft.previewView.client_finance_version}</div>
                  <div>Payroll v{reopenDraft.previewView.payroll_version}</div>
                  <div>Cancellation Event #{reopenDraft.previewView.cancellation_event_id}</div>
                  <div>
                    requires_fresh_scheduling_preview：
                    {reopenDraft.previewView.requires_fresh_scheduling_preview ? '是，必須重新產生排程預覽' : '否'}
                  </div>
                  <div>恢復 Assignment／Schedule／Lock：0／0／0</div>
                </div>

                <label style={{ fontWeight: 700 }}>
                  重開原因
                  <textarea
                    data-control-id="orders.reopen.reason"
                    rows={4}
                    maxLength={500}
                    value={reopenDraft.reason}
                    disabled={reopenLocked}
                    onChange={(event) => updateReopenReason(reopenOrder.id, event.target.value)}
                    style={{ display: 'block', width: '100%', marginTop: '6px' }}
                  />
                </label>
                <button
                  type="button"
                  data-control-id="orders.reopen.apply"
                  disabled={reopenLocked || reopenDraft.reason.trim().length === 0}
                  onClick={() => void applyReopenFlow(reopenOrder.id, fetchOrderSummaries).catch(() => undefined)}
                >
                  確認受控重開
                </button>
              </>
            )}

            {reopenDraft?.status === 'outcome_unknown' && (
              <div role="alert" style={{ color: '#9a3412' }}>
                訂單重開回應逾時或未明；只可使用相同 Payload 與相同 Key 重試。
                <button
                  type="button"
                  onClick={() => void retryReopenApplyFlow(reopenOrder.id, fetchOrderSummaries).catch(() => undefined)}
                >
                  重試重開
                </button>
              </div>
            )}

            {reopenDraft?.receiptView && (
              <div role="status" style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '12px', padding: '14px', color: '#166534' }}>
                <strong>訂單已成功重開</strong>
                <div>伺服器狀態：{reopenDraft.receiptView.lifecycle_status}</div>
                <div>Order v{reopenDraft.receiptView.order_version}</div>
                <div>仍需 fresh scheduling preview：{reopenDraft.receiptView.requires_fresh_scheduling_preview ? '是' : '否'}</div>
              </div>
            )}

            {reopenDraft?.status === 'observation_failed' && (
              <div role="alert" style={{ color: '#9a3412' }}>
                重開 receipt 已收到，但重新查詢失敗：{reopenDraft.error?.message}
                <button
                  type="button"
                  onClick={() => void retryReopenObservationFlow(reopenOrder.id, fetchOrderSummaries).catch(() => undefined)}
                >
                  重試觀察
                </button>
              </div>
            )}

            {(reopenDraft?.status === 'typed_error' || reopenDraft?.status === 'stale') && (
              <div role="alert" style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '12px', padding: '14px', color: '#991b1b' }}>
                <div>{reopenDraft.error?.message ?? '訂單受控重開失敗。'}</div>
                {reopenTypedError?.correlationId && <div>ID: {reopenTypedError.correlationId}</div>}
                {reopenTypedError?.domainBlockers.map((blocker) => (
                  <div key={blocker}>{blocker}</div>
                ))}
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default OrdersPage;
