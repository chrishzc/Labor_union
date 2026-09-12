import { useEffect, useRef, useState, type FC } from 'react';
import type {
  ServiceDateConfirmationPreviewView,
  ServiceDateConfirmationQueryView,
} from '../api/orders/order_mutation_schemas';
import { ordersQueryClient } from '../api/orders/order_query_client';
import {
  schedulePrecisionClient,
  type SchedulePrecisionResult,
} from '../api/scheduling/schedule_precision_client';
import {
  applyServiceDatesFlow,
  fetchServiceDatesQuery,
  previewServiceDatesFlow,
  retryServiceDatesApplyFlow,
  retryServiceDatesObservationFlow,
  selectServiceDates,
  updateServiceDatesReason,
} from '../adapters/orders/order_mutation_adapter';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';

interface OrderServiceDatesPanelProps {
  caseNo: string;
  onObserved?: () => void;
}

type WorkingAction = 'load' | 'preview' | 'apply' | null;
type ServiceMode = '休周六' | '休周日' | '週休2日' | '連續服務';
type ServiceDatesRecovery =
  | { caseNo: string; kind: 'outcome_unknown' }
  | { caseNo: string; kind: 'observation_failed'; confirmedVersion: number }
  | { caseNo: string; kind: 'observation_in_progress' };
const AUTOMATIC_CONFIRMATION_REASON = '確認正式服務日期';

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '服務日期操作失敗';
}

function recoveryFromServiceDatesDraft(caseNo: string): ServiceDatesRecovery | null {
  const draft = orderMutationFlowStore.getServiceDatesDraft(caseNo);
  if (draft?.status === 'outcome_unknown') {
    return { caseNo, kind: 'outcome_unknown' };
  }
  if (draft?.status === 'observation_failed' && draft.receiptView !== null) {
    return {
      caseNo,
      kind: 'observation_failed',
      confirmedVersion: draft.receiptView.confirmed_version,
    };
  }
  if (
    draft?.status === 'apply_pending'
    || draft?.status === 'receipt_received'
    || draft?.status === 'requery_loading'
  ) {
    return { caseNo, kind: 'observation_in_progress' };
  }
  return null;
}

