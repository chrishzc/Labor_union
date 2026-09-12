/**
 * File: OrderServiceCompletionActions.tsx
 * Description: 提供管理員依 AutoComplete owner command 完成服務的 Preview、確認、Apply 與 receipt UI。
 */
import React, { useEffect, useRef, useState, useSyncExternalStore } from 'react';

import {
  orderServiceCompletionClient,
  type OrderServiceCompletionPreview,
} from '../api/orders/order_service_completion_client';
import { orderMutationFlowStore, type CompletionCommand } from '../adapters/orders/order_mutation_flow_store';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { ApiHttpError, ApiNetworkError, ApiTimeoutError } from '../api/shared/typed_errors';

interface Props {
  caseNo: string;
  orderStatus: string;
  onCompleted: () => void | Promise<void>;
}

type MutationStatus = 'idle' | 'previewing' | 'previewed' | 'applying' | 'completed' | 'failed'
  | 'outcome_unknown' | 'observation_failed' | 'observing';

const subscribeCompletion = (listener: () => void) => orderMutationFlowStore.subscribe(listener);

function completionErrorMessage(caught: unknown): string {
  if (caught instanceof ApiTimeoutError || caught instanceof ApiNetworkError) {
    return '連線暫時中斷，請重新查詢案件狀態後再確認。';
  }
  if (caught instanceof ApiHttpError) {
    if (caught.status === 401 || caught.status === 403) return '目前帳號無權處理這筆服務完成。';
    if (caught.status === 409) return '案件資料已變更，請重新查詢後再檢查完工影響。';
    if (caught.retryable || caught.status >= 500) return '服務完成處理暫時無法使用，請稍後重新查詢。';
    return '這筆操作未通過完工檢查，請核對目前案件狀態。';
  }
  return '無法處理服務完成，請重新查詢後再試。';
}

