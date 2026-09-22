import { orderActualStartClient, type ActualStartPreview } from '../../api/orders/order_actual_start_client';
import { ordersQueryClient } from '../../api/orders/order_query_client';
import { ordersMutationClient } from '../../api/orders/order_mutation_client';
import type { ServiceDateConfirmationQueryView } from '../../api/orders/order_mutation_schemas';
import { ApiHttpError } from '../../api/shared/typed_errors';
import { OrderMutationError } from '../../api/orders/order_mutation_errors';
import { orderMutationFlowStore, type ActualStartCommand } from './order_mutation_flow_store';

export function serviceDatesNeedCompletion(caseNo: string): boolean {
  const draft = orderMutationFlowStore.getServiceDatesDraft(caseNo);
  const start = orderMutationFlowStore.getActualStart(caseNo);
  return draft?.status !== 'observed' && !!draft?.calculation?.startPreview && !!start
    && start.command.payload.preview_fingerprint === draft.calculation.startPreview.preview_fingerprint;
}

export function isServiceDateConflict(error: unknown): boolean {
  return (error instanceof ApiHttpError || error instanceof OrderMutationError) && error.status === 409;
}

export function sameServiceDates(left: readonly string[], right: readonly string[]): boolean {
  const orderedRight = [...right].sort();
  return left.length === right.length && [...left].sort().every((value, index) => value === orderedRight[index]);
}

/** Project only the existing server range at the proposed start; this does not approve a write. */
export function serviceDateRange(query: ServiceDateConfirmationQueryView, startDate: string): string[] {
  const first = query.selectable_dates[0];
  if (!first) throw new Error('目前沒有可用的服務日期範圍，請重新讀取。');
  const offset = Date.parse(`${startDate}T00:00:00Z`) - Date.parse(`${first}T00:00:00Z`);
  if (!Number.isFinite(offset)) throw new Error('請輸入有效的開始日期。');
  return query.selectable_dates.map((value) => new Date(Date.parse(`${value}T00:00:00Z`) + offset).toISOString().slice(0, 10));
}

export function assertStartDates(preview: ActualStartPreview, dates: string[]): void {
  if (preview.operation === 'reschedule' && !sameServiceDates(preview.actual_start.official_service_dates, dates)) {
    throw new Error('本案開始日變更會重排既有或歷史服務安排；目前選日與正式重排結果不同。請採用重排建議，或從案件異動辦理日期調整。尚未保存。');
  }
}

function commandFor(preview: ActualStartPreview): ActualStartCommand {
  return {
    idempotencyKey: `service-dates-start-${crypto.randomUUID()}`,
    payload: preview.operation === 'date_only' ? {
      operation: 'date_only', new_actual_start_date: preview.after_actual_start_date,
      expected_order_version: preview.order_version, preview_fingerprint: preview.preview_fingerprint,
    } : {
      operation: 'reschedule', new_actual_start_date: preview.after_actual_start_date,
      expected_order_version: preview.order_version, expected_scheduling_version: preview.scheduling_version,
      preview_fingerprint: preview.preview_fingerprint, reason: '核對服務日期並確認實際開始日',
    },
  };
}