export const OrderServiceDatesPanel: FC<OrderServiceDatesPanelProps> = ({ caseNo, onObserved }) => {
  const [working, setWorking] = useState<WorkingAction>(null);
  const [queryView, setQueryView] = useState<ServiceDateConfirmationQueryView | null>(null);
  const [precision, setPrecision] = useState<SchedulePrecisionResult | null>(null);
  const [serviceMode, setServiceMode] = useState<ServiceMode | null>(null);
  const [selectedDates, setSelectedDates] = useState<string[]>([]);
  const [preview, setPreview] = useState<ServiceDateConfirmationPreviewView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [, setRecoveryRevision] = useState(0);
  const actionInFlight = useRef(new Set<string>());
  const renderedCaseNo = useRef(caseNo);
  renderedCaseNo.current = caseNo;
  const recovery = recoveryFromServiceDatesDraft(caseNo);
  const isRecoveryActive = recovery?.caseNo === caseNo;

  useEffect(() => {
    setWorking(null);
    setQueryView(null);
    setPrecision(null);
    setServiceMode(null);
    setSelectedDates([]);
    setPreview(null);
    setError(null);
    setSuccess(null);
    setRecoveryRevision((revision) => revision + 1);

    return orderMutationFlowStore.subscribe(() => {
      if (renderedCaseNo.current === caseNo) {
        setRecoveryRevision((revision) => revision + 1);
      }
    });
  }, [caseNo]);

  const captureRecovery = () => {
    setRecoveryRevision((revision) => revision + 1);
  };

  const loadAndCalculate = async () => {
    if (actionInFlight.current.has(caseNo) || isRecoveryActive) return;
    actionInFlight.current.add(caseNo);
    setWorking('load');
    setError(null);
    setSuccess(null);
    setPreview(null);
    try {
      const [actualStart, serviceDates, calendarDetail] = await Promise.all([
        ordersQueryClient.getActualStart(caseNo),
        fetchServiceDatesQuery(caseNo),
        ordersQueryClient.getOrderCalendarDetail(caseNo),
      ]);
      if (renderedCaseNo.current !== caseNo) return;
      const startDate = actualStart.current_actual_start_date ?? actualStart.planned_start_date;
      if (
        actualStart.case_no !== caseNo
        || serviceDates.case_no !== caseNo
        || calendarDetail.case_no !== caseNo
      ) {
        throw new Error('服務日期精算回讀案件編號不一致。');
      }

      const calculated = await schedulePrecisionClient.calculate({
        actual_start_date: startDate,
        target_service_days: serviceDates.contracted_service_days,
        service_mode: calendarDetail.service_mode,
      });
      if (renderedCaseNo.current !== caseNo) return;
      const selectable = new Set(serviceDates.selectable_dates);
      const calculatedDates = calculated.day_by_day
        .filter((day) => day.is_work_day && selectable.has(day.date))
        .map((day) => day.date);

      selectServiceDates(caseNo, calculatedDates);
      updateServiceDatesReason(caseNo, AUTOMATIC_CONFIRMATION_REASON);
      setQueryView(serviceDates);
      setPrecision(calculated);
      setServiceMode(calendarDetail.service_mode);
      setSelectedDates(calculatedDates);
    } catch (caught) {
      if (renderedCaseNo.current !== caseNo) return;
      setError(errorMessage(caught));
      setQueryView(null);
      setPrecision(null);
      setServiceMode(null);
      setSelectedDates([]);
    } finally {
      actionInFlight.current.delete(caseNo);
      if (renderedCaseNo.current === caseNo) setWorking(null);
    }
  };

  const changeDate = (date: string, checked: boolean) => {
    if (queryView === null || isRecoveryActive) return;
    const nextSet = new Set(selectedDates);
    if (checked) nextSet.add(date);
    else nextSet.delete(date);
    const nextDates = queryView.selectable_dates.filter((candidate) => nextSet.has(candidate));
    selectServiceDates(caseNo, nextDates);
    setSelectedDates(nextDates);
    setPreview(null);
    setSuccess(null);
  };

  const runPreview = async () => {
    if (actionInFlight.current.has(caseNo) || isRecoveryActive) return;
    actionInFlight.current.add(caseNo);
    setWorking('preview');
    setError(null);
    setSuccess(null);
    try {
      const nextPreview = await previewServiceDatesFlow(caseNo);
      if (renderedCaseNo.current !== caseNo) return;
      if (nextPreview.case_no !== caseNo) {
        throw new Error('服務日期確認預覽案件識別不一致。');
      }
      setPreview(nextPreview);
      setSuccess('服務日期確認內容已準備。');
    } catch (caught) {
      if (renderedCaseNo.current !== caseNo) return;
      setError(errorMessage(caught));
    } finally {
      actionInFlight.current.delete(caseNo);
      if (renderedCaseNo.current === caseNo) setWorking(null);
    }
  };

  const runApply = async () => {
    if (actionInFlight.current.has(caseNo) || isRecoveryActive) return;
    actionInFlight.current.add(caseNo);
    setWorking('apply');
    setError(null);
    setSuccess(null);
    try {
      const receipt = await applyServiceDatesFlow(caseNo);
      if (renderedCaseNo.current !== caseNo) return;
      const observed = orderMutationFlowStore.getServiceDatesDraft(caseNo);
      if (observed?.status !== 'observed' || observed.queryView === null) {
        throw new Error('服務日期已套用，但未取得正式回讀狀態。');
      }
      setQueryView(observed.queryView);
      setSelectedDates(observed.queryView.current_dates);
      setPreview(null);
      setSuccess(`服務日期已確認並回讀版本 #${receipt.confirmed_version}。`);
      onObserved?.();
    } catch (caught) {
      if (renderedCaseNo.current !== caseNo) return;
      captureRecovery();
      setError(errorMessage(caught));
    } finally {
      actionInFlight.current.delete(caseNo);
      if (renderedCaseNo.current === caseNo) setWorking(null);
    }
  };

  const retryApply = async () => {
    if (actionInFlight.current.has(caseNo) || recovery?.caseNo !== caseNo || recovery.kind !== 'outcome_unknown') return;
    actionInFlight.current.add(caseNo);
    setWorking('apply');
    setError(null);
    try {
      const receipt = await retryServiceDatesApplyFlow(caseNo);
      if (renderedCaseNo.current !== caseNo) return;
      const observed = orderMutationFlowStore.getServiceDatesDraft(caseNo);
      if (observed?.status !== 'observed' || observed.queryView === null) {
        throw new Error('服務日期已套用，但未取得正式回讀狀態。');
      }
      setQueryView(observed.queryView);
      setSelectedDates(observed.queryView.current_dates);
      setPreview(null);
      setSuccess(`服務日期已確認並回讀版本 #${receipt.confirmed_version}。`);
      onObserved?.();
    } catch (caught) {
      if (renderedCaseNo.current !== caseNo) return;
      captureRecovery();
      setError(errorMessage(caught));
    } finally {
      actionInFlight.current.delete(caseNo);
      if (renderedCaseNo.current === caseNo) setWorking(null);
    }
  };

  const retryObservation = async () => {
    if (actionInFlight.current.has(caseNo) || recovery?.caseNo !== caseNo || recovery.kind !== 'observation_failed') return;
    actionInFlight.current.add(caseNo);
    setWorking('apply');
    setError(null);
    try {
      const observed = await retryServiceDatesObservationFlow(caseNo);
      if (renderedCaseNo.current !== caseNo) return;
      if (observed.case_no !== caseNo) {
        throw new Error('服務日期正式回讀案件識別不一致。');
      }
      setQueryView(observed);
      setSelectedDates(observed.current_dates);
      setPreview(null);
      setSuccess(`服務日期已確認並回讀版本 #${recovery.confirmedVersion}。`);
      onObserved?.();
    } catch (caught) {
      if (renderedCaseNo.current !== caseNo) return;
      captureRecovery();
      setError(errorMessage(caught));
    } finally {
      actionInFlight.current.delete(caseNo);
      if (renderedCaseNo.current === caseNo) setWorking(null);
    }
  };

  const requiredDateCount = queryView?.contracted_service_days ?? 0;
  const canPreview = queryView !== null
    && selectedDates.length === requiredDateCount
    && selectedDates.length > 0
    && working === null
    && !isRecoveryActive;
  const canApply = preview !== null && working === null && !isRecoveryActive;

  return (
    <section aria-label={`案件 ${caseNo} 服務日期設定`}>
      <button
        type="button"
        className="order-v2-open-drawer"
        disabled={working !== null || isRecoveryActive}
        onClick={() => void loadAndCalculate()}
      >
        {working === 'load' ? '正在精算服務日期…' : '精算天數並設定服務日期'}
      </button>

      {error !== null && <p role="alert">{error}</p>}
      {success !== null && <p role="status">{success}</p>}
      {recovery?.caseNo === caseNo && recovery.kind === 'outcome_unknown' && (
        <button
          type="button"
          className="order-v2-open-drawer"
          disabled={working !== null}
          onClick={() => void retryApply()}
        >
          {working === 'apply' ? '以原操作重新確認中…' : '以原操作重新確認服務日期'}
        </button>
      )}
      {recovery?.caseNo === caseNo && recovery.kind === 'observation_failed' && (
        <button
          type="button"
          className="order-v2-open-drawer"
          disabled={working !== null}
          onClick={() => void retryObservation()}
        >
          {working === 'apply' ? '重新讀取服務日期結果中…' : '只重新讀取服務日期結果'}
        </button>
      )}
      {recovery?.caseNo === caseNo && recovery.kind === 'observation_in_progress' && (
        <p role="status">服務日期確認正在處理或回讀中，暫不可建立新操作。</p>
      )}

      {queryView !== null && precision !== null && serviceMode !== null && (
        <>
          <dl className="order-v2-business-summary" aria-label="建議服務日期摘要">
            <div><dt>排休類型</dt><dd>{serviceMode}</dd></div>
            <div><dt>建議開始</dt><dd>{precision.actual_start_date}</dd></div>
            <div><dt>建議完工</dt><dd>{precision.actual_end_date}</dd></div>
            <div><dt>合約服務日</dt><dd>{requiredDateCount} 天</dd></div>
          </dl>

          <div className="service-calendar-workbench-layout">
            <div className="calendar-matrix-card">
              <div className="calendar-month-header">
                <h3 style={{ fontSize: '1.05rem', fontWeight: 750, color: '#0f766e', margin: 0 }}>
                  📅 正式服務日期確認（日曆排盤）
                </h3>
                <span>已選 {selectedDates.length} / {requiredDateCount} 天</span>
              </div>

              <div
                className="calendar-days-grid"
                role="group"
                aria-label="服務日期月曆"
                data-surface-id="orders.date.service-date-selection"
              >
                {queryView.selectable_dates.length > 0 && Array.from({
                  length: new Date(`${queryView.selectable_dates[0]}T00:00:00`).getDay(),
                }).map((_, index) => <div key={`calendar-leading-${index}`} aria-hidden="true" />)}
                {queryView.selectable_dates.map((date) => {
                  const selected = selectedDates.includes(date);
                  return (
                    <button
                      key={date}
                      data-control-id="orders.date.service-date-select"
                      type="button"
                      aria-label={`服務日期 ${date}`}
                      aria-pressed={selected}
                      className={`calendar-date-cell${selected ? ' selected' : ''}`}
                      disabled={working !== null || isRecoveryActive}
                      onClick={() => changeDate(date, !selected)}
                    >
                      <span>{date}</span>
                      {selected && <span className="calendar-date-cell-badge">8hr / 服務</span>}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <button
            type="button"
            className="order-v2-open-drawer"
            disabled={!canPreview}
            onClick={() => void runPreview()}
          >
            {working === 'preview' ? '檢查確認內容中…' : '確認服務日期'}
          </button>
        </>
      )}

      {preview !== null && (
        <>
          <dl className="order-v2-business-summary" aria-label="服務日期確認內容">
            <div><dt>目前版本</dt><dd>{preview.current_version === null ? '首次確認' : `#${preview.current_version}`}</dd></div>
            <div><dt>確認日期</dt><dd>{preview.service_dates.join('、')}</dd></div>
          </dl>
          <p>系統會自動記錄「確認正式服務日期」，不需另外填寫原因。</p>
          <button
            type="button"
            className="order-v2-open-drawer"
            disabled={!canApply}
            onClick={() => void runApply()}
          >
            {working === 'apply' ? '確認並回讀中…' : '完成服務日期確認'}
          </button>
        </>
      )}

      {queryView !== null && queryView.current_dates.length > 0 && (
        <dl className="order-v2-business-summary" aria-label="正式服務日期回讀">
          <div><dt>正式版本</dt><dd>{queryView.current_version === null ? '未建立' : `#${queryView.current_version}`}</dd></div>
          <div><dt>正式服務日期</dt><dd>{queryView.current_dates.join('、')}</dd></div>
        </dl>
      )}
    </section>
  );
};

export default OrderServiceDatesPanel;
