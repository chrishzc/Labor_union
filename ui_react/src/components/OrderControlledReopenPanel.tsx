import { useUnsavedDraft } from './UnsavedChanges';
import { useEffect, useRef, useState, type FC } from 'react';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { OrderMutationError } from '../api/orders/order_mutation_errors';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import {
  applyReopenFlow, previewReopenFlow, retryReopenApplyFlow,
  retryReopenObservationFlow, updateReopenReason,
} from '../adapters/orders/order_mutation_adapter';

interface Props {
  caseNo: string;
  startDisabled?: boolean;
  onObserved?: () => void;
  onBusyChange?: (busy: boolean) => void;
}

export const OrderControlledReopenPanel: FC<Props> = ({ caseNo, startDisabled = false, onObserved, onBusyChange }) => {
  const [, setRevision] = useState(0);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const previewController = useRef<AbortController | null>(null);
  const actionInFlight = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    const unsubscribe = orderMutationFlowStore.subscribe(() => setRevision((value) => value + 1));
    return () => { mounted.current = false; previewController.current?.abort(); unsubscribe(); };
  }, []);

  const draft = orderMutationFlowStore.getReopenDraft(caseNo);
  const status = draft?.status ?? 'closed';
  const inFlight = status === 'apply_pending' || status === 'receipt_received' || status === 'requery_loading';
  const unresolved = inFlight || status === 'outcome_unknown' || status === 'observation_failed';
  useEffect(() => { onBusyChange?.(unresolved || status === 'preview_loading'); }, [unresolved, status, onBusyChange]);
  useEffect(() => () => { onBusyChange?.(false); }, [onBusyChange]);

  const preview = async () => {
    if (startDisabled || unresolved || actionInFlight.current || status === 'preview_loading') return;
    previewController.current?.abort();
    const controller = new AbortController();
    previewController.current = controller;
    setError(null);
    try {
      const result = await previewReopenFlow(caseNo, { signal: controller.signal });
      if (result.case_no !== caseNo) throw new Error('重開檢查結果與本案不符。');
      if (controller.signal.aborted || !mounted.current) return;
      updateReopenReason(caseNo, reason.trim());
      await apply();
    } catch (caught) {
      if (!controller.signal.aborted) {
        setError(caught instanceof OrderMutationError && caught.code === 'order_reopen_financial_history_exists'
          ? '此案件已有取消相關的退款、沖正或結算紀錄，無法重開。請另建新案。'
          : caught instanceof Error ? caught.message : '無法檢查重開條件。');
      }
    }
  };

  const observe = async () => {
    const current = orderMutationFlowStore.getReopenDraft(caseNo);
    const receipt = current?.receiptView;
    if (!receipt || receipt.case_no !== caseNo || receipt.preview_fingerprint !== current?.previewView?.preview_fingerprint) {
      throw new Error('重開結果與本案或本次檢查不符。');
    }
    const detail = await ordersQueryClient.getOrderDetail(caseNo);
    if (detail.case_no !== caseNo || detail.order_status !== receipt.lifecycle_status) {
      throw new Error('已收到重開結果，但案件狀態尚未更新。請查詢結果，勿再次提交。');
    }
  };


  const apply = async (retry: 'apply' | 'observation' | null = null) => {
    if (actionInFlight.current || inFlight) return;
    const current = orderMutationFlowStore.getReopenDraft(caseNo);
    if (retry !== 'observation' && current?.previewView?.case_no !== caseNo) {
      setError('請先取得同一案件的有效重開預覽。');
      return;
    }
    if (retry === null && current?.status !== 'preview_ready') return;
    actionInFlight.current = true;
    setError(null);
    onBusyChange?.(true);
    try {
      if (retry === 'observation') await retryReopenObservationFlow(caseNo, observe);
      else if (retry === 'apply') await retryReopenApplyFlow(caseNo, observe);
      else await applyReopenFlow(caseNo, observe);
      if (mounted.current) onObserved?.();
    } catch (caught) {
      if (mounted.current) setError(caught instanceof Error ? caught.message : '重開未完成。');
    } finally {
      actionInFlight.current = false;
      if (mounted.current) {
        const phase = orderMutationFlowStore.getReopenDraft(caseNo)?.status;
        onBusyChange?.(phase === 'outcome_unknown' || phase === 'observation_failed');
      }
    }
  };
  useUnsavedDraft('重開案件', { '重開原因': reason }, { baseline: { '重開原因': '' }, enabled: status !== 'observed', busy: unresolved });


  return (
    <section aria-label={`案件 ${caseNo} 重開取消案件`}>
      <h4>重開取消案件</h4>
      <p>重開後須重新確認月嫂與排班。原指派、排班及檔期鎖不會恢復。</p>
      <label>重開原因（選填）<textarea aria-label="重開原因（選填）" maxLength={500} value={reason} disabled={startDisabled || unresolved || status === 'preview_loading'} onChange={event => setReason(event.target.value)} /></label>
      <button type="button" disabled={startDisabled || unresolved || status === 'preview_loading'} onClick={() => void preview()}>重開訂單</button>
      {status === 'preview_loading' && <p role="status">正在檢查重開條件…</p>}
      {draft?.previewView && (
        <>
          <p>{draft.previewView.before_status} → {draft.previewView.after_status}</p>
          <p>取消事件：#{draft.previewView.cancellation_event_id}</p>

        </>
      )}
      {inFlight && <p role="status">正在重開並確認結果，請留在此頁。</p>}
      {status === 'outcome_unknown' && (
        <div role="alert"><p>重開結果尚未確認。重試會使用同一筆操作。</p>
          <button type="button" onClick={() => void apply('apply')}>重試重開</button>
        </div>
      )}
      {status === 'observation_failed' && (
        <div role="alert"><p>已收到重開結果，尚未確認最新狀態。</p>
          <button type="button" onClick={() => void apply('observation')}>查詢重開結果</button>
        </div>
      )}
      {status === 'observed' && <p role="status">訂單已重開為「{draft?.receiptView?.lifecycle_status}」。請重新確認服務日期與排班。</p>}
      {(error || draft?.error) && <p role="alert">{error ?? draft?.error?.message}</p>}
    </section>
  );
};