/** Called only after human confirmation. Reuses Actual Start recovery and never retries a known receipt. */
export async function saveServiceDatesStart(caseNo: string, preview: ActualStartPreview): Promise<void> {
  let flow = orderMutationFlowStore.getActualStart(caseNo);
  if (flow && flow.command.payload.preview_fingerprint !== preview.preview_fingerprint) {
    if (flow.status !== 'observed') throw new Error('另一次實際開始日操作尚未完成，請先從實際開始日入口讀取結果。');
    flow = undefined;
  }
  if (flow?.status === 'applying' || flow?.status === 'observing') throw new Error('實際開始日正在處理，請稍候。');
  const command = flow?.command ?? commandFor(preview);
  const wasUnknown = flow?.status === 'outcome_unknown';
  if (wasUnknown && preview.operation === 'date_only') {
    const facts = await ordersQueryClient.getActualStart(caseNo);
    if (facts.case_no !== caseNo) throw new Error('開始日回讀案件不一致。');
    // Date-only has no durable receipt: observe current state before considering an explicit retry.
    if (facts.current_actual_start_date === preview.after_actual_start_date && facts.order_version === preview.order_version + 1) {
      flow = { ...flow!, status: 'observed', error: null };
      orderMutationFlowStore.setActualStart(caseNo, flow);
    } else if (facts.order_version !== preview.order_version) {
      throw new Error('開始日結果與原操作不同，請從實際開始日入口重新讀取並核對；未重送。');
    }
  }
  if (!flow?.receipt && flow?.status !== 'observed') {
    orderMutationFlowStore.setActualStart(caseNo, { status: 'applying', command, receipt: null, error: null });
    try {
      const receipt = await orderActualStartClient.apply(caseNo, command.payload, { idempotencyKey: command.idempotencyKey });
      flow = { status: 'observation_failed', command, receipt, error: null };
      orderMutationFlowStore.setActualStart(caseNo, flow);
    } catch (error) {
      const rejected = (error instanceof ApiHttpError || error instanceof OrderMutationError)
        && error.status >= 400 && error.status < 500 && error.status !== 408 && error.status !== 429;
      if (rejected && !wasUnknown) orderMutationFlowStore.clearActualStart(caseNo);
      else orderMutationFlowStore.setActualStart(caseNo, {
        status: 'outcome_unknown', command, receipt: null, error: '開始日保存結果尚未確認，請先讀取結果後接續。',
      });
      throw error;
    }
  }
  const receipt = flow?.receipt;
  if (receipt && (receipt.case_no !== caseNo || receipt.operation !== preview.operation
    || receipt.preview_fingerprint !== preview.preview_fingerprint
    || (receipt.operation === 'date_only' && receipt.actual_start_date !== preview.after_actual_start_date))) throw new Error('開始日回讀資料不一致，已停止接續保存。');
  const facts = await ordersQueryClient.getActualStart(caseNo);
  const expectedVersion = receipt?.order_version ?? preview.order_version + 1;
  if (facts.case_no !== caseNo || facts.current_actual_start_date !== preview.after_actual_start_date
    || facts.order_version !== expectedVersion
    || (receipt?.operation === 'reschedule' && facts.scheduling_version !== receipt.scheduling_version)) {
    throw new Error('開始日已回傳結果，但目前日期或版本不同，請重新讀取核對；未保存服務日期。');
  }
  orderMutationFlowStore.setActualStart(caseNo, { ...flow!, status: 'observed', error: null });
}

/** Fresh versions after the first commit; never carry the pre-save service-date Preview forward. */
export async function refreshServiceDatesAfterStart(caseNo: string, preview: ActualStartPreview): Promise<void> {
  const draft = orderMutationFlowStore.getServiceDatesDraft(caseNo);
  if (!draft?.queryView) throw new Error('服務日期草稿不存在，請重新核對。');
  const original = draft.queryView;
  const dates = [...draft.selectedDates];
  const flow = orderMutationFlowStore.getActualStart(caseNo);
  const current = await ordersMutationClient.getServiceDates(caseNo);
  const orderVersion = flow?.receipt?.order_version ?? preview.order_version + 1;
  const schedulingVersion = flow?.receipt?.scheduling_version ?? original.scheduling_version;
  if (current.case_no !== caseNo || current.order_version !== orderVersion
    || current.scheduling_version !== schedulingVersion || current.current_version !== original.current_version
    || current.contracted_service_days !== original.contracted_service_days) {
    throw new Error('開始日已保存，但服務日期或條件已被更新；請重新讀取並核對，未覆蓋其他人的安排。');
  }
  if (dates.length !== current.contracted_service_days || dates.some((date) => !current.selectable_dates.includes(date))) {
    throw new Error('開始日已保存，但此次服務日期不符合目前可選範圍或天數，請重新核對。');
  }
  orderMutationFlowStore.setServiceDatesQueryReady(caseNo, current);
  orderMutationFlowStore.updateServiceDatesSelection(caseNo, dates);
}
