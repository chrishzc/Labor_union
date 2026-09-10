import { useState, type FC } from 'react';
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
  selectServiceDates,
  updateServiceDatesReason,
} from '../adapters/orders/order_mutation_adapter';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';

interface OrderServiceDatesPanelProps {
  caseNo: string;
  onObserved?: () => void;
}

type WorkingAction = 'load' | 'preview' | 'apply' | null;
type ServiceMode = '週休1日' | '週休2日' | '連續服務';
const AUTOMATIC_CONFIRMATION_REASON = '確認正式服務日期';

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '服務日期操作失敗';
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

  const loadAndCalculate = async () => {
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
      setError(errorMessage(caught));
      setQueryView(null);
      setPrecision(null);
      setServiceMode(null);
      setSelectedDates([]);
    } finally {
      setWorking(null);
    }
  };

  const changeDate = (date: string, checked: boolean) => {
    if (queryView === null) return;
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
    setWorking('preview');
    setError(null);
    setSuccess(null);
    try {
      const nextPreview = await previewServiceDatesFlow(caseNo);
      setPreview(nextPreview);
      setSuccess('服務日期確認內容已準備。');
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setWorking(null);
    }
  };

  const runApply = async () => {
    setWorking('apply');
    setError(null);
    setSuccess(null);
    try {
      const receipt = await applyServiceDatesFlow(caseNo);
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
      setError(errorMessage(caught));
    } finally {
      setWorking(null);
    }
  };

  const requiredDateCount = queryView?.contracted_service_days ?? 0;
  const canPreview = queryView !== null
    && selectedDates.length === requiredDateCount
    && selectedDates.length > 0
    && working === null;
  const canApply = preview !== null && working === null;

  return (
    <section aria-label={`案件 ${caseNo} 服務日期設定`}>
      <button
        type="button"
        className="order-v2-open-drawer"
        disabled={working !== null}
        onClick={() => void loadAndCalculate()}
      >
        {working === 'load' ? '正在精算服務日期…' : '精算天數並設定服務日期'}
      </button>

      {error !== null && <p role="alert">{error}</p>}
      {success !== null && <p role="status">{success}</p>}

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
                      disabled={working !== null}
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