const ServiceCompletionForCase: React.FC<Props> = ({
  caseNo,
  orderStatus,
  onCompleted,
}) => {
  const [localStatus, setStatus] = useState<MutationStatus>('idle');
  const flow = useSyncExternalStore(subscribeCompletion, () => orderMutationFlowStore.getCompletion(caseNo));
  const status = flow?.status ?? localStatus;
  const receipt = flow?.receipt ?? null;
  const [preview, setPreview] = useState<OrderServiceCompletionPreview | null>(null);
  const [reason, setReason] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [localError, setError] = useState<string | null>(null);
  const error = flow?.error ?? localError;
  const working = useRef(false);
  const mounted = useRef(true);
  const observationSequence = useRef(0);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      observationSequence.current += 1;
      const current = orderMutationFlowStore.getCompletion(caseNo);
      if (current?.status === 'observing' && current.receipt) {
        orderMutationFlowStore.setCompletion(caseNo, {
          ...current, status: 'observation_failed', error: '服務完成已登記，請只重新讀取案件結果。',
        });
      }
    };
  }, []);

  const previewCompletion = async () => {
    if (working.current || orderMutationFlowStore.getCompletion(caseNo)) return;
    working.current = true;
    setStatus('previewing');
    setError(null);
    setPreview(null);
    setConfirmed(false);
    try {
      const result = await orderServiceCompletionClient.preview(caseNo);
      if (!mounted.current) return;
      setPreview(result);
      setStatus('previewed');
    } catch (caught) {
      if (!mounted.current) return;
      setError(completionErrorMessage(caught));
      setStatus('failed');
    } finally {
      working.current = false;
    }
  };

  const observeCompletion = async () => {
    const observation = ++observationSequence.current;
    const current = orderMutationFlowStore.getCompletion(caseNo);
    if (!current?.receipt) return;
    orderMutationFlowStore.setCompletion(caseNo, { ...current, status: 'observing', error: null });
    try {
      const [detail, terms] = await Promise.all([
        ordersQueryClient.getOrderDetail(caseNo),
        ordersQueryClient.getOrderTerms(caseNo),
      ]);
      if (observation !== observationSequence.current) return;
      if (detail.case_no !== caseNo || terms.case_no !== caseNo
        || detail.order_status !== '訂單完成' || terms.order_version < current.receipt.order_version) {
        throw new Error('服務完成尚未取得對應案件狀態與版本。');
      }
      if (mounted.current) await onCompleted();
      if (observation !== observationSequence.current) return;
      orderMutationFlowStore.setCompletion(caseNo, { ...current, status: 'completed', error: null });
    } catch {
      if (observation !== observationSequence.current) return;
      orderMutationFlowStore.setCompletion(caseNo, {
        ...current, status: 'observation_failed', error: '服務完成已登記，請只重新讀取案件結果。',
      });
    }
  };

  const sendCompletion = async (command: CompletionCommand) => {
    const current = orderMutationFlowStore.getCompletion(caseNo);
    if (working.current || current?.receipt || current?.status === 'applying') return;
    const recoveringUnknown = current?.status === 'outcome_unknown' && current.command !== null;
    working.current = true;
    orderMutationFlowStore.setCompletion(caseNo, { status: 'applying', command, receipt: null, error: null });
    setError(null);
    try {
      const result = await orderServiceCompletionClient.apply(caseNo, command.preview, command.reason, command.key);
      // Preserve the receipt even when its original view has been unmounted.
      orderMutationFlowStore.setCompletion(caseNo, {
        status: 'observation_failed', command: null, receipt: result, error: null,
      });
      if (!mounted.current) return;
      setPreview(null);
      setConfirmed(false);
      await observeCompletion();
    } catch (caught) {
      const rejected = caught instanceof ApiHttpError && caught.status >= 400 && caught.status < 500
        && caught.status !== 408 && caught.status !== 429 && !caught.retryable;
      if (rejected && !recoveringUnknown) {
        orderMutationFlowStore.clearCompletion(caseNo);
        if (mounted.current) {
          setError(completionErrorMessage(caught));
          setPreview(null);
          setStatus('failed');
        }
      } else {
        orderMutationFlowStore.setCompletion(caseNo, {
          status: 'outcome_unknown', command, receipt: null,
          error: recoveringUnknown
            ? '服務完成結果仍未確認；請恢復權限後以原操作重新確認。'
            : '服務完成結果尚未確認，請以原操作重新確認。',
        });
      }
    } finally {
      working.current = false;
    }
  };

  const applyCompletion = async () => {
    if (!preview || !confirmed || !reason.trim() || status !== 'previewed' || working.current) return;
    const command = { preview, reason: reason.trim(), key: `ui-order-service-completion-${crypto.randomUUID()}` };
    await sendCompletion(command);
  };

  const retryObservation = async () => {
    if (!receipt || working.current || status !== 'observation_failed') return;
    working.current = true;
    setError(null);
    try { await observeCompletion(); } finally { working.current = false; }
  };

  return (
    <div className="calendar-workbench-card" style={{ marginTop: '16px' }}>
      <div className="calendar-card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="calendar-badge actual">完工</span>
          <h4 className="calendar-card-title">服務完成與結案階段</h4>
        </div>
      </div>

      {orderStatus === '訂單完成' ? (
        <div role="status" style={{ color: '#166534', fontWeight: 700 }}>
          本案已有正式服務完成事件；後續請至客戶帳務與服務人員款項流程處理結算。
        </div>
      ) : orderStatus !== '服務中' ? (
        <div role="status" style={{ color: '#92400e' }}>
          目前狀態為「{orderStatus}」；只有已確認實際開工且進入服務中的案件，才能預覽服務完成。
        </div>
      ) : (
        <>
          <p style={{ margin: '0 0 10px', color: '#57423b', fontSize: '0.86rem' }}>
            系統會重新核對正式排班、完整服務日、服務結束時刻與可完成條件；不接受手動指定目標狀態。
          </p>
          <button
            type="button"
            className="btn-secondary-action"
            disabled={status === 'previewing' || status === 'applying' || status === 'outcome_unknown' || receipt !== null}
            onClick={() => void previewCompletion()}
          >
            {status === 'previewing' ? '正在檢查完成影響…' : '檢查服務完成影響'}
          </button>

          {preview && (
            <div style={{ background: '#fffdfb', border: '1px solid #fed9b8', borderRadius: '12px', padding: '14px', marginTop: '12px' }}>
              <strong>服務完成內容已檢查</strong>
              <div>目前狀態：{preview.current_status}</div>
              <div>完成時刻：{new Date(preview.completion_instant).toLocaleString('zh-TW')}</div>
              <div>正式服務日：{preview.official_service_dates.join('、')}</div>
              <div>確認後訂單會進入服務完成狀態。</div>
              <label style={{ display: 'block', marginTop: '10px', fontWeight: 700 }}>
                完工確認原因
                <textarea
                  aria-label="完工確認原因"
                  rows={2}
                  maxLength={500}
                  value={reason}
                  disabled={status === 'applying' || status === 'outcome_unknown'}
                  onChange={(event) => {
                    setReason(event.target.value);
                    setConfirmed(false);
                  }}
                  style={{ width: '100%', marginTop: '6px' }}
                />
              </label>
              <label style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                <input
                  type="checkbox"
                  checked={confirmed}
                  disabled={status === 'applying' || status === 'outcome_unknown'}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                我已核對正式服務日與完成時刻，確認將訂單標記為服務完成。
              </label>
              <button
                type="button"
                className="btn-primary-action"
                style={{ marginTop: '10px' }}
                disabled={!confirmed || !reason.trim() || status !== 'previewed'}
                onClick={() => void applyCompletion()}
              >
                {status === 'applying' ? '服務完成套用中…' : '確認套用服務完成'}
              </button>
            </div>
          )}
        </>
      )}
      {status === 'outcome_unknown' && (
        <button type="button" className="btn-secondary-action" onClick={() => {
          if (flow?.command) void sendCompletion(flow.command);
        }}>
          以原操作重新確認服務完成
        </button>
      )}
      {(status === 'observation_failed' || status === 'observing') && (
        <button type="button" className="btn-secondary-action" disabled={status === 'observing'}
          onClick={() => void retryObservation()}>
          {status === 'observing' ? '正在讀取服務完成結果…' : '只重新讀取服務完成結果'}
        </button>
      )}

      {receipt && (
        <div role="status" style={{ color: '#166534', fontWeight: 700, marginTop: '10px' }}>
          {status === 'completed' ? '服務完成已登記並完成回讀。' : '服務完成已登記，案件狀態尚未回讀確認，請重新查詢案件。'}
        </div>
      )}
      {error && <div role="alert" style={{ color: '#b91c1c', marginTop: '10px' }}>{error}</div>}
    </div>
  );
};

export const OrderServiceCompletionActions: React.FC<Props> = (props) => (
  <ServiceCompletionForCase key={props.caseNo} {...props} />
);
