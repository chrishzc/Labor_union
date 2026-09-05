import { useEffect, useRef, useState, type FC } from 'react';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import {
  applyReopenFlow, previewReopenFlow, retryReopenApplyFlow,
  retryReopenObservationFlow, updateReopenReason,
} from '../adapters/orders/order_mutation_adapter';

interface Props {
  caseNo: string;
  onObserved?: () => void;
  onBusyChange?: (busy: boolean) => void;
}

export const OrderControlledReopenPanel: FC<Props> = ({ caseNo, onObserved, onBusyChange }) => {
  const [, setRevision] = useState(0);
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
  useEffect(() => { onBusyChange?.(unresolved); }, [unresolved, onBusyChange]);
  useEffect(() => () => { onBusyChange?.(false); }, [onBusyChange]);

  const preview = async () => {
    if (unresolved || actionInFlight.current || status === 'preview_loading') return;
    previewController.current?.abort();
    const controller = new AbortController();
    previewController.current = controller;
    setError(null);
    try {
      const result = await previewReopenFlow(caseNo, { signal: controller.signal });
      if (result.case_no !== caseNo) throw new Error('受控重開預覽案件識別不一致。');
    } catch (caught) {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : '受控重開預覽失敗。');
    }
  };

  const observe = async () => {
    const current = orderMutationFlowStore.getReopenDraft(caseNo);
    const receipt = current?.receiptView;
    if (!receipt || receipt.case_no !== caseNo || receipt.preview_fingerprint !== current?.previewView?.preview_fingerprint) {
      throw new Error('受控重開收據案件識別或 fingerprint 不一致。');
    }
    const detail = await ordersQueryClient.getOrderDetail(caseNo);
    if (detail.case_no !== caseNo || detail.order_status !== receipt.lifecycle_status) {
      throw new Error('重開已回傳收據，但正式案件尚未觀察到收據狀態；只重試回讀，不重送重開。');
    }
  };

  const apply = async (retry: 'apply' | 'observation' | null = null) => {
    if (actionInFlight.current || inFlight) return;
    if (retry !== 'observation' && draft?.previewView?.case_no !== caseNo) {
      setError('請先取得同一案件的有效重開預覽。');
      return;
    }
    if (retry === null && status !== 'preview_ready') return;
    actionInFlight.current = true;
    setError(null);
    onBusyChange?.(true);
    try {
      if (retry === 'observation') await retryReopenObservationFlow(caseNo, observe);
      else if (retry === 'apply') await retryReopenApplyFlow(caseNo, observe);
      else await applyReopenFlow(caseNo, observe);
      if (mounted.current) onObserved?.();
    } catch (caught) {
      if (mounted.current) setError(caught instanceof Error ? caught.message : '受控重開未完成。');
    } finally {
      actionInFlight.current = false;
      if (mounted.current) {
        const phase = orderMutationFlowStore.getReopenDraft(caseNo)?.status;
        onBusyChange?.(phase === 'outcome_unknown' || phase === 'observation_failed');
      }
    }
  };

  return (
    <section aria-label={`案件 ${caseNo} 受控重開`}>
      <h4>受控重開取消案件</h4>
      <p>只重開正式案件狀態；不恢復舊指派、舊排班或舊檔期鎖，必須重新完成 Scheduling 預覽。</p>
      <button type="button" disabled={unresolved || status === 'preview_loading'} onClick={() => void preview()}>檢查受控重開影響</button>
      {status === 'preview_loading' && <p role="status">檢查受控重開中…</p>}
      {draft?.previewView && (
        <>
          <p>{draft.previewView.before_status} → {draft.previewView.after_status}</p>
          <p>取消事件：#{draft.previewView.cancellation_event_id}</p>
          <label>重開原因
            <textarea aria-label="Beta 受控重開原因" maxLength={500} value={draft.reason} disabled={unresolved}
              onChange={(event) => updateReopenReason(caseNo, event.target.value)} />
          </label>
          {status === 'preview_ready' && (
            <button type="button" disabled={!draft.reason.trim() || draft.previewView.case_no !== caseNo} onClick={() => void apply()}>確認受控重開</button>
          )}
        </>
      )}
      {inFlight && <p role="status">受控重開／正式回讀中，請勿切換操作。</p>}
      {status === 'outcome_unknown' && (
        <div role="alert"><p>重開結果未明；保留原內容與原冪等鍵，不建立新操作。</p>
          <button type="button" onClick={() => void apply('apply')}>以原操作重新確認重開結果</button>
        </div>
      )}
      {status === 'observation_failed' && (
        <div role="alert"><p>已收到重開收據，但正式回讀未完成。</p>
          <button type="button" onClick={() => void apply('observation')}>只重新讀取重開結果</button>
        </div>
      )}
      {status === 'observed' && <p role="status">受控重開已完成正式回讀：{draft?.receiptView?.lifecycle_status}。請重新確認正式服務日期與排班。</p>}
      {(error || draft?.error) && <p role="alert">{error ?? draft?.error?.message}</p>}
    </section>
  );
};