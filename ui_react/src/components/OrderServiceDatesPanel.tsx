import { useEffect, useRef, useState, type FC } from 'react';
import type {
  ServiceDateConfirmationPreviewView,
  ServiceDateConfirmationQueryView,
} from '../api/orders/order_mutation_schemas';
import { ordersMutationClient } from '../api/orders/order_mutation_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import {
  schedulePrecisionClient,
  type SchedulePrecisionResult,
} from '../api/scheduling/schedule_precision_client';
import {
  applyServiceDatesFlow,
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
  onOpenActualStart?: () => void;
  calculationRevision?: number;
}

type WorkingAction = 'load' | 'preview' | 'apply' | null;
type DateLoadMode = 'read' | 'calculate' | 'resume';
type ServiceMode = '休周六' | '休周日' | '週休2日' | '連續服務';
type ServiceDatesRecovery =
  | { caseNo: string; kind: 'outcome_unknown' }
  | { caseNo: string; kind: 'observation_failed'; confirmedVersion: number }
  | { caseNo: string; kind: 'superseded'; confirmedVersion: number; currentVersion: number }
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
    const receipt = draft.receiptView;
    const current = draft.queryView;
    if (current !== null && current.case_no === caseNo && receipt.case_no === caseNo
      && current.current_version !== null && current.current_version > receipt.confirmed_version
      && current.order_version >= receipt.order_version && current.scheduling_version >= receipt.scheduling_version
      && (current.current_dates.length !== receipt.service_dates.length
        || current.current_dates.some((date) => !receipt.service_dates.includes(date)))) {
      return { caseNo, kind: 'superseded', confirmedVersion: receipt.confirmed_version, currentVersion: current.current_version };
    }
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

export const OrderServiceDatesPanel: FC<OrderServiceDatesPanelProps> = ({ caseNo, onObserved, onOpenActualStart, calculationRevision = 0 }) => {
  const [working, setWorking] = useState<WorkingAction>(null);
  const [queryView, setQueryView] = useState<ServiceDateConfirmationQueryView | null>(null);
  const [precision, setPrecision] = useState<SchedulePrecisionResult | null>(null);
  const [serviceMode, setServiceMode] = useState<ServiceMode | null>(null);
  const [selectedDates, setSelectedDates] = useState<string[]>([]);
  const [preview, setPreview] = useState<ServiceDateConfirmationPreviewView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [basisNotice, setBasisNotice] = useState<string | null>(null);
  const [calculationBasis, setCalculationBasis] = useState<{ date: string; confirmed: boolean } | null>(null);
  const [hasManualChanges, setHasManualChanges] = useState(false);
  const [, setRecoveryRevision] = useState(0);
  const [attemptedCalculationRevision, setAttemptedCalculationRevision] = useState(0);
  const actionInFlight = useRef(new Set<string>());
  const calculationSequence = useRef(0);
  const readController = useRef<AbortController | null>(null);
  const renderedCaseNo = useRef(caseNo);
  renderedCaseNo.current = caseNo;
  const recovery = recoveryFromServiceDatesDraft(caseNo);
  const isRecoveryActive = recovery?.caseNo === caseNo;
  const needsBasisUpdate = calculationRevision > attemptedCalculationRevision;

  useEffect(() => {
    setAttemptedCalculationRevision(0);
    setWorking(null);
    setQueryView(null);
    setPrecision(null);
    setServiceMode(null);
    setSelectedDates([]);
    setPreview(null);
    setError(null);
    setSuccess(null);
    setBasisNotice(null);
    setCalculationBasis(null);
    setHasManualChanges(false);
    setRecoveryRevision((revision) => revision + 1);

    const unsubscribe = orderMutationFlowStore.subscribe(() => {
      if (renderedCaseNo.current === caseNo) {
        setRecoveryRevision((revision) => revision + 1);
      }
    });
    // Opening an existing case reads saved dates; it does not regenerate them.
    if (calculationRevision === 0) void loadServiceDates('read');
    return () => {
      unsubscribe();
      readController.current?.abort();
      readController.current = null;
      calculationSequence.current += 1;
    };
    // A new case has its own read lifecycle; revisions are handled below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseNo]);

  const captureRecovery = () => {
    setRecoveryRevision((revision) => revision + 1);
  };

  const loadServiceDates = async (mode: DateLoadMode) => {
    const pending = recoveryFromServiceDatesDraft(caseNo);
    if (actionInFlight.current.has(caseNo)
      || (pending !== null && !(mode === 'resume' && pending.kind === 'superseded'))
      || (mode === 'resume' && pending?.kind !== 'superseded')) return;
    const original = orderMutationFlowStore.getServiceDatesDraft(caseNo);
    const receipt = original?.receiptView;
    const previous = original?.queryView;
    const originalKey = original?.idempotencyKey;
    readController.current?.abort();
    const controller = new AbortController();
    readController.current = controller;
    const request = ++calculationSequence.current;
    const current = () => !controller.signal.aborted
      && readController.current === controller
      && renderedCaseNo.current === caseNo
      && calculationSequence.current === request;
    if (mode === 'calculate') setAttemptedCalculationRevision(calculationRevision);
    setWorking('load');
    setError(null); setSuccess(null); setPreview(null);
    if (mode === 'calculate') {
      setBasisNotice(hasManualChanges
        ? '正在重新精算；先前人工調整將由新建議取代，請重新核對。'
        : '正在依目前日期基準更新服務日期與日曆。');
      setPrecision(null); setServiceMode(null); setCalculationBasis(null);
    }
    try {
      // Pure reads: stale responses must be discarded BEFORE any shared draft writes.
      const serviceDates = await ordersMutationClient.getServiceDates(caseNo, { signal: controller.signal });
      if (!current()) return;
      if (serviceDates.case_no !== caseNo) throw new Error('服務日期回讀案件編號不一致。');
      if (previous && (serviceDates.order_version < previous.order_version
        || serviceDates.scheduling_version < previous.scheduling_version)) {
        throw new Error('服務日期回讀版本落後，尚未更新；請重新讀取。');
      }
      if (pending?.kind === 'superseded' && (serviceDates.current_version === null
        || serviceDates.current_version < pending.currentVersion)) {
        throw new Error('尚未讀到目前正式日期版本；原收據仍保留，請重新讀取。');
      }
      let dates = serviceDates.current_dates;
      let calculated: SchedulePrecisionResult | null = null;
      let modeValue: ServiceMode | null = null;
      let basis: { date: string; confirmed: boolean } | null = null;
      if (mode === 'calculate') {
        const [actualStart, calendarDetail] = await Promise.all([
          ordersQueryClient.getActualStart(caseNo, { signal: controller.signal }),
          ordersQueryClient.getOrderCalendarDetail(caseNo, { signal: controller.signal }),
        ]);
        if (!current()) return;
        if (actualStart.case_no !== caseNo || calendarDetail.case_no !== caseNo) {
          throw new Error('服務日期精算回讀案件編號不一致。');
        }
        if (actualStart.order_version !== serviceDates.order_version
          || actualStart.scheduling_version !== serviceDates.scheduling_version) {
          throw new Error('實際開始日與服務日期版本不同，尚未更新；請重新精算。');
        }
        basis = { date: actualStart.current_actual_start_date ?? actualStart.planned_start_date,
          confirmed: actualStart.current_actual_start_date !== null };
        modeValue = calendarDetail.service_mode;
        calculated = await schedulePrecisionClient.calculate({
          actual_start_date: basis.date,
          target_service_days: serviceDates.contracted_service_days,
          service_mode: modeValue,
        });
        if (!current()) return;
        const selectable = new Set(serviceDates.selectable_dates);
        dates = calculated.day_by_day.filter((day) => day.is_work_day && selectable.has(day.date)).map((day) => day.date);
      }
      const liveRecovery = recoveryFromServiceDatesDraft(caseNo);
      if (!current() || actionInFlight.current.has(caseNo)
        || (mode === 'resume'
          ? liveRecovery?.kind !== 'superseded' || orderMutationFlowStore.getServiceDatesDraft(caseNo)?.receiptView !== receipt
          : liveRecovery !== null)) return;
      const draft = orderMutationFlowStore.getServiceDatesDraft(caseNo);
      if (draft?.queryView !== previous || draft?.receiptView !== receipt
        || draft?.idempotencyKey !== originalKey) return;
      // A same-basis unsaved draft survives a read; a saved arrangement is never recalculated by a read.
      const keepDraft = mode === 'read' && draft?.receiptView === null
        && draft.queryView?.order_version === serviceDates.order_version
        && draft.queryView?.scheduling_version === serviceDates.scheduling_version
        && draft.queryView?.current_version === serviceDates.current_version
        && draft.selectedDates.length > 0;
      if (keepDraft) dates = [...draft.selectedDates];
      // This validated read starts a fresh preview lifecycle, never an unresolved command.
      orderMutationFlowStore.resetServiceDatesDraft(caseNo);
      orderMutationFlowStore.setServiceDatesQueryReady(caseNo, serviceDates);
      selectServiceDates(caseNo, dates);
      updateServiceDatesReason(caseNo, AUTOMATIC_CONFIRMATION_REASON);
      setQueryView(serviceDates); setSelectedDates(dates);
      setPrecision(calculated); setServiceMode(modeValue); setCalculationBasis(basis);
      setHasManualChanges(keepDraft);
      setBasisNotice(basis === null ? null
        : `${basis.confirmed ? '已依正式實際開始日更新' : '尚未確認實際開始日，已依原訂日期試算'}服務日期，請核對後再確認。${hasManualChanges ? '先前人工調整已由新建議取代。' : ''}`);
      if (mode === 'resume') {
        // Explicitly adopting the current formal arrangement resolves the pending view update, without recalculating it.
        setAttemptedCalculationRevision(calculationRevision);
        setSuccess(`已載入目前正式日期版本 #${serviceDates.current_version}，請核對後再確認；未重送原操作。`);
        onObserved?.();
      }
    } catch (caught) {
      if (!current()) return;
      setError(errorMessage(caught));
      if (mode !== 'resume') setQueryView(null);
      setBasisNotice(mode === 'calculate' ? '服務日期尚未更新，請重新精算；目前正式日期未被此試算修改。' : null);
      setPrecision(null); setServiceMode(null); setCalculationBasis(null);
    } finally {
      if (current()) { readController.current = null; setWorking(null); }
    }
  };

  useEffect(() => {
    if (!needsBasisUpdate) return;
    setPreview(null);
    if (isRecoveryActive || actionInFlight.current.has(caseNo)) {
      setBasisNotice('日期基準已變更；待目前操作結果確認後，會接續更新。');
      return;
    }
    void loadServiceDates('calculate');
    // A blocked revision is not consumed. Resume when its write/readback settles,
    // but do not retry failed reads forever or recalculate on unrelated refreshes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseNo, calculationRevision, needsBasisUpdate, isRecoveryActive, working]);

  const changeDate = (date: string, checked: boolean) => {
    if (queryView === null || isRecoveryActive || needsBasisUpdate || readController.current !== null) return;
    const nextSet = new Set(selectedDates);
    if (checked) nextSet.add(date);
    else nextSet.delete(date);
    const nextDates = queryView.selectable_dates.filter((candidate) => nextSet.has(candidate));
    selectServiceDates(caseNo, nextDates);
    setSelectedDates(nextDates);
    setPreview(null);
    setSuccess(null);
    setHasManualChanges(true);
  };

  const runPreview = async () => {
    if (actionInFlight.current.has(caseNo) || isRecoveryActive || needsBasisUpdate || readController.current !== null) return;
    actionInFlight.current.add(caseNo);
    const controller = new AbortController();
    readController.current = controller;
    const basisSequence = calculationSequence.current;
    setWorking('preview');
    setError(null);
    setSuccess(null);
    try {
      const nextPreview = await previewServiceDatesFlow(caseNo, { signal: controller.signal });
      if (renderedCaseNo.current !== caseNo || calculationSequence.current !== basisSequence) return;
      if (nextPreview.case_no !== caseNo) {
        throw new Error('服務日期確認預覽案件識別不一致。');
      }
      setPreview(nextPreview);
      setSuccess('服務日期確認內容已準備。');
    } catch (caught) {
      if (renderedCaseNo.current !== caseNo || calculationSequence.current !== basisSequence) return;
      setError(errorMessage(caught));
    } finally {
      if (readController.current === controller) readController.current = null;
      actionInFlight.current.delete(caseNo);
      if (renderedCaseNo.current === caseNo && calculationSequence.current === basisSequence) setWorking(null);
    }
  };

  const runApply = async () => {
    if (actionInFlight.current.has(caseNo) || isRecoveryActive || needsBasisUpdate || readController.current !== null) return;
    actionInFlight.current.add(caseNo);
    const basisSequence = calculationSequence.current;
    setWorking('apply');
    setError(null);
    setSuccess(null);
    try {
      const receipt = await applyServiceDatesFlow(caseNo);
      if (renderedCaseNo.current !== caseNo || calculationSequence.current !== basisSequence) return;
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
      if (renderedCaseNo.current !== caseNo || calculationSequence.current !== basisSequence) return;
      captureRecovery();
      setError(errorMessage(caught));
    } finally {
      actionInFlight.current.delete(caseNo);
      if (renderedCaseNo.current === caseNo && calculationSequence.current === basisSequence) setWorking(null);
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
    && !isRecoveryActive
    && !needsBasisUpdate;
  const canApply = preview !== null && working === null && !isRecoveryActive && !needsBasisUpdate;

  return (
    <section aria-label={`案件 ${caseNo} 服務日期設定`}>
      <button
        type="button"
        className="order-v2-open-drawer"
        disabled={working !== null || isRecoveryActive}
        onClick={() => void loadServiceDates('calculate')}
      >
        {working === 'load' ? '正在更新服務日期…' : '精算天數並設定服務日期'}
      </button>

      {error !== null && <p role="alert">{error}</p>}
      {error !== null && queryView === null && !isRecoveryActive && (
        <button type="button" disabled={working !== null} onClick={() => void loadServiceDates('read')}>重新讀取正式服務日期</button>
      )}
      {basisNotice !== null && <p role="status">{basisNotice}</p>}
      {calculationBasis !== null && (
        <div className="order-case-review-note" aria-label="服務日期計算基準">
          <strong>{calculationBasis.confirmed ? '正式實際開始日' : '目前以原訂日試算'}</strong>
          <span>：{calculationBasis.date}</span>
          {onOpenActualStart !== undefined && (
            <button type="button" className="order-v2-open-drawer" onClick={onOpenActualStart}>
              確認／更正實際開始日
            </button>
          )}
        </div>
      )}
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
      {recovery?.caseNo === caseNo && recovery.kind === 'superseded' && (
        <div role="status">
          <p>本次收據為版本 #{recovery.confirmedVersion}；目前正式日期已更新為版本 #{recovery.currentVersion}。請載入目前日期核對，不要重送原操作。</p>
          <button type="button" className="order-v2-open-drawer" disabled={working !== null}
            onClick={() => void loadServiceDates('resume')}>載入目前正式服務日期</button>
        </div>
      )}
      {recovery?.caseNo === caseNo && recovery.kind === 'observation_in_progress' && (
        <p role="status">服務日期確認正在處理或回讀中，暫不可建立新操作。</p>
      )}

      {queryView !== null && (
        <>
          {queryView.bound_staff.length > 0 && (
            <div role="status" className="order-v2-inline-notice">
              <strong>既定服務人員：</strong>
              {queryView.bound_staff.map((staff) => staff.staff_name).join('、')}
              <span>。此歷史綁定已保留，不需重新挑選候選或再次推薦。</span>
            </div>
          )}
          {precision !== null && serviceMode !== null && <dl className="order-v2-business-summary" aria-label="建議服務日期摘要">
            <div><dt>排休類型</dt><dd>{serviceMode}</dd></div>
            <div><dt>建議開始</dt><dd>{precision.actual_start_date}</dd></div>
            <div><dt>建議完工</dt><dd>{precision.actual_end_date}</dd></div>
            <div><dt>合約服務日</dt><dd>{requiredDateCount} 天</dd></div>
          </dl>}

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
                      disabled={working !== null || isRecoveryActive || needsBasisUpdate}
                      onClick={() => changeDate(date, !selected)}
                    >
                      <span>{date}</span>
                      {selected && <span className="calendar-date-cell-badge">服務日</span>}
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

      {preview !== null && !needsBasisUpdate && (
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
